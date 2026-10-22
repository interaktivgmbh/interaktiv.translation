import csv
import re
from typing import Dict, List, Optional, Tuple

from plone import api
from plone.registry.interfaces import IRegistry
from Products.GenericSetup.tool import SetupTool
from zope.component import getUtility

from interaktiv.translation import logger
from interaktiv.translation.registry.translation import ITranslationSettings

MAPPING_RECORD = f"{ITranslationSettings.__identifier__}.metadata_mapping_table"

# the CSV format of 1.0.0a1, kept here so this step does not depend on the current helpers
SECTION_RE = re.compile(r"^\[(?P<field_id>[^\]]+)\]$")
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})?$")


# noinspection PyUnusedLocal
def upgrade(site_setup: Optional[SetupTool] = None) -> None:
    registry = getUtility(IRegistry)
    old_value = registry.records[MAPPING_RECORD].value if MAPPING_RECORD in registry.records else None

    # the registry step turns the record into the JSON field
    setup_tool = site_setup or api.portal.get_tool("portal_setup")
    setup_tool.runImportStepFromProfile(
        "profile-interaktiv.translation:default", "plone.app.registry", run_dependencies=False
    )

    if isinstance(old_value, dict):
        registry[MAPPING_RECORD] = old_value
        return

    mapping = csv_to_mapping(old_value or "")
    registry[MAPPING_RECORD] = mapping
    logger.info(
        "Metadata mapping as JSON: %s fields, %s rows taken over.",
        len(mapping),
        sum(len(rows) for rows in mapping.values()),
    )


def csv_to_mapping(table: str) -> Dict[str, List[Dict[str, str]]]:
    mapping: Dict[str, List[Dict[str, str]]] = {}
    for field_id, lines in _sections(table):
        rows = _rows(field_id, lines)
        if rows:
            mapping.setdefault(field_id, []).extend(rows)

    return mapping


def _sections(table: str) -> List[Tuple[str, List[str]]]:
    sections: List[Tuple[str, List[str]]] = []
    field_id = ""
    lines: List[str] = []
    for raw_line in table.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = SECTION_RE.match(line)
        if match:
            if field_id:
                sections.append((field_id, lines))
            field_id = match.group("field_id").strip()
            lines = []
        elif field_id:
            lines.append(line)
    if field_id:
        sections.append((field_id, lines))

    return sections


def _rows(field_id: str, lines: List[str]) -> List[Dict[str, str]]:
    if not lines:
        return []

    delimiter = ";" if ";" in lines[0] else ","
    table = [[cell.strip() for cell in row] for row in csv.reader(lines, delimiter=delimiter)]
    # a column that is no language code, or a language named twice, is dropped
    columns: List[Optional[str]] = []
    seen = set()
    for language in table[0]:
        if LANGUAGE_RE.match(language) and language.lower() not in seen:
            seen.add(language.lower())
            columns.append(language)
        else:
            logger.warning("Metadata mapping as JSON: column '%s' of [%s] dropped.", language, field_id)
            columns.append(None)

    rows: List[Dict[str, str]] = []
    for cells in table[1:]:
        # an empty cell is left out: the translation keeps the source value
        row = {language: cell for language, cell in zip(columns, cells) if language and cell}
        if row:
            rows.append(row)

    return rows
