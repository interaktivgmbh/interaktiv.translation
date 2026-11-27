import html
import posixpath
import re
from typing import Any, Dict, List, Match, NamedTuple, Optional, Tuple, Union
from urllib.parse import urlparse

import plone.api as api
from Acquisition import aq_base, aq_parent
from plone.app.contenttypes.interfaces import IFile, IImage
from plone.app.uuid.utils import uuidToObject
from plone.app.multilingual.interfaces import ITranslationLocator, ITranslationManager
from plone.dexterity.content import DexterityContent
from plone.dexterity.utils import iterSchemata
from plone.restapi.deserializer.utils import path2uid
from plone.restapi.serializer.utils import uid_to_url
from Products.CMFCore.interfaces import IFolderish, ISiteRoot

from interaktiv.translation.blocks import HTML_BLOCK_KEY, HTML_BLOCK_TYPE
from interaktiv.translation.helpers.field_access import field_value, schema_field
from interaktiv.translation.helpers.field_selection import is_reference
from interaktiv.translation.settings import settings
from zope.schema import getFieldNames

LINK_PREFIXES = ("/", "./", "../", "http://", "https://")
RESOLVEUID_MARKER = "resolveuid/"
ABSOLUTE_PATH_OPERATION = "plone.app.querystring.operation.string.absolutePath"
NAVIGATION_PATH_OPERATION = "plone.app.querystring.operation.string.path"
RELATIVE_PATH_OPERATION = "plone.app.querystring.operation.string.relativePath"
PATH_OPERATIONS = (ABSOLUTE_PATH_OPERATION, NAVIGATION_PATH_OPERATION, RELATIVE_PATH_OPERATION)
API_PREFIXES = ("/++api++", "/api")
HTML_LINK_PREFIXES = ("/", "http://", "https://")
HTML_LINK_TAG = re.compile(r"<(a|img)\s[^<>]*>", re.IGNORECASE)
HTML_ATTRIBUTE = r"""(?<=\s)(%s\s*=\s*)(["'])(.*?)\2"""
HTML_LINK_ATTRIBUTES = {
    "a": re.compile(HTML_ATTRIBUTE % "href", re.IGNORECASE | re.DOTALL),
    "img": re.compile(HTML_ATTRIBUTE % "src", re.IGNORECASE | re.DOTALL),
}
HTML_ALT = re.compile(HTML_ATTRIBUTE % "alt", re.IGNORECASE | re.DOTALL)
HTML_MARKUP = re.compile(r"<[^<>]*>")
# a computed scale, image-800-<hash>.png: stored with the one image it was made of
COMPUTED_SCALE = re.compile(r"^/@@images/(\w+?)-\d+-[0-9a-f]{32}\.\w+$")

# only a broken link is a mistake: an editor may link content of another language
STATUS_TRANSLATED = "translated"  # the target is in that language
STATUS_TRANSLATABLE = "translatable"  # in another, a translation exists
STATUS_UNTRANSLATED = "untranslated"  # in another, without a translation
STATUS_INDEPENDENT = "independent"  # the target has no language of its own
STATUS_BROKEN = "broken"  # the target is not found
STATUS_EXTERNAL = "external"  # leads out of the site; not checked any further
LINK_STATUSES = (
    STATUS_TRANSLATED,
    STATUS_TRANSLATABLE,
    STATUS_UNTRANSLATED,
    STATUS_INDEPENDENT,
    STATUS_BROKEN,
    STATUS_EXTERNAL,
)


def _resolveuid_uid(path: str) -> str:
    parsed_path = urlparse(path).path or ""

    return parsed_path.split("resolveuid/")[-1].split("/")[0].strip()


def _get_translated_resolveuid_path(path: str, target_language: str) -> Optional[str]:
    uid = _resolveuid_uid(path)
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


