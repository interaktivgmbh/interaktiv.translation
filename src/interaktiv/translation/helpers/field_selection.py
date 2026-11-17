"""Which fields of a content type the translation lists, and how it would treat them.

These are the suggestions the add-on makes on its own: what a site decides per
field (``metadata_selection``) comes on top of them.

Every listed field has a role and a mode:

* role ``always``: goes along whatever the site decides — title, description,
  the page content and the type's primary field (the image of an image).
* role ``default``: goes along unless the site leaves it out.
* role ``impossible``: cannot go along — a structure the add-on cannot take apart.
* mode ``translate``, ``copy`` (taken over as it is) or ``mapping`` (through the
  metadata mapping); ``None`` for a field that cannot go along.

``reason`` names the rule that decided the mode, for the control panel to tell.

The mode is a suggestion: for a field of role ``default`` the site says how it goes
along, ``translate`` or ``copy``, among the modes the field can take (``modes``).
Only a text can be translated; a reference, a link, a language independent field and
a field the site names to be copied (``copied_fields``) are taken over. What always
goes along, and what the mapping translates, has no choice.

A reference (a relation, or a list of them) is taken over pointing at the target's
translation where there is one, else at the target itself — as an editor may
choose content of another language too. A link field (``link_fields``) is taken
over the same way: an internal link points at the translation of its target.
Neither is ever mapped.

The listing (``get_listed_fields``) leaves the mapping out of the mode and tells it
apart as ``mapped``: the control panel shows the mapping it is editing, not the
saved one, and a field taken out of the mapping falls back to its mode.
"""

import json
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

from plone.app.textfield.interfaces import IRichText
from plone.dexterity.interfaces import IDexterityFTI
from plone.dexterity.utils import getAdditionalSchemata
from plone.namedfile.interfaces import INamedField
from plone.restapi.types.utils import get_fieldsets
from plone.rfc822.interfaces import IPrimaryField
from plone.schema.jsonfield import IJSONField
from plone.supermodel.utils import mergedTaggedValueList
from z3c.form.interfaces import HIDDEN_MODE
from z3c.relationfield.interfaces import IRelation, IRelationList
from zope import schema
from zope.component import queryUtility
from zope.i18n import translate
from zope.schema.interfaces import IVocabularyFactory

from interaktiv.translation import _

try:
    from plone.app.multilingual.dx.interfaces import MULTILINGUAL_KEY, ILanguageIndependentField
except ImportError:  # pragma: no cover - plone.app.multilingual is a dependency
    MULTILINGUAL_KEY = None
    ILanguageIndependentField = None

# {portal_type: {field_id: "translate" | "copy"}}:
# the fields that go along for each portal_type, and how
# for a missing portal_type the always and mapped fields are handled
METADATA_SELECTION_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "propertyNames": {"minLength": 1},
            "additionalProperties": {"enum": ["translate", "copy"]},
        },
    }
)

ROLE_ALWAYS = "always"
ROLE_DEFAULT = "default"
ROLE_IMPOSSIBLE = "impossible"

MODE_TRANSLATE = "translate"
MODE_COPY = "copy"
MODE_MAPPING = "mapping"

REASON_ALWAYS = "always"
REASON_PRIMARY = "primary"
REASON_MAPPING = "mapping"
REASON_FIELD_NAME = "field_name"
REASON_LANGUAGE_INDEPENDENT = "language_independent"
REASON_FIELD_TYPE = "field_type"
REASON_REFERENCE = "reference"
REASON_LINK = "link"

# The lists below are the defaults of the settings `excluded_fields`,
# `always_fields`, `copied_fields` and `link_fields`; a site changes them in the
# advanced settings.

# fields that never go along and are not listed: they belong to the object, not to its language
EXCLUDED_FIELDS = (
    "id",
    "language",
    "changeNote",
    "creators",
    "contributors",
    # the page content is "blocks"; its layout goes along with it
    "blocks_layout",
    # a copied calendar UID would make two events one
    "sync_uid",
    # a translation gets its own dates when it is published
    "effective",
    "expires",
)

# the title, the description and the page content always go along, and come first
ALWAYS_FIELDS = ("title", "description", "text", "blocks")

# "Blocks" says little to an editor
FIELD_TITLES = {"blocks": _("Page content")}

