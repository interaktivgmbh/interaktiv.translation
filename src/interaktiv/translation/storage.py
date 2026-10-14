from datetime import datetime, timezone
from typing import Any, Dict, Optional

import plone.api as api
from AccessControl import getSecurityManager
from Acquisition import aq_base, aq_inner, aq_parent
from Products.GenericSetup.tool import UNKNOWN
from interaktiv.translation import logger
from interaktiv.translation.providers.base import PROVIDERS, TranslationError
from interaktiv.translation.settings import settings
from plone.app.iterate.interfaces import ICheckinCheckoutPolicy, IObjectArchiver
from plone.app.iterate.permissions import CheckoutPermission
from plone.app.multilingual.interfaces import ITranslationManager
from plone.locking.interfaces import ILockable
from zope.annotation.interfaces import IAnnotations
from zope.component import getMultiAdapter
from zope.event import notify
from zope.globalrequest import getRequest
from zope.lifecycleevent import ObjectModifiedEvent
from zope.publisher.interfaces.browser import IBrowserRequest

CHANGE_NOTE_KEY = "plone.app.versioningbehavior-changeNote"
MACHINE_TRANSLATION_KEY = "interaktiv.translation.machine_translation"
STORING_KEY = "interaktiv.translation.storing"

MANAGE_TRANSLATIONS_PERMISSION = "plone.app.multilingual: Manage Translations"

WORKING_COPY_REFUSAL = "This is a working copy. Translate the original instead."
EXCLUDED_TYPE_REFUSAL = "This content type is not translated by machine."

STATUS_MANUAL = "manual"
STATUS_MACHINE_UNREVIEWED = "machine_unreviewed"
STATUS_MACHINE_EDITED = "machine_edited"
STATUS_MACHINE_REVIEWED = "machine_reviewed"


def review_note(marker: Dict[str, Any], reviewer: str) -> str:
    return (
        f"Machine translation into {marker['target_language']} with {marker['provider']}, "
        f"reviewed by {reviewer}"
    )


def get_translation_marker(content: Any) -> Optional[Dict[str, Any]]:
    annotations = IAnnotations(content, None)
    translation_marker = annotations.get(MACHINE_TRANSLATION_KEY) if annotations is not None else None
    if not translation_marker or translation_marker.get("reviewed_by"):
        return None

    return translation_marker


def get_current_user_id() -> str:
    return api.user.get_current().getId()


def translation_status(content: Any) -> str:
    annotations = IAnnotations(content, None)
    marker = annotations.get(MACHINE_TRANSLATION_KEY) if annotations is not None else None
    if not marker:
        return STATUS_MANUAL
    if marker.get("reviewed_by"):
        return STATUS_MACHINE_REVIEWED
    if marker.get("edited_by"):
        return STATUS_MACHINE_EDITED

    return STATUS_MACHINE_UNREVIEWED


MULTILINGUAL_PROFILE = "plone.app.multilingual:default"
ITERATE_PROFILE = "plone.app.iterate:default"