def _object_path_as_uid_link(path: str, content: Optional[Any] = None) -> Optional[str]:
    """The path of an object as resolveuid link, or ``None`` if no object is found."""
    portal = api.portal.get()
    portal_path = "/".join(portal.getPhysicalPath())

    locator = urlparse(path).path or ""
    if not locator:
        return None

    for prefix in API_PREFIXES:
        if locator == prefix or locator.startswith(f"{prefix}/"):
            locator = locator[len(prefix) :] or "/"
            break

    # handle relative path like "../"
    if not locator.startswith("/"):
        if content is None:
            return None
        locator = posixpath.normpath(f"{'/'.join(content.getPhysicalPath())}/{locator}")
        if locator != portal_path and not locator.startswith(f"{portal_path}/"):
            return None

    uid_link = path2uid(content if content is not None else portal, locator)
    # path2uid returns locator if target could not be found
    if uid_link == locator:
        return None

    return uid_link


def _get_translated_object_path(path: str, target_language: str, content: Optional[Any] = None) -> Optional[str]:
    uid_link = _object_path_as_uid_link(path, content)
    if uid_link is None:
        return None

    translated = _get_translated_resolveuid_path(uid_link, target_language)
    if translated is None:
        return None

    parsed = urlparse(path)
    tail = f"?{parsed.query}" if parsed.query else ""
    tail += f"#{parsed.fragment}" if parsed.fragment else ""

    return f"{translated}{tail}"


def _link_target(path: str, content: Optional[Any] = None) -> Optional[Any]:
    """The object an internal link points at; ``None`` if it is not found."""
    uid_link = path if RESOLVEUID_MARKER in path else _object_path_as_uid_link(path, content)
    if uid_link is None:
        return None

    return uuidToObject(_resolveuid_uid(uid_link))


class LinkOutcome(NamedTuple):
    value: Optional[str]
    internal: bool
    target: Optional[Any] = None


def _translation_of(target: Any, language: str) -> Optional[Any]:
    try:
        return ITranslationManager(target).get_translation(language)
    except TypeError:  # the target is not translatable
        return None


def link_status(target: Optional[Any], language: Optional[str]) -> str:
    """How a link to ``target`` stands to ``language``, the language of the content holding it."""
    if target is None:
        return STATUS_BROKEN

    target_language = getattr(aq_base(target), "language", None)
    if not language or not target_language:
        return STATUS_INDEPENDENT
    if target_language == language:
        return STATUS_TRANSLATED
    if _translation_of(target, language) is not None:
        return STATUS_TRANSLATABLE

    return STATUS_UNTRANSLATED


def _status(target: Optional[Any], language: str, moved: bool, check: bool) -> str:
    # a link just pointed at the translation of its target is translated now
    if moved and not check:
        return STATUS_TRANSLATED

    return link_status(target, language)


def _is_external(path: Any) -> bool:
    if not isinstance(path, str):
        return False

    stripped = path.strip()

    return stripped.startswith(("http://", "https://")) and not stripped.startswith(api.portal.get().absolute_url())


def _external_entry(text: Optional[str], value: str) -> Dict[str, Any]:
    return {"text": text, "before": value.strip(), "after": None, "kind": "link", "status": STATUS_EXTERNAL}


def _kind(target: Optional[Any]) -> str:
    """report: what a link points at — an image, a file or anything else"""
    if IImage.providedBy(target):
        return "image"
    if IFile.providedBy(target):
        return "file"

    return "link"


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


def _physical_path(obj: Any) -> str:
    return "/".join(obj.getPhysicalPath())


def _path_root(operation: str, obj: Optional[Any]) -> str:
    """Where a path of the criterion starts: the portal, or the navigation root of the object."""
    if operation == NAVIGATION_PATH_OPERATION and obj is not None:
        return _physical_path(api.portal.get_navigation_root(obj))

    return _physical_path(api.portal.get())


def _relative_target(content: Any, target: str) -> Optional[Any]:
    """The object a relative path names, walked from the content; ``None`` where a name leads nowhere."""
    obj = content
    for name in target.split("/"):
        if name in ("", "."):
            continue
        if name == "..":
            if not ISiteRoot.providedBy(obj):
                obj = aq_parent(obj)
        elif IFolderish.providedBy(obj) and name in obj:
            obj = obj[name]
        else:
            return None

    return obj


def _relative_path(content: Any, translated: Any, target_language: str) -> str:
    """The path to the translated folder from where the translation of the content lies, or will lie."""
    page = _translation_of(content, target_language)
    if page is not None:
        start = _physical_path(page)
    else:
        try:
            container = ITranslationLocator(content)(target_language)
        except TypeError:  # the content is not translatable
            container = aq_parent(content)
        start = f"{_physical_path(container)}/{content.getId()}"

    return posixpath.relpath(_physical_path(translated), start)