# fields of Plone's own types that are taken over though their type says otherwise:
# text that is no prose (an address, a rule), or the search of a collection
COPIED_FIELDS = (
    "contact_email",
    "contact_phone",
    "recurrence",
    "attendees",
    # the name of a catalog index
    "sort_on",
)

# fields of Plone's own types that hold a link: taken over, an internal link
# pointed at the translation of its target
LINK_FIELDS = (
    # the address of a link
    "remoteUrl",
    # the web address of an event
    "event_url",
    # the search of a collection: a path from the portal root is a link to a folder
    "query",
)


class FieldRules(NamedTuple):
    """The lists of field names the rules go by: the add-on's defaults, or a site's own."""

    excluded: Tuple[str, ...] = EXCLUDED_FIELDS
    always: Tuple[str, ...] = ALWAYS_FIELDS
    copied: Tuple[str, ...] = COPIED_FIELDS
    links: Tuple[str, ...] = LINK_FIELDS


DEFAULT_RULES = FieldRules()

# plone.app.multilingual's language folders are no content of their own
EXCLUDED_TYPES = ("LRF", "LIF")

# text that is no prose: an address, a name, a token
_COPIED_TEXT_LINES = (
    schema.interfaces.IURI,
    schema.interfaces.IASCII,
    schema.interfaces.IASCIILine,
    schema.interfaces.IDottedName,
    schema.interfaces.IId,
    schema.interfaces.INativeStringLine,
)
_SCALARS = (
    schema.interfaces.IBool,
    schema.interfaces.IInt,
    schema.interfaces.IFloat,
    schema.interfaces.IDecimal,
    schema.interfaces.IDate,
    schema.interfaces.IDatetime,
    schema.interfaces.ITime,
    schema.interfaces.IChoice,
)


def _provides(field: Any, interfaces: Iterable[Any]) -> bool:
    return any(interface.providedBy(field) for interface in interfaces)


def is_reference(field: Any) -> bool:
    """a relation, or a list of relations"""
    if IRelation.providedBy(field):
        return True

    return IRelationList.providedBy(field) or (
        schema.interfaces.ICollection.providedBy(field) and IRelation.providedBy(getattr(field, "value_type", None))
    )


def holds_texts(field: Any) -> bool:
    """a text, a choice or a collection of them: used to check if mappaple"""
    if is_reference(field) or IRichText.providedBy(field):
        return False
    if _provides(field, (schema.interfaces.ITextLine, schema.interfaces.IText)):
        return True
    if schema.interfaces.IChoice.providedBy(field):
        # a vocabulary of its own tells its values (allow_discussion: True, False);
        # a named one is looked up only with a context, and taken for texts
        vocabulary = getattr(field, "vocabulary", None)
        terms = list(vocabulary) if vocabulary is not None and hasattr(vocabulary, "__iter__") else []
        return all(isinstance(term.value, str) for term in terms)
    if schema.interfaces.ICollection.providedBy(field):
        value_type = getattr(field, "value_type", None)
        return value_type is not None and holds_texts(value_type)

    return False


def mode_by_field_type(field: Any) -> Optional[str]:
    """get mode how to handle field by field type -> ``translate``, ``copy`` or ``None``"""
    # the order matters: an URI is a text line too, a relation a choice
    if is_reference(field):
        # taken over, pointing at the translation of its target
        return MODE_COPY
    if INamedField.providedBy(field):
        return MODE_COPY
    if IRichText.providedBy(field):
        return MODE_TRANSLATE
    if _provides(field, (IJSONField, schema.interfaces.IObject, schema.interfaces.IDict)):
        return None
    if _provides(field, (schema.interfaces.IPassword, schema.interfaces.IBytes, schema.interfaces.IBytesLine)):
        return None
    if _provides(field, _COPIED_TEXT_LINES):
        return MODE_COPY
    if _provides(field, (schema.interfaces.ITextLine, schema.interfaces.IText)):
        return MODE_TRANSLATE
    if _provides(field, _SCALARS):
        return MODE_COPY
    if schema.interfaces.ICollection.providedBy(field):
        # keywords, names, choices: taken over; the mapping translates keywords
        value_type = getattr(field, "value_type", None)
        if value_type is None:
            return None
        return MODE_COPY if mode_by_field_type(value_type) is not None else None

    return None


