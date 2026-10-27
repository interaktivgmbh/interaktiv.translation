from typing import Any, List, Optional, Dict

from plone import api
from plone.registry.interfaces import IRegistry
from zope.component import getUtility
from zope.interface.interfaces import ComponentLookupError

from interaktiv.translation.helpers.field_selection import (
    ALWAYS_FIELDS,
    COPIED_FIELDS,
    EXCLUDED_FIELDS,
    FieldRules,
)
from interaktiv.translation.helpers.metadata import parse_metadata_mapping
from interaktiv.translation.registry.translation import (
    DEFAULT_BLOCK_LINK_FIELDS,
    DEFAULT_BLOCK_TEXT_KEYS,
    DEFAULT_EXCLUDED_TYPES,
    ITranslationSettings,
)


class Settings:
    def __init__(self, records=None) -> None:
        self._records = records if records is not None else self._records_from_site()

    @staticmethod
    def _records_from_site():
        try:
            return getUtility(IRegistry).forInterface(ITranslationSettings, check=False)
        except ComponentLookupError:
            return None

    def _get(self, name: str, default: Any = None) -> Any:
        return getattr(self._records, name, default) or default

    @property
    def provider(self) -> str:
        return self._get("provider", "deepl")

    @property
    def api_key(self) -> str:
        return self._get("api_key", "")

    @property
    def api_url(self) -> str:
        return self._get("api_url", "")

    @property
    def default_source_language(self) -> Optional[str]:
        # content that names no language of its own is taken to be in the site's default language
        try:
            return api.portal.get_default_language() or None
        except (ComponentLookupError, KeyError):
            return None

    @property
    def target_languages(self) -> List[str]:
        return list(self._get("target_languages", []))

    @property
    def link_fields(self) -> List[str]:
        return list(self._get("link_fields", []))

    @property
    def block_link_fields(self) -> List[str]:
        return list(self._get("block_link_fields", DEFAULT_BLOCK_LINK_FIELDS))

    @property
    def block_text_keys(self) -> List[str]:
        return list(self._get("block_text_keys", DEFAULT_BLOCK_TEXT_KEYS))

    @property
    def excluded_types(self) -> List[str]:
        # an empty list means "translate every type" and must not fall back to the default
        if self._records is None:
            return list(DEFAULT_EXCLUDED_TYPES)

        return list(getattr(self._records, "excluded_types", None) or [])

    def _field_list(self, name: str, default: tuple) -> List[str]:
        # an emptied list means "none" and must not fall back to the default
        if self._records is None:
            return list(default)

        value = getattr(self._records, name, None)
        return list(default) if value is None else list(value)

    @property
    def excluded_fields(self) -> List[str]:
        return self._field_list("excluded_fields", EXCLUDED_FIELDS)

    @property
    def always_fields(self) -> List[str]:
        return self._field_list("always_fields", ALWAYS_FIELDS)

    @property
    def copied_fields(self) -> List[str]:
        return self._field_list("copied_fields", COPIED_FIELDS)

    @property
    def field_rules(self) -> FieldRules:
        # the lists the field rules go by, as this site has them
        return FieldRules(
            excluded=tuple(self.excluded_fields),
            always=tuple(self.always_fields),
            copied=tuple(self.copied_fields),
        )

    @property
    def metadata_selection(self) -> Dict[str, List[str]]:
        # {portal_type: [field_id, ...]}: the fields chosen per content type
        selection = self._get("metadata_selection", {})
        return selection if isinstance(selection, dict) else {}

    @property
    def mapped_fields(self) -> List[str]:
        # the fields the metadata mapping has values for
        mapping = self._get("metadata_mapping_table", {})
        return [field_id for field_id, rows in mapping.items() if rows] if isinstance(mapping, dict) else []

    def get_metadata_mapping(self, source_language: str, target_language: str) -> Dict[str, Dict[str, str]]:
        # {field_id: {source_value: target_value}}
        return parse_metadata_mapping(self._get("metadata_mapping_table", {}), source_language, target_language)


def settings() -> Settings:
    return Settings()