def _translated_path_criterion(
    value: str,
    target_language: str,
    operation: str = ABSOLUTE_PATH_OPERATION,
    content: Optional[Any] = None,
) -> Tuple[Optional[str], Optional[Any], Optional[Any]]:
    """A path criterion pointed at the translation of its folder, with both folders."""
    target, separator, depth = value.partition("::")
    suffix = f"{separator}{depth}"
    portal = api.portal.get()
    relative = operation == RELATIVE_PATH_OPERATION
    if content is None and operation != ABSOLUTE_PATH_OPERATION:
        return None, None, None

    is_uid = not relative and "/" not in target
    rooted = False
    if relative:
        folder = _relative_target(content, target)
        if folder is not None and aq_base(folder) is aq_base(content):
            return None, None, None
    elif is_uid:
        folder = uuidToObject(target)
    else:
        root = _path_root(operation, content)
        rooted = target == root or target.startswith(f"{root}/")
        path = target if rooted else f"{root}{target}"
        folder = portal.unrestrictedTraverse(path.rstrip("/"), None)
    if folder is None or aq_base(folder) is aq_base(portal):
        return None, None, None

    translated = _translation_of(folder, target_language)
    if translated is None:
        return value, folder, None

    if is_uid:
        return f"{translated.UID()}{suffix}", folder, translated
    if relative:
        return f"{_relative_path(content, translated, target_language)}{suffix}", folder, translated

    translated_path = _physical_path(translated)
    if not rooted:
        # as it came: from its root, without the root's own path
        translated_path = translated_path[len(_path_root(operation, translated)) :] or "/"
    return f"{translated_path}{suffix}", folder, translated


def _resolve_path_criterion(
    criterion: Dict[str, Any],
    target_language: str,
    report: Optional[List[Dict[str, Any]]],
    text: Optional[str],
    check: bool = False,
    content: Optional[Any] = None,
) -> None:
    value = criterion.get("v")
    if not isinstance(value, str) or not value.strip():
        return

    translated_value, folder, translated = _translated_path_criterion(
        value.strip(), target_language, criterion.get("o"), content
    )
    if folder is None:
        return

    if report is not None:
        report.append(
            {
                "text": text or "query",
                "before": folder.absolute_url(),
                "after": translated.absolute_url() if translated is not None else None,
                "kind": "link",
                "status": _status(folder, target_language, translated is not None, check),
            }
        )
    if not check:
        criterion["v"] = translated_value


def _is_link(path: str) -> bool:
    stripped = path.strip()

    return stripped.startswith(LINK_PREFIXES) or RESOLVEUID_MARKER in stripped


def _resolve_internal_link(path: str, target_language: str, content: Optional[Any] = None) -> LinkOutcome:
    if not isinstance(path, str) or not path.strip():
        return LinkOutcome(None, False)

    if not _is_link(path):
        return LinkOutcome(None, False)

    parsed = urlparse(path)

    # a full URL that names a host but no page
    if not parsed.path:
        return LinkOutcome(None, False)

    portal_url = api.portal.get().absolute_url()
    if path.startswith("http") and not path.startswith(portal_url):
        return LinkOutcome(None, False)

    target = _link_target(path, content)
    if RESOLVEUID_MARKER in path:
        return LinkOutcome(_get_translated_resolveuid_path(path, target_language), True, target)

    return LinkOutcome(_get_translated_object_path(path, target_language, content), True, target)