def classify_field(
    field: Any,
    *,
    primary: bool = False,
    language_independent: bool = False,
    mapped_fields: Iterable[str] = (),
    rules: FieldRules = DEFAULT_RULES,
) -> Tuple[str, Optional[str], str]:
    """The role, the mode and the reason for the mode of one field."""
    name = field.getName()
    # a field named to be copied, or to hold a link, goes along whatever its type
    by_type = MODE_COPY if name in rules.copied or name in rules.links else mode_by_field_type(field)

    if name in rules.always:
        role, role_reason = ROLE_ALWAYS, REASON_ALWAYS
    elif primary and by_type is not None:
        role, role_reason = ROLE_ALWAYS, REASON_PRIMARY
    elif by_type is None:
        return ROLE_IMPOSSIBLE, None, REASON_FIELD_TYPE
    else:
        role, role_reason = ROLE_DEFAULT, REASON_FIELD_TYPE

    if is_reference(field):
        return role, MODE_COPY, REASON_REFERENCE
    if name in rules.links:
        return role, MODE_COPY, REASON_LINK
    if name in mapped_fields:
        return role, MODE_MAPPING, REASON_MAPPING
    if name in rules.copied:
        return role, MODE_COPY, REASON_FIELD_NAME
    if language_independent:
        return role, MODE_COPY, REASON_LANGUAGE_INDEPENDENT
    if role == ROLE_ALWAYS and by_type is None:
        # the page content (blocks) is translated by its extractor
        return role, MODE_TRANSLATE, role_reason

    return role, by_type, REASON_FIELD_TYPE if role == ROLE_DEFAULT else role_reason


def selectable_modes(field: Any, role: str, reason: str) -> List[str]:
    """The modes a site may choose for a field; none where it has no choice."""
    if role != ROLE_DEFAULT:
        return []
    # a field named to be copied is copied for every type: no choice of one type
    if reason in (REASON_REFERENCE, REASON_LINK, REASON_LANGUAGE_INDEPENDENT, REASON_FIELD_NAME):
        return [MODE_COPY]
    if mode_by_field_type(field) == MODE_TRANSLATE:
        return [MODE_TRANSLATE, MODE_COPY]

    return [MODE_COPY]


def chosen_modes(selection: Any, portal_type: str) -> Dict[str, Optional[str]]:
    """``{field_id: mode}`` as chosen for a type; ``None`` for a field chosen without a mode."""
    chosen = (selection or {}).get(portal_type) if isinstance(selection, dict) else None
    if isinstance(chosen, dict):
        return {name: mode for name, mode in chosen.items() if isinstance(name, str)}
    # a list, as it was before the mode could be chosen: the fields go by their kind
    if isinstance(chosen, (list, tuple)):
        return {name: None for name in chosen if isinstance(name, str)}

    return {}


def _language_independent_names(schemata: Iterable[Any]) -> Set[str]:
    if MULTILINGUAL_KEY is None:
        return set()

    names: Set[str] = set()
    for item in schemata:
        for _interface, name, value in mergedTaggedValueList(item, MULTILINGUAL_KEY):
            if value in (True, "true"):
                names.add(name)
    return names


def always_first(fields: List[Dict[str, Any]], always: Iterable[str] = ALWAYS_FIELDS) -> List[Dict[str, Any]]:
    rank = {name: position for position, name in enumerate(always)}
    # sorted() is stable: fields of the same rank keep their order
    return sorted(fields, key=lambda field: rank.get(field["id"], len(rank)))


def selectable_types(context: Any, excluded: Iterable[str] = ()) -> List[Tuple[str, str]]:
    factory = queryUtility(IVocabularyFactory, name="plone.app.vocabularies.ReallyUserFriendlyTypes")
    if factory is None:
        return []

    skipped = set(EXCLUDED_TYPES) | set(excluded)
    return [
        (term.value, term.title)
        for term in factory(context)
        if term.value not in skipped and queryUtility(IDexterityFTI, name=term.value) is not None
    ]


