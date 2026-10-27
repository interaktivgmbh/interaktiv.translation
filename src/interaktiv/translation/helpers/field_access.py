"""
Helper for getting and setting fields
"""

from typing import Any, Optional

from Acquisition import aq_base
from plone.dexterity.interfaces import IDexterityFTI
from plone.dexterity.utils import iterSchemata
from z3c.form.interfaces import NO_VALUE, IDataManager
from zope.component import getMultiAdapter, queryUtility
from zope.schema.interfaces import IField

from interaktiv.translation import logger

MISSING = object()


def schema_field(content: Any, name: str) -> Optional[Any]:
    portal_type = getattr(aq_base(content), "portal_type", None)
    if not portal_type or queryUtility(IDexterityFTI, name=portal_type) is None:
        return None

    for schema in iterSchemata(content):
        field = schema.get(name)
        if field is not None and IField.providedBy(field):
            return field

    return None


def field_value(content: Any, name: str, default: Any = None) -> Any:
    base = aq_base(content)
    field = schema_field(content, name)
    if field is None:
        return getattr(base, name, default)

    try:
        value = getMultiAdapter((base, field), IDataManager).query(NO_VALUE)
    except TypeError:
        return getattr(base, name, default)

    return default if value is NO_VALUE else value


def set_field_value(content: Any, name: str, value: Any) -> None:
    field = schema_field(content, name)
    if field is None:
        setattr(content, name, value)
        return

    if field.readonly:
        logger.warning("Not writing the read-only field %s", name)
        return

    try:
        getMultiAdapter((content, field), IDataManager).set(value)
    except TypeError:
        setattr(content, name, value)
