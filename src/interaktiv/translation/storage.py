from datetime import datetime, timezone
from typing import Any, Dict, Optional

import plone.api as api
from AccessControl import getSecurityManager
from Acquisition import aq_base, aq_inner, aq_parent
from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.GenericSetup.tool import UNKNOWN
from interaktiv.translation import _, logger
from interaktiv.translation.helpers.field_access import set_field_value
from interaktiv.translation.providers.base import PROVIDERS, TranslationError
from interaktiv.translation.settings import settings
from interaktiv.translation.translation_id import TRANSLATED_TITLE_KEY
from plone.app.iterate.dexterity.utils import get_relations
from plone.app.iterate.interfaces import ICheckinCheckoutPolicy, IObjectArchiver
from plone.app.iterate.permissions import CheckoutPermission
from plone.app.multilingual.interfaces import ITranslationManager
from plone.locking.interfaces import ILockable
from zope.annotation.interfaces import IAnnotations
from zope.component import getMultiAdapter, getUtility
from zope.event import notify
from zope.globalrequest import getRequest
from zope.i18n import translate
from zope.i18nmessageid import Message
from zope.intid.interfaces import IIntIds
from zope.lifecycleevent import ObjectModifiedEvent
from zope.publisher.interfaces.browser import IBrowserRequest
from zope.schema.interfaces import IVocabularyFactory

CHANGE_NOTE_KEY = "plone.app.versioningbehavior-changeNote"
MACHINE_TRANSLATION_KEY = "interaktiv.translation.machine_translation"
STORING_KEY = "interaktiv.translation.storing"

MANAGE_TRANSLATIONS_PERMISSION = "plone.app.multilingual: Manage Translations"


class Refusal(str):
    """Why a translation is refused: a text, its translatable message, a code and its values."""

    code: str
    values: Dict[str, str]
    message: Message

    def __new__(cls, code: str, message: Message, **values: str) -> "Refusal":
        if values:
            message = Message(message, mapping=values)
        refusal = super().__new__(cls, translate(message))
        refusal.code = code
        refusal.values = values
        refusal.message = message

        return refusal

    def error(self, status: int) -> TranslationError:
        return TranslationError(self.message, status=status, code=self.code, values=self.values)


WORKING_COPY_REFUSAL = Refusal("working_copy", _("This is a working copy. Translate the original instead."))
SOURCE_WORKING_COPY_REFUSAL = Refusal(
    "source_working_copy", _("This content has an open working copy. Check it in or discard it, then translate.")
)
EXCLUDED_TYPE_REFUSAL = Refusal("excluded_type", _("This content type is not translated by machine."))
NO_LANGUAGE_REFUSAL = Refusal(
    "no_language", _("This content has no language of its own. Give it a language, then translate.")
)
TARGET_LANGUAGES_VOCABULARY = "interaktiv.translation.TargetLanguages"

STATUS_MANUAL = "manual"
STATUS_MACHINE_UNREVIEWED = "machine_unreviewed"
STATUS_MACHINE_EDITED = "machine_edited"
STATUS_MACHINE_REVIEWED = "machine_reviewed"
STATUS_MACHINE_WITHOUT_REVIEW = "machine_without_review"


def content_language(content: Any) -> Optional[str]:
    # own language only, never one acquired from a parent
    return getattr(aq_base(content), "language", None) or None


def source_language_of(content: Any, given: Optional[str] = None) -> Optional[str]:
    # content without a language of its own is in the site's default language
    return given or content_language(content) or settings().default_source_language


def review_note(marker: Dict[str, Any], reviewer: str) -> str:
    return f"Machine translation into {marker['target_language']} with {marker['provider']}, reviewed by {reviewer}"


def get_translation_marker(content: Any) -> Optional[Dict[str, Any]]:
    annotations = IAnnotations(content, None)
    translation_marker = annotations.get(MACHINE_TRANSLATION_KEY) if annotations is not None else None
    if not translation_marker or translation_marker.get("reviewed_by"):
        return None

    return translation_marker


def get_current_user_id() -> str:
    return api.user.get_current().getId()


def has_workflow(content: Any) -> bool:
    return bool(api.portal.get_tool("portal_workflow").getChainFor(content))