class TranslationStorage:
    def __init__(self, content: Any, request: Optional[Any] = None) -> None:
        self.content = content
        self.request = request
        # What the last `store` did, for the report an editor is shown:
        # where the translation went and whether that object is new.
        self.stored_as: Optional[str] = None
        self.created: bool = False

    @property
    def multilingual(self) -> bool:
        # The profile version, not `getProfileImportDate`: that one answers
        # out of the import log files portal_setup keeps, whose names carry
        # the `profile-` prefix the caller does not write — so it says "never
        # imported" for a profile that is installed. This is what Plone's own
        # installer asks.
        setup_tool = api.portal.get_tool("portal_setup")

        return setup_tool.getLastVersionForProfile(MULTILINGUAL_PROFILE) != UNKNOWN

    @property
    def working_copies(self) -> bool:
        # `plone.app.iterate` installed on the site: an existing translation is
        # then not overwritten but checked out, so the machine translation
        # lands in a working copy an editor reviews and checks in. The profile
        # version, the same way `multilingual` is read — the admin switches the
        # feature on by installing iterate.
        setup_tool = api.portal.get_tool("portal_setup")

        return setup_tool.getLastVersionForProfile(ITERATE_PROFILE) != UNKNOWN

    def uses_working_copies(self, content: Any) -> bool:
        # iterate checks out only what can be locked: a type without the
        # `plone.locking` behavior (a stock Folder, say) is never checked out,
        # so its translation is overwritten as on a site without iterate.
        return self.working_copies and ILockable(content, None) is not None

    def existing_translation(self, target_language: str) -> Optional[Any]:
        if not self.multilingual:
            return None

        try:
            return ITranslationManager(self.content).get_translation(target_language)
        except TypeError:
            # Not translatable content — the site root, say.
            return None

    def baseline(self) -> Optional[Any]:
        policy = ICheckinCheckoutPolicy(self.content, None)
        if policy is None:
            return None

        return policy.getBaseline()

    @property
    def is_working_copy(self) -> bool:
        return self.baseline() is not None

    @property
    def is_excluded_type(self) -> bool:
        return getattr(self.content, "portal_type", None) in settings().excluded_types

    def working_copy_of(self, translation: Any) -> Optional[Any]:
        # The working copy of a checked-out translation, or None. Answers None
        # where iterate is not installed on the site, so callers need not
        # guard separately.
        policy = ICheckinCheckoutPolicy(translation, None)
        if policy is None:
            return None

        return policy.getWorkingCopy()

    @staticmethod
    def locked(translation: Any) -> bool:
        lockable = ILockable(translation, None)

        return lockable is not None and lockable.locked()

    def checkout_allowed(self, translation: Any) -> bool:
        # need to check locked for Plone < 6.1
        if self.locked(translation):
            return False

        control = getMultiAdapter((translation, self.request or getRequest()), name="iterate_control")

        return control.checkout_allowed()

    def checkout_refusal(self, translation: Any, target_language: str) -> Optional[str]:
        if self.checkout_allowed(translation):
            return None

        if self.locked(translation):
            return (
                f"The {target_language} translation is being edited by someone right now. "
                "Try again once it is saved."
            )
        if not getSecurityManager().checkPermission(CheckoutPermission, translation):
            return f"You are not allowed to check out the {target_language} translation."

        return f"The {target_language} translation cannot be checked out."

    def refusal(self, target_language: str, overwrite: bool) -> Optional[str]:
        # The one place that decides whether a save would be refused, so the
        # service can turn DeepL away before it is paid and `store` can raise
        # the same way. None means "go ahead".
        if self.is_excluded_type:
            return EXCLUDED_TYPE_REFUSAL

        if self.is_working_copy:
            return WORKING_COPY_REFUSAL

        existing = self.existing_translation(target_language)
        if existing is None:
            return None

        if aq_base(existing) is aq_base(self.content):
            # Asked for its own language, pam answers the object itself:
            # "translating" would check out or overwrite the original.
            return f"The content is already in {target_language}. Translate it into another language."

        if self.uses_working_copies(existing):
            # A translation exists but iterate is on: a working copy is made
            # instead of overwriting it. Only a working copy that is already
            # there needs the editor's leave to be replaced.
            if self.working_copy_of(existing) is not None:
                if not overwrite:
                    return (
                        f"There is already a working copy of the {target_language} translation. "
                        "Ask for overwrite to update it."
                    )
                return None

            # A fresh checkout would be made: iterate's own rules first, or
            # somebody editing the translation right now would lose their lock
            # and with it their unsaved work.
            return self.checkout_refusal(existing, target_language)

        if not overwrite:
            return f"There is already a {target_language} translation. Ask for overwrite to replace it."

        return None

    def store(self, fields: Dict[str, Any], target_language: str, overwrite: bool = False) -> Any:
        # mark request annotations for machine created content
        request = getRequest()
        annotations = IAnnotations(request) if request is not None else None
        if annotations is not None:
            annotations[STORING_KEY] = True

        try:
            if self.multilingual:
                return self._store_as_translation(fields, target_language, overwrite)

            return self._store_in_place(fields, target_language)
        finally:
            if annotations is not None:
                annotations.pop(STORING_KEY, None)

    @staticmethod
    def provider_title() -> str:
        name = settings().provider
        factory = PROVIDERS.get(name)
        if factory is None:
            return name

        return factory.title or name

    def _note_change(self, target_language: str) -> None:
        if self.request is None or not IBrowserRequest.providedBy(self.request):
            return
        IAnnotations(self.request)[CHANGE_NOTE_KEY] = (
            f"Machine translation into {target_language} with {self.provider_title()}"
        )

    def _mark_machine_translated(self, content: Any, target_language: str) -> None:
        IAnnotations(content)[MACHINE_TRANSLATION_KEY] = {
            "provider": self.provider_title(),
            "target_language": target_language,
            "translated": datetime.now(timezone.utc).isoformat(),
        }

    def _apply(self, content: Any, fields: Dict[str, Any], target_language: str) -> Any:
        for name, value in fields.items():
            setattr(content, name, value)

        self._mark_machine_translated(content, target_language)
        self._note_change(target_language)
        # Subscribers, not just the catalog: versioning, link integrity and
        # cache purging all hang off the modified event, and a translation that
        # skips it leaves an object nobody can roll back.
        notify(ObjectModifiedEvent(content))
        content.reindexObject()

        return content

    def _store_in_place(self, fields: Dict[str, Any], target_language: str) -> Any:
        # The page now holds another language, and nothing else is going to say
        # so: no second object was made here, and it is the field the catalogue
        # and the front end both read. On the other path
        # `plone.app.multilingual` sets it on the object it creates.
        self.stored_as = "in_place"
        self.created = False

        return self._apply(self.content, {**fields, "language": target_language}, target_language)

    def _store_as_translation(self, fields: Dict[str, Any], target_language: str, overwrite: bool = False) -> Any:
        existing = self.existing_translation(target_language)

        if existing is not None:
            refusal = self.refusal(target_language, overwrite)
            if refusal is not None:
                raise TranslationError(refusal, status=409)
            if self.uses_working_copies(existing):
                # Don't touch the live translation: translate into a working
                # copy the editor reviews and checks in. Replacing a standing
                # one needed `overwrite`, which `refusal` asked for.
                working_copy = self.working_copy_of(existing)
                self.stored_as = "working_copy"
                if working_copy is None:
                    working_copy = self._checkout(existing, target_language)
                    self.created = True
                else:
                    self.created = False

                return self._apply(working_copy, fields, target_language)

            self.stored_as = "translation"
            self.created = False

            return self._apply(existing, fields, target_language)

        manager = ITranslationManager(self.content)
        try:
            manager.add_translation(target_language)
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not create the %s translation: %s", target_language, error)
            raise TranslationError(f"Plone refused to create the {target_language} translation.", status=400) from error
        existing = manager.get_translation(target_language)

        if existing is None:
            raise TranslationError(f"There is no {target_language} translation to write to.", status=400)

        self.stored_as = "translation"
        self.created = True

        return self._apply(existing, fields, target_language)

    def _checkout(self, translation: Any, target_language: str) -> Any:
        # A fresh checkout into the translation's own folder, with the
        # baseline versioned first so the history names what it was cut from.
        self._version_baseline_before_translation(translation, target_language)

        policy = ICheckinCheckoutPolicy(translation)
        working_copy_container = aq_parent(aq_inner(translation))
        working_copy = policy.checkout(working_copy_container)
        return working_copy

    def _version_baseline_before_translation(self, translation: Any, target_language: str) -> None:
        # call "archiver.save" before handleBeforeCheckout does it
        # -> creates version baseline with a custom comment
        archiver = IObjectArchiver(translation, None)
        if archiver is None or not archiver.isVersionable():
            return
        if archiver.isModified() or not archiver.isVersioned():
            comment = f"Baseline before machine translation into {target_language} with {self.provider_title()}"
            archiver.save(comment)
