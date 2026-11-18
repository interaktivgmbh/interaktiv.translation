from datetime import datetime, timezone
from typing import Any

import plone.api as api
from AccessControl.Permission import Permission
from zope.annotation.interfaces import IAnnotations
from zope.container.interfaces import IContainerModifiedEvent
from zope.globalrequest import getRequest

from interaktiv.translation.helpers.encryption import stored_value
from interaktiv.translation.registry.translation import ITranslationSettings
from interaktiv.translation.storage import (
    CHANGE_NOTE_KEY,
    MACHINE_TRANSLATION_KEY,
    MANAGE_TRANSLATIONS_PERMISSION,
    STORING_KEY,
    get_current_user_id,
    get_translation_marker,
    review_note,
)

PUBLISHED_STATES = ("published",)

API_KEY_RECORD = f"{ITranslationSettings.__identifier__}.api_key"


def restrict_translations_on_checkout(event: Any) -> None:
    # a working copy is not translatable; a tuple of roles stops acquiring
    Permission(MANAGE_TRANSLATIONS_PERMISSION, (), event.working_copy).setRoles(())


def restore_translations_on_checkin(event: Any) -> None:
    # translatable again after the checkin; a list of roles acquires
    Permission(MANAGE_TRANSLATIONS_PERMISSION, (), event.object).setRoles([])


def note_machine_translation_checkin(event: Any) -> None:
    translation_marker = get_translation_marker(event.object)
    if translation_marker is None:
        return

    reviewer = get_current_user_id()
    request = getRequest()
    if request is not None:
        IAnnotations(request)[CHANGE_NOTE_KEY] = review_note(translation_marker, reviewer)

    _set_translation_marker_to_reviewed(event.object, translation_marker, reviewer)


def note_machine_translation_edit(obj: Any, event: Any) -> None:
    if IContainerModifiedEvent.providedBy(event):
        return

    request = getRequest()

    if request is not None and IAnnotations(request).get(STORING_KEY):
        return

    translation_marker = get_translation_marker(obj)
    if translation_marker is None:
        return

    translation_marker = dict(translation_marker)
    translation_marker["edited_by"] = get_current_user_id()
    translation_marker["edited"] = datetime.now(timezone.utc).isoformat()
    IAnnotations(obj)[MACHINE_TRANSLATION_KEY] = translation_marker


def note_machine_translation_before_publication(obj: Any, event: Any) -> None:
    new_state = getattr(event, "new_state", None)
    if not new_state or event.kwargs is None:
        # an automatic transition carries no kwargs: no comment to write into
        return

    translation_marker = get_translation_marker(obj)
    if translation_marker is None:
        return

    if getattr(event.new_state, "id", None) not in PUBLISHED_STATES:
        return

    _review_note = review_note(translation_marker, get_current_user_id())
    user_comment = event.kwargs.get("comment") or ""
    event.kwargs["comment"] = f"{user_comment} — {_review_note}" if user_comment else _review_note


def note_machine_translation_publication(obj: Any, event: Any) -> None:
    translation_marker = get_translation_marker(obj)
    if translation_marker is None:
        return
    if api.content.get_state(obj, default=None) not in PUBLISHED_STATES:
        return

    _set_translation_marker_to_reviewed(obj, translation_marker, get_current_user_id())


def _set_translation_marker_to_reviewed(content: Any, marker: Any, reviewer: str) -> None:
    marker = dict(marker)
    marker["reviewed_by"] = reviewer
    marker["reviewed"] = datetime.now(timezone.utc).isoformat()
    IAnnotations(content)[MACHINE_TRANSLATION_KEY] = marker


def encrypt_api_key(event: Any) -> None:
    """Encrypts the API key on its way into the registry, whichever way it comes."""
    record = event.record
    if getattr(record, "__name__", None) != API_KEY_RECORD:
        return

    # plain text, or encrypted with the site's secret while the environment has one
    value = stored_value(record.value)
    if value is not None:
        # sets the record again; the value stored as it should be passes unchanged
        record.value = value
