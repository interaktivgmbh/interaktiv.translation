import json
import re
from typing import Any, Dict, List

from zope.globalrequest import getRequest
from zope.i18n import translate
from zope.interface import Invalid

from interaktiv.translation import _

# regex for language code like "de", "en-gb" or "pt_BR"
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})?$")

# {field_id: [{language: value}, ...]} — the structure, checked by the JSONField itself
METADATA_MAPPING_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "additionalProperties": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
    }
)


def validate_metadata_mapping(mapping: Dict[str, List[Dict[str, str]]]) -> bool:
    # the field runs this before its JSON schema: a value of the wrong shape is left to the schema
    if not isinstance(mapping, dict):
        return True

    problems: List[str] = []
    for field_id, rows in mapping.items():
        if not field_id.strip():
            problems.append(_("a mapped field needs an id"))
            continue

        if not isinstance(rows, list):
            continue

        for number, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue

            for language in row:
                if not LANGUAGE_RE.match(language.strip()):
                    problems.append(
                        _(
                            "${field}, row ${number}: '${language}' is no language code",
                            mapping={"field": field_id, "number": number, "language": language},
                        )
                    )
            if len({language.strip().lower() for language in row}) != len(row):
                problems.append(
                    _(
                        "${field}, row ${number}: a language appears twice",
                        mapping={"field": field_id, "number": number},
                    )
                )

    if problems:
        request = getRequest()
        details = "; ".join(translate(problem, context=request) for problem in problems)

        raise Invalid(translate(_("The metadata mapping has problems: "), context=request) + details)

    return True


def parse_metadata_mapping(mapping: Any, source_language: str, target_language: str) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    if not source_language or not target_language or not isinstance(mapping, dict):
        return result

    source = source_language.lower()
    target = target_language.lower()
    for field_id, rows in mapping.items():
        pairs: Dict[str, str] = {}
        for row in rows or []:
            values = {language.strip().lower(): (value or "").strip() for language, value in row.items()}
            source_value = values.get(source)
            target_value = values.get(target)
            # an empty or missing value: the translation keeps the source value
            if source_value and target_value:
                pairs[source_value] = target_value
        if pairs:
            result.setdefault(field_id.strip(), {}).update(pairs)

    return result
