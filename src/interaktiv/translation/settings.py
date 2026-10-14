from typing import Any, List, Optional, Dict

from plone.registry.interfaces import IRegistry
from zope.component import getUtility
from zope.interface.interfaces import ComponentLookupError

from interaktiv.translation.helpers.metadata import parse_metadata_mapping
from interaktiv.translation.registry.translation import (
    DEFAULT_BLOCK_LINK_FIELDS,
    DEFAULT_BLOCK_TEXT_KEYS,
    DEFAULT_COPY_FIELDS,
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
        return self._get("default_source_language") or None

    @property
    def target_languages(self) -> List[str]:
        return list(self._get("target_languages", []))

    @property
    def translate_fields(self) -> List[str]:
        return list(self._get("translate_fields", ["title", "description", "text", "blocks"]))

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

    @property
    def copy_fields(self) -> List[str]:
        # an empty list means "copy nothing" and must not fall back to the default
        if self._records is None:
            return list(DEFAULT_COPY_FIELDS)

        return list(getattr(self._records, "copy_fields", None) or [])

    def get_metadata_mapping(self, source_language: str, target_language: str) -> Dict[str, Dict[str, str]]:
        # {field_id: {source_value: target_value}}
        return parse_metadata_mapping(
            self._get("metadata_mapping_table", ""), source_language, target_language
        )


def settings() -> Settings:
    return Settings()