def _html_link(value: str, target_language: str) -> LinkOutcome:
    """A link of raw HTML pointed at the translation of its target, written the way it came."""
    if value.startswith("//"):
        return LinkOutcome(None, False)
    if RESOLVEUID_MARKER in value:
        return _resolve_internal_link(value, target_language)
    if not value.startswith(HTML_LINK_PREFIXES):
        return LinkOutcome(None, False)

    outcome = _resolve_internal_link(value, target_language)
    if not outcome.internal or outcome.target is None:
        return outcome
    translated = _translation_of(outcome.target, target_language)
    uid_link = _object_path_as_uid_link(value)
    if translated is None or uid_link is None:
        return LinkOutcome(None, True, outcome.target)

    # what follows the target: a view or a scale, the query and the fragment
    _uid, slash, view = uid_link.split(RESOLVEUID_MARKER, 1)[1].partition("/")
    tail = COMPUTED_SCALE.sub(r"/@@images/\1", f"{slash}{view}")
    portal = api.portal.get()
    portal_url = portal.absolute_url()
    portal_path = _physical_path(portal)
    parsed = urlparse(value)
    tail += f"?{parsed.query}" if parsed.query else ""
    tail += f"#{parsed.fragment}" if parsed.fragment else ""
    locator = parsed.path
    head = portal_url if value.startswith(portal_url) else ""
    if head:
        locator = urlparse(value[len(portal_url) :]).path
    for prefix in API_PREFIXES:
        if locator == prefix or locator.startswith(f"{prefix}/"):
            head += prefix
            locator = locator[len(prefix) :]
            break
    if locator == portal_path or locator.startswith(f"{portal_path}/"):
        head += portal_path

    return LinkOutcome(f"{head}{_physical_path(translated)[len(portal_path) :]}{tail}", True, outcome.target)


def _html_link_text(markup: str, tag: Match[str]) -> Optional[str]:
    """report: the alternative text of an image, the text of a link"""
    if tag.group(1).lower() == "img":
        alt = HTML_ALT.search(tag.group(0))
        if alt is None:
            return None

        return html.unescape(alt.group(3)).strip() or None

    end = tag.end()
    close = markup.lower().find("</a", end)
    if close == -1:
        return None

    return html.unescape(HTML_MARKUP.sub("", markup[end:close])).strip() or None


def _resolve_html_links(
    markup: str,
    target_language: str,
    report: Optional[List[Dict[str, Any]]],
    text: Optional[str],
    check: bool = False,
) -> str:
    """Points the internal links of raw HTML at their targets' translations; nothing else of it changes."""

    def link_tag(tag: Match[str]) -> str:
        link_text = _html_link_text(markup, tag) or text

        def attribute(found: Match[str]) -> str:
            value = html.unescape(found.group(3)).strip()
            outcome = _html_link(value, target_language)
            if not outcome.internal:
                if check and report is not None and _is_external(value):
                    report.append(_external_entry(link_text, value))
                return found.group(0)
            if report is not None:
                kind = _kind(outcome.target)
                entry_text = link_text
                if kind == "image" and not entry_text and outcome.target is not None:
                    entry_text = outcome.target.Title() or None
                report.append(
                    {
                        "text": entry_text,
                        "before": _readable(value),
                        "after": _readable(outcome.value),
                        "kind": kind,
                        "status": _status(outcome.target, target_language, outcome.value is not None, check),
                    }
                )
            if outcome.value is None or check:
                return found.group(0)

            return f"{found.group(1)}{found.group(2)}{html.escape(outcome.value)}{found.group(2)}"

        return HTML_LINK_ATTRIBUTES[tag.group(1).lower()].sub(attribute, tag.group(0))

    return HTML_LINK_TAG.sub(link_tag, markup)


def _image_text(branch: Dict[str, Any], image: Any) -> Optional[str]:
    """What the report calls an image nothing else names: its alternative text, else its title."""
    alt = branch.get("alt")
    if isinstance(alt, str) and alt.strip():
        return alt

    return image.Title() or None