def get_listed_fields(
    portal_type: str,
    context: Any,
    request: Any,
    mapped_fields: Iterable[str] = (),
    rules: FieldRules = DEFAULT_RULES,
) -> List[Dict[str, Any]]:
    """get all fields of type that are not excluded
    mode: how the field should be handled
    mapped: is there a metadata mapping for the field
    """
    fti = queryUtility(IDexterityFTI, name=portal_type)
    if fti is None:
        return []

    base = fti.lookupSchema()
    additional = tuple(getAdditionalSchemata(portal_type=portal_type))
    independent = _language_independent_names((base,) + additional)
    mapped = set(mapped_fields)

    # a reference or a link is never mapped, whatever the mapping holds
    unmappable = (REASON_REFERENCE, REASON_LINK)

    fields: List[Dict[str, Any]] = []
    for fieldset in get_fieldsets(context, request, base, additional):
        for form_field in fieldset["fields"]:
            field = form_field.field
            name = field.getName()
            # an excluded field never goes along; a hidden form field is no choice of the editor's
            if name in rules.excluded or form_field.mode == HIDDEN_MODE:
                continue

            role, mode, reason = classify_field(
                field,
                primary=IPrimaryField.providedBy(field),
                language_independent=name in independent
                or bool(ILanguageIndependentField and ILanguageIndependentField.providedBy(field)),
                rules=rules,
            )
            fields.append(
                {
                    "id": name,
                    "title": translate(FIELD_TITLES.get(name, field.title), context=request),
                    "fieldset": fieldset["id"],
                    "kind": type(field).__name__,
                    "role": role,
                    "mode": mode,
                    "modes": selectable_modes(field, role, reason),
                    "reason": reason,
                    "mapped": name in mapped and role != ROLE_IMPOSSIBLE and reason not in unmappable,
                    "mappable": role == ROLE_DEFAULT and reason == REASON_FIELD_TYPE and holds_texts(field),
                }
            )

    return always_first(fields, rules.always)


def get_handled_fields(
    portal_type: Optional[str],
    selection: Dict[str, Any],
    mapped_fields: Iterable[str] = (),
    rules: FieldRules = DEFAULT_RULES,
) -> Dict[str, str]:
    """{field_id: mode} of fields that are handled by translation"""
    fti = queryUtility(IDexterityFTI, name=portal_type) if portal_type else None
    if fti is None:
        return {name: MODE_TRANSLATE for name in rules.always}

    schemata = (fti.lookupSchema(),) + tuple(getAdditionalSchemata(portal_type=portal_type))
    independent = _language_independent_names(schemata)
    chosen = chosen_modes(selection, portal_type)
    mapped = set(mapped_fields)

    going: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in schemata:
        for name, field in schema.getFieldsInOrder(item):
            if name in seen or name in rules.excluded:
                continue
            seen.add(name)

            role, mode, reason = classify_field(
                field,
                primary=IPrimaryField.providedBy(field),
                language_independent=name in independent
                or bool(ILanguageIndependentField and ILanguageIndependentField.providedBy(field)),
                mapped_fields=mapped,
                rules=rules,
            )
            if role == ROLE_IMPOSSIBLE:
                continue
            if role == ROLE_ALWAYS or name in mapped:
                going.append({"id": name, "mode": mode})
            elif name in chosen:
                # a mode the field cannot take is no choice: the field goes by its kind
                wanted = chosen[name]
                going.append({"id": name, "mode": wanted if wanted in selectable_modes(field, role, reason) else mode})

    # what always goes along, also where no schema names it (blocks without the behavior)
    going.extend({"id": name, "mode": MODE_TRANSLATE} for name in rules.always if name not in seen)

    return {field["id"]: field["mode"] for field in always_first(going, rules.always)}


def get_suggested_modes(
    portal_type: str, field_ids: Iterable[str], rules: FieldRules = DEFAULT_RULES
) -> Dict[str, str]:
    """``{field_id: mode}`` of the given fields as their kind has it, for the fields
    of the type a site has a choice for; the mapping is left out, as in the listing."""
    fti = queryUtility(IDexterityFTI, name=portal_type)
    if fti is None:
        return {}

    schemata = (fti.lookupSchema(),) + tuple(getAdditionalSchemata(portal_type=portal_type))
    independent = _language_independent_names(schemata)
    wanted = list(field_ids)

    modes: Dict[str, str] = {}
    for item in schemata:
        for name, field in schema.getFieldsInOrder(item):
            if name in modes or name not in wanted or name in rules.excluded:
                continue

            role, mode, reason = classify_field(
                field,
                primary=IPrimaryField.providedBy(field),
                language_independent=name in independent
                or bool(ILanguageIndependentField and ILanguageIndependentField.providedBy(field)),
                rules=rules,
            )
            if mode in selectable_modes(field, role, reason):
                modes[name] = mode

    # in the order they were chosen
    return {name: modes[name] for name in wanted if name in modes}
