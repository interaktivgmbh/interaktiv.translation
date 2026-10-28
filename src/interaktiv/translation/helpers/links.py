import posixpath
from typing import Any, Dict, List, NamedTuple, Optional
from urllib.parse import urlparse

import plone.api as api
from plone.app.uuid.utils import uuidToObject
from plone.app.multilingual.interfaces import ITranslationManager
from plone.restapi.deserializer.utils import path2uid
from plone.restapi.serializer.utils import uid_to_url

from interaktiv.translation.settings import settings

LINK_PREFIXES = ("/", "./", "../", "http://", "https://")
RESOLVEUID_MARKER = "resolveuid/"


def _get_translated_resolveuid_path(path: str, target_language: str) -> Optional[str]:
    parsed = urlparse(path)
    parsed_path = parsed.path or ""

    uid = parsed_path.split("resolveuid/")[-1].split("/")[0].strip()
    obj = uuidToObject(uid)
    if obj is None:
        return None

    try:
        translated_obj = ITranslationManager(obj).get_translation(target_language)
    except TypeError:  # obj is not translatable
        return None
    if translated_obj is None:
        return None

    translated_uid = translated_obj.UID()
    return path.replace(uid, translated_uid)


def _get_translated_object_path(path: str, target_language: str, content: Optional[Any] = None) -> Optional[str]:
    portal = api.portal.get()
    portal_path = "/".join(portal.getPhysicalPath())

    parsed = urlparse(path)
    locator = parsed.path or ""
    if not locator:
        return None

    # handle query and fragment
    tail = f"?{parsed.query}" if parsed.query else ""
    tail += f"#{parsed.fragment}" if parsed.fragment else ""

    # remove api prefix
    for prefix in ("/++api++", "/api"):
        if locator == prefix or locator.startswith(f"{prefix}/"):
            locator = locator[len(prefix) :] or "/"
            break

    # handle relative path like "../"
    if not locator.startswith("/"):
        if content is None:
            return None
        locator = posixpath.normpath(f"{'/'.join(content.getPhysicalPath())}/{locator}")
        if locator != portal_path and not locator.startswith(f"{portal_path}/"):
            # locator is outside portal
            return None

    uid_link = path2uid(content if content is not None else portal, locator)
    # path2uid returns locator if target could not be found
    if uid_link == locator:
        return None

    translated = _get_translated_resolveuid_path(uid_link, target_language)
    if translated is None:
        return None

    return f"{translated}{tail}"


class LinkOutcome(NamedTuple):
    value: Optional[str]
    internal: bool


def _readable(value: Optional[str]) -> Optional[str]:
    """report: convert uid link to url format for readability"""
    if not value:
        return value

    return uid_to_url(value)


def _slate_text(node: Dict) -> str:
    """report: get text of slate node recursively"""
    parts = []
    for child in node.get("children") or []:
        if not isinstance(child, dict):
            continue
        parts.append(child["text"] if isinstance(child.get("text"), str) else _slate_text(child))

    return "".join(parts).strip()


def _is_link(path: str) -> bool:
    stripped = path.strip()

    return stripped.startswith(LINK_PREFIXES) or RESOLVEUID_MARKER in stripped


def _resolve_internal_link(path: str, target_language: str, content: Optional[Any] = None) -> LinkOutcome:
    if not isinstance(path, str) or not path.strip():
        return LinkOutcome(None, False)

    if not _is_link(path):
        return LinkOutcome(None, False)

    parsed = urlparse(path)

    # A full URL that names a host but no page.
    if not parsed.path:
        return LinkOutcome(None, False)

    portal_url = api.portal.get().absolute_url()
    if path.startswith("http") and not path.startswith(portal_url):
        return LinkOutcome(None, False)

    if RESOLVEUID_MARKER in path:
        return LinkOutcome(_get_translated_resolveuid_path(path, target_language), True)

    return LinkOutcome(_get_translated_object_path(path, target_language, content), True)


def _resolve_internal_link_recursive(
    branch: Any,
    target_language: str,
    report: Optional[List[Dict[str, Any]]] = None,
    content: Optional[Any] = None,
    text: Optional[str] = None,
    link_keys: Optional[List[str]] = None,
) -> Any:
    if link_keys is None:
        link_keys = settings().block_link_fields

    # handle list
    if isinstance(branch, list):
        for value in branch:
            _resolve_internal_link_recursive(value, target_language, report, content, text, link_keys)

    # handle dict
    elif isinstance(branch, dict):
        link_text = text
        if branch.get("type") in ("link", "a"):
            link_text = _slate_text(branch) or link_text
        elif isinstance(branch.get("title"), str) and branch["title"].strip():
            link_text = branch["title"]

        for key, value in branch.items():
            if isinstance(value, (dict, list)):
                _resolve_internal_link_recursive(value, target_language, report, content, link_text, link_keys)
            elif isinstance(value, str) and key in link_keys:
                outcome = _resolve_internal_link(value, target_language, content)
                if not outcome.internal:
                    continue
                if report is not None:
                    report.append(
                        {
                            "text": link_text,
                            "before": _readable(value),
                            "after": _readable(outcome.value),
                        }
                    )
                # update value if translated content was found
                if outcome.value is not None:
                    branch[key] = outcome.value

    return branch


def postprocess_links(
    content: Any,
    field_id: str,
    value: Any,
    target_language: str,
    report: Optional[List[Dict[str, Any]]] = None,
) -> Any:

    # process string
    if isinstance(value, str):
        if field_id in settings().link_fields:
            outcome = _resolve_internal_link(value, target_language, content)
            if outcome.internal and report is not None:
                report.append(
                    {
                        "text": field_id,
                        "before": _readable(value),
                        "after": _readable(outcome.value),
                    }
                )
            if outcome.value is not None:
                value = outcome.value

    # process tree structure
    elif isinstance(value, (dict, list)):
        value = _resolve_internal_link_recursive(value, target_language, report, content)

    return value