def translation_status(content: Any) -> str:
    annotations = IAnnotations(content, None)
    marker = annotations.get(MACHINE_TRANSLATION_KEY) if annotations is not None else None
    if not marker:
        return STATUS_MANUAL
    if marker.get("reviewed_by"):
        return STATUS_MACHINE_REVIEWED
    if not has_workflow(content):
        return STATUS_MACHINE_WITHOUT_REVIEW
    if marker.get("edited_by"):
        return STATUS_MACHINE_EDITED

    return STATUS_MACHINE_UNREVIEWED


MULTILINGUAL_PROFILE = "plone.app.multilingual:default"
ITERATE_PROFILE = "plone.app.iterate:default"


class TranslationStorage:
    def __init__(self, content: Any, request: Optional[Any] = None) -> None:
        self.content = content
        self.request = request
        self.stored_as: Optional[str] = None
        self.created: bool = False
        self.source_language: Optional[str] = None

    @property
    def multilingual(self) -> bool:
        # not getProfileImportDate: it misses a profile named without the "profile-" prefix
        setup_tool = api.portal.get_tool("portal_setup")

        return setup_tool.getLastVersionForProfile(MULTILINGUAL_PROFILE) != UNKNOWN

    @property
    def working_copies(self) -> bool:
        setup_tool = api.portal.get_tool("portal_setup")

        return setup_tool.getLastVersionForProfile(ITERATE_PROFILE) != UNKNOWN

    def uses_working_copies(self, content: Any) -> bool:
        # iterate checks out only what can be locked; anything else is overwritten
        return self.working_copies and ILockable(content, None) is not None

    def existing_translation(self, target_language: str) -> Optional[Any]:
        if not self.multilingual:
            return None

        try:
            return ITranslationManager(self.content).get_translation(target_language)
        except TypeError:
            # not translatable content, the site root say
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
    def open_working_copy(self) -> Optional[Any]:
        # iterate answers a working copy itself as its own working copy
        if self.is_working_copy:
            return None

        return self.working_copy_of(self.content)

    @property
    def has_open_working_copy(self) -> bool:
        return self.open_working_copy is not None

    @property
    def has_no_language(self) -> bool:
        if not self.multilingual or IPloneSiteRoot.providedBy(self.content):
            return False

        return content_language(self.content) is None

    @property
    def is_excluded_type(self) -> bool:
        return getattr(self.content, "portal_type", None) in settings().excluded_types

    @property
    def content_refusal(self) -> Optional[Refusal]:
        if self.is_excluded_type:
            return EXCLUDED_TYPE_REFUSAL

        if self.has_no_language:
            return NO_LANGUAGE_REFUSAL

        return None

    def working_copy_of(self, translation: Any) -> Optional[Any]:
        # None also where iterate is not installed
        if ICheckinCheckoutPolicy(translation, None) is None:
            return None

        # not iterate's getWorkingCopy(): it takes the first relation, even a broken one
        own_id = getUtility(IIntIds).queryId(aq_base(translation))
        for relation in get_relations(translation):
            if relation.from_id == own_id and not relation.isBroken():
                return relation.to_object

        return None

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

    def checkout_refusal(self, translation: Any, target_language: str) -> Optional[Refusal]:
        if self.checkout_allowed(translation):
            return None

        if self.locked(translation):
            return Refusal(
                "target_locked",
                _("The ${language} translation is being edited by someone right now. Try again once it is saved."),
                language=target_language,
            )
        if not getSecurityManager().checkPermission(CheckoutPermission, translation):
            return Refusal(
                "checkout_not_allowed",
                _("You are not allowed to check out the ${language} translation."),
                language=target_language,
            )

        return Refusal(
            "checkout_refused", _("The ${language} translation cannot be checked out."), language=target_language
        )

    def is_offered(self, target_language: str) -> bool:
        factory = getUtility(IVocabularyFactory, name=TARGET_LANGUAGES_VOCABULARY)

        return target_language in factory(self.content)

    def target_refusal(self, target_language: str) -> Optional[Refusal]:
        # check if target is its own language (without multilingual it is stored in place)
        if self.multilingual and target_language == content_language(self.content):
            return Refusal(
                "own_language",
                _("The content is already in ${language}. Translate it into another language."),
                language=target_language,
            )

        if not self.is_offered(target_language):
            return Refusal(
                "not_offered", _("${language} is not offered for machine translation."), language=target_language
            )

        return None

    def refusal(self, target_language: str, overwrite: bool) -> Optional[Refusal]:
        # None means "go ahead"; asked before the translation service is paid
        if self.content_refusal is not None:
            return self.content_refusal

        if self.is_working_copy:
            return WORKING_COPY_REFUSAL

        if self.has_open_working_copy:
            return SOURCE_WORKING_COPY_REFUSAL

        refusal = self.target_refusal(target_language)
        if refusal is not None:
            return refusal

        existing = self.existing_translation(target_language)
        if existing is None:
            return None

        if self.uses_working_copies(existing):
            # a working copy that is already there holds somebody's work and is never replaced
            if self.working_copy_of(existing) is not None:
                return Refusal(
                    "target_working_copy",
                    _(
                        "There is already a working copy of the ${language} translation. Check it in or discard it first."  # noqa: E501
                    ),
                    language=target_language,
                )

            # iterate's own rules first: a checkout would take the lock of somebody editing
            return self.checkout_refusal(existing, target_language)

        if not overwrite:
            return Refusal(
                "translation_exists",
                _("There is already a ${language} translation. Ask for overwrite to replace it."),
                language=target_language,
            )

        return None

    def store(
        self,
        fields: Dict[str, Any],
        target_language: str,
        overwrite: bool = False,
        source_language: Optional[str] = None,
    ) -> Any:
        self.source_language = source_language_of(self.content, source_language)
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
            "source_language": self.source_language,
            "target_language": target_language,
            "translated": datetime.now(timezone.utc).isoformat(),
        }

    def _apply(self, content: Any, fields: Dict[str, Any], target_language: str) -> Any:
        for name, value in fields.items():
            set_field_value(content, name, value)

        self._mark_machine_translated(content, target_language)
        self._note_change(target_language)
        # versioning, link integrity and cache purging hang off the modified event
        notify(ObjectModifiedEvent(content))
        content.reindexObject()

        return content

    def _store_in_place(self, fields: Dict[str, Any], target_language: str) -> Any:
        # no second object was made: the page itself holds the other language now
        self.stored_as = "in_place"
        self.created = False

        return self._apply(self.content, {**fields, "language": target_language}, target_language)

    def _store_as_translation(self, fields: Dict[str, Any], target_language: str, overwrite: bool = False) -> Any:
        existing = self.existing_translation(target_language)

        if existing is not None:
            refusal = self.refusal(target_language, overwrite)
            if refusal is not None:
                raise refusal.error(409)
            if self.uses_working_copies(existing):
                working_copy = self._checkout(existing, target_language)
                self.stored_as = "working_copy"
                self.created = True

                return self._apply(working_copy, fields, target_language)

            self.stored_as = "translation"
            self.created = False

            return self._apply(existing, fields, target_language)

        manager = ITranslationManager(self.content)
        # our id chooser names the translation after its translated title (translation_id.py)
        request = getRequest()
        annotations = IAnnotations(request) if request is not None else None
        title = fields.get("title")
        if annotations is not None and isinstance(title, str):
            annotations[TRANSLATED_TITLE_KEY] = title
        try:
            manager.add_translation(target_language)
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not create the %s translation: %s", target_language, error)
            raise TranslationError(
                _("Plone refused to create the ${language} translation."),
                status=400,
                code="create_refused",
                values={"language": target_language},
            ) from error
        finally:
            if annotations is not None:
                annotations.pop(TRANSLATED_TITLE_KEY, None)
        existing = manager.get_translation(target_language)

        if existing is None:
            raise TranslationError(
                _("There is no ${language} translation to write to."),
                status=400,
                code="no_translation",
                values={"language": target_language},
            )

        self.stored_as = "translation"
        self.created = True

        return self._apply(existing, fields, target_language)

    def _checkout(self, translation: Any, target_language: str) -> Any:
        # the baseline is versioned first, so the history names what it was cut from
        self._version_baseline_before_translation(translation, target_language)

        policy = ICheckinCheckoutPolicy(translation)
        working_copy_container = aq_parent(aq_inner(translation))
        working_copy = policy.checkout(working_copy_container)
        return working_copy

    def _version_baseline_before_translation(self, translation: Any, target_language: str) -> None:
        # archiver.save before handleBeforeCheckout does it: a baseline version with our comment
        archiver = IObjectArchiver(translation, None)
        if archiver is None or not archiver.isVersionable():
            return
        if archiver.isModified() or not archiver.isVersioned():
            comment = f"Baseline before machine translation into {target_language} with {self.provider_title()}"
            archiver.save(comment)
