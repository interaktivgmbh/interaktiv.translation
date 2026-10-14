import csv
import re
from typing import Dict, List, Tuple

from zope.globalrequest import getRequest
from zope.i18n import translate
from zope.interface import Invalid

from interaktiv.translation import _

# regex for field_id like "[metadatafield_id]"
SECTION_RE = re.compile(r"^\[(?P<field_id>[^\]]+)\]$")

# regex for language code like "de", "en-gb" or "pt_BR"
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})?$")


def validate_metadata_mapping_table(table: str) -> bool:
    problems: List[str] = []
    in_section = False
    header_cells = 0
    delimiter = ","
    for number, raw_line in enumerate((table or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if SECTION_RE.match(line):
            in_section = True
            header_cells = 0
            continue

        if not in_section:
            problems.append(_("line ${number}: belongs to no [field] section", mapping={"number": number}))
            continue

        if not header_cells:
            delimiter = ";" if ";" in line else ","
            cells = [cell.strip() for cell in next(csv.reader([line], delimiter=delimiter))]
            header_cells = len(cells)
            if header_cells < 2:
                problems.append(_("line ${number}: a mapping needs at least two languages", mapping={"number": number}))
            for cell in cells:
                if not LANGUAGE_RE.match(cell):
                    problems.append(
                        _("line ${number}: '${cell}' is no language code", mapping={"number": number, "cell": cell})
                    )
            if len({cell.lower() for cell in cells}) != len(cells):
                problems.append(_("line ${number}: a language appears twice", mapping={"number": number}))
            continue

        row = next(csv.reader([line], delimiter=delimiter))
        if len(row) != header_cells:
            problems.append(
                _(
                    "line ${number}: ${cells} cells, but the header names ${languages} languages",
                    mapping={"number": number, "cells": len(row), "languages": header_cells},
                )
            )

    if problems:
        request = getRequest()
        details = "; ".join(translate(problem, context=request) for problem in problems)

        raise Invalid(translate(_("The mapping table has problems: "), context=request) + details)

    return True


def parse_metadata_mapping(table: str, source_language: str, target_language: str) -> Dict[str, Dict[str, str]]:
    mapping: Dict[str, Dict[str, str]] = {}
    if not source_language or not target_language:
        return mapping

    for field_id, lines in _sections(table):
        pairs = _pairs(lines, source_language, target_language)
        if pairs:
            mapping.setdefault(field_id, {}).update(pairs)

    return mapping


def _sections(table: str) -> List[Tuple[str, List[str]]]:
    # start with first [field_id] marker
    sections: List[Tuple[str, List[str]]] = []
    field_id = ""
    lines: List[str] = []
    for raw_line in (table or "").splitlines():
        line = raw_line.strip()

        # ignore empty lines
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


def _pairs(lines: List[str], source_language: str, target_language: str) -> Dict[str, str]:
    if not lines:
        return {}

    delimiter = ";" if ";" in lines[0] else ","
    rows = [[cell.strip() for cell in row] for row in csv.reader(lines, delimiter=delimiter)]

    # get language indexes from header row
    header = [code.lower() for code in rows[0]]
    try:
        source_index = header.index(source_language.lower())
        target_index = header.index(target_language.lower())
    except ValueError:
        return {}

    pairs: Dict[str, str] = {}
    for row in rows[1:]:
        if len(row) <= max(source_index, target_index):
            continue
        source_value = row[source_index]
        target_value = row[target_index]
        if source_value and target_value:
            pairs[source_value] = target_value

    return pairs