def _resolve_internal_link_recursive(
    branch: Any,
    target_language: str,
    report: Optional[List[Dict[str, Any]]] = None,
    content: Optional[Any] = None,
    text: Optional[str] = None,
    link_keys: Optional[List[str]] = None,
    check: bool = False,
) -> Any:
    """Points the internal links of a tree of blocks at their targets' translations and reports them."""
    if link_keys is None:
        link_keys = settings().block_link_fields

    if isinstance(branch, list):
        for value in branch:
            _resolve_internal_link_recursive(value, target_language, report, content, text, link_keys, check)

    elif isinstance(branch, dict):
        if branch.get("i") == "path" and branch.get("o") in PATH_OPERATIONS:
            _resolve_path_criterion(branch, target_language, report, text, check, content)
            return branch

        link_text = text
        if branch.get("type") in ("link", "a"):
            link_text = _slate_text(branch) or link_text
        elif isinstance(branch.get("title"), str) and branch["title"].strip():
            link_text = branch["title"]

        for key, value in branch.items():
            if isinstance(value, str) and key == HTML_BLOCK_KEY and branch.get("@type") == HTML_BLOCK_TYPE:
                branch[key] = _resolve_html_links(value, target_language, report, link_text, check)
            elif isinstance(value, (dict, list)):
                _resolve_internal_link_recursive(value, target_language, report, content, link_text, link_keys, check)
            elif isinstance(value, str) and key in link_keys:
                outcome = _resolve_internal_link(value, target_language, content)
                if not outcome.internal:
                    if check and report is not None and _is_external(value):
                        report.append(_external_entry(link_text, value))
                    continue
                if report is not None:
                    kind = _kind(outcome.target)
                    entry_text = link_text
                    if kind == "image" and not entry_text:
                        entry_text = _image_text(branch, outcome.target)
                    report.append(
                        {
                            "text": entry_text,
                            "before": _readable(value),
                            "after": _readable(outcome.value),
                            "kind": kind,
                            "status": _status(outcome.target, target_language, outcome.value is not None, check),
                        }
                    )
                if outcome.value is not None and not check:
                    branch[key] = outcome.value

    return branch


def postprocess_links(
    content: Any,
    field_id: str,
    value: Any,
    target_language: str,
    report: Optional[List[Dict[str, Any]]] = None,
    check: bool = False,
) -> Any:

    if isinstance(value, str):
        if field_id in settings().link_fields:
            outcome = _resolve_internal_link(value, target_language, content)
            if outcome.internal and report is not None:
                report.append(
                    {
                        "text": field_id,
                        "before": _readable(value),
                        "after": _readable(outcome.value),
                        "kind": _kind(outcome.target),
                        "status": _status(outcome.target, target_language, outcome.value is not None, check),
                    }
                )
            elif check and report is not None and _is_external(value):
                report.append(_external_entry(field_id, value))
            if outcome.value is not None and not check:
                value = outcome.value

    elif isinstance(value, (dict, list)):
        value = _resolve_internal_link_recursive(value, target_language, report, content, check=check)

    return value


def _translated_target(
    target: DexterityContent,
    field_id: str,
    target_language: str,
    report: Optional[List[Dict[str, Any]]],
    check: bool = False,
) -> DexterityContent:
    translated = _translation_of(target, target_language)

    if report is not None:
        report.append(
            {
                "text": field_id,
                "before": target.absolute_url(),
                "after": translated.absolute_url() if translated is not None else None,
                "kind": _kind(target),
                "status": _status(target, target_language, translated is not None, check),
            }
        )

    return translated if translated is not None else target


def translated_targets(
    field_id: str,
    value: Union[DexterityContent, List[Optional[DexterityContent]], None],
    target_language: str,
    report: Optional[List[Dict[str, Any]]] = None,
    check: bool = False,
) -> Union[DexterityContent, List[DexterityContent], None]:
    """The targets of a reference field, each replaced by its translation where there is one."""
    if value is None:
        return None
    if not isinstance(value, list):
        return _translated_target(value, field_id, target_language, report, check)

    return [_translated_target(item, field_id, target_language, report, check) for item in value if item is not None]


def check_links(content: Any) -> List[Dict[str, Any]]:
    """The links of the content as it is now, each with its status; changes nothing."""
    language = getattr(aq_base(content), "language", None) or ""
    report: List[Dict[str, Any]] = []

    # a type may have always translated and link fields without a schema saying so
    field_ids = [field_id for schema in iterSchemata(content) for field_id in getFieldNames(schema)]
    field_ids += settings().always_fields + settings().link_fields
    for field_id in dict.fromkeys(field_ids):
        value = field_value(content, field_id)
        if value is None:
            continue
        if is_reference(schema_field(content, field_id)):
            translated_targets(field_id, value, language, report, check=True)
        elif isinstance(value, (str, dict, list)):
            postprocess_links(content, field_id, value, language, report, check=True)

    return [
        {
            "text": entry["text"],
            "kind": entry["kind"],
            "status": entry["status"],
            "url": entry["before"],
            # where the link could point instead
            "translation": entry["after"] if entry["status"] == STATUS_TRANSLATABLE else None,
        }
        for entry in report
    ]
