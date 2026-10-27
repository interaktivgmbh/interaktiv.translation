import copy
from datetime import date
from typing import Any, Dict, List, Optional, TypedDict

from Acquisition import aq_base
from plone.namedfile.interfaces import INamedFile

from interaktiv.translation import logger
from interaktiv.translation.extractors import ExtractorRegistry, FieldExtractor, Share, default_extractors
from interaktiv.translation.providers.base import PROVIDERS, TranslationError, TranslationProvider
from interaktiv.translation.helpers.field_access import MISSING, field_value
from interaktiv.translation.helpers.field_selection import (
    MODE_COPY,
    MODE_MAPPING,
    MODE_TRANSLATE,
    get_handled_fields,
)
from interaktiv.translation.helpers.links import postprocess_links
from interaktiv.translation.settings import settings


# What may travel unchanged: values that mean the same in every language. A
# reference would still point at the source language's content — left out.
COPYABLE_TYPES = (str, int, float, bool, date)
COLLECTION_TYPES = (list, tuple, set, frozenset)


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, (str,) + COLLECTION_TYPES) and not value)


def is_copyable(value: Any) -> bool:
    if INamedFile.providedBy(value):
        return True

    if isinstance(value, dict):
        return all(isinstance(key, str) and is_copyable(item) for key, item in value.items())

    if isinstance(value, COLLECTION_TYPES):
        return all(is_copyable(item) for item in value)

    return value is None or isinstance(value, COPYABLE_TYPES)


def copied_value(value: Any) -> Any:
    if INamedFile.providedBy(value):
        return type(value)(data=value.data, contentType=value.contentType, filename=value.filename)

    return copy.deepcopy(value)


class QueueEntry(TypedDict):
    value: Any
    extractor: Optional[FieldExtractor]
    texts: Optional[List[str]]
    shares: Optional[List[Share]]


def provider() -> TranslationProvider:
    name = settings().provider
    factory = PROVIDERS.get(name)
    if factory is None:
        raise TranslationError(f"No translation provider named '{name}'.", status=503)

    return factory()


class ContentTranslator:
    def __init__(
        self, translation_provider: Optional[TranslationProvider] = None, extractors: Optional[ExtractorRegistry] = None
    ) -> None:
        self.provider = translation_provider or provider()
        self.extractors = extractors or default_extractors(settings().block_text_keys)
        self.link_report: List[Dict[str, Any]] = []
        self.metadata_report: List[Dict[str, Any]] = []
        self.copied_report: List[str] = []

    def get_handled_fields(self, content: Any) -> Dict[str, str]:
        """``{field_id: mode}`` of the fields that go into the translation of this content."""
        current = settings()
        portal_type = getattr(aq_base(content), "portal_type", None)

        return get_handled_fields(portal_type, current.metadata_selection, current.mapped_fields)

    def _handled_fields_in_mode(self, content: Any, mode: str) -> List[str]:
        return [name for name, field_mode in self.get_handled_fields(content).items() if field_mode == mode]

    def fields_of(self, content: Any) -> List[str]:
        """The fields to translate that the content has."""
        return [
            name
            for name in self._handled_fields_in_mode(content, MODE_TRANSLATE)
            if field_value(content, name, MISSING) is not MISSING
        ]

    def create_queue_entry(self, value: Any) -> QueueEntry:
        data = {
            "value": value,
            "extractor": None,
            "texts": None,
            "shares": None,
        }

        extractor = self.extractors.for_value(value)
        if extractor is None:
            return data

        shares = extractor.shares(value)
        texts = extractor.texts(value, shares)
        if not any(text.strip() for text in texts):
            return data

        data["extractor"] = extractor
        data["shares"] = shares
        data["texts"] = texts
        return data

    def postprocessed_value(self, content: Any, field_id: str, value: Any, target_language: str) -> Any:

        # process link values
        value = postprocess_links(
            content, field_id, value, target_language, report=self.link_report
        )

        return value

    def companions_of(self, content: Any, value: Any) -> Dict[str, Any]:
        extractor = self.extractors.for_value(value)
        if extractor is None:
            return {}

        return {
            name: copy.deepcopy(getattr(content, name)) for name in extractor.COMPANION_FIELDS if hasattr(content, name)
        }

    def copied_fields(self, content: Any) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for field_id in self._handled_fields_in_mode(content, MODE_COPY):
            value = field_value(content, field_id)
            if is_empty(value):
                continue
            if not is_copyable(value):
                logger.warning("Not carrying over the field %s: %s is no plain value", field_id, type(value).__name__)
                continue

            result[field_id] = copied_value(value)
            self.copied_report.append(field_id)

        return result

    def mapped_metadata(
        self, content: Any, target_language: str, source_language: Optional[str] = None
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        metadata_mapping = settings().get_metadata_mapping(source_language, target_language)
        for field_id in self._handled_fields_in_mode(content, MODE_MAPPING):
            mapping = metadata_mapping.get(field_id)
            if not mapping:
                # no value of this direction is mapped: the translation keeps what it has
                continue
            source_value = field_value(content, field_id)
            if is_empty(source_value):
                # Nothing to map: the translation keeps what it has.
                continue

            if isinstance(source_value, str):
                result[field_id] = self._mapped_value(field_id, mapping, source_value)
            elif isinstance(source_value, (list, tuple)):
                values = [self._mapped_value(field_id, mapping, value) for value in source_value]
                if isinstance(source_value, tuple):
                    result[field_id] = tuple(values)
                else:
                    result[field_id] = values

        return result

    def _mapped_value(self, field_id: str, mapping: Dict[str, str], value: str) -> str:
        mapped = mapping.get(value)
        self.metadata_report.append({"field": field_id, "before": value, "after": mapped})

        return value if mapped is None else mapped

    def translate(self, content: Any, target_language: str, source_language: Optional[str] = None) -> Dict[str, Any]:
        source = source_language or getattr(content, "language", None) or settings().default_source_language

        self.link_report = []
        self.metadata_report = []
        self.copied_report = []
        result: Dict[str, Any] = {}

        # queue values
        queue = {}
        for field_id in self.fields_of(content):
            value = field_value(content, field_id)
            if value in (None, "", {}, []):
                continue

            try:
                queue[field_id] = self.create_queue_entry(value)
            except Exception as error:  # noqa: BLE001
                logger.warning("Could not translate the field %s: %s", field_id, error)
                continue

        # translate queued values
        texts_by_field = {
            field_id: entry["texts"]
            for field_id, entry in queue.items()
            if entry["texts"]
        }
        translated_texts = self.provider.translate_texts_by_key(texts_by_field, target_language, source)

        # rebuild and postprocess translated values
        for field_id, entry in queue.items():
            translated = entry["value"]

            if entry["extractor"] is not None and field_id in translated_texts:
                translated = entry["extractor"].rebuild(
                    entry["value"], translated_texts[field_id], entry["shares"]
                )

            try:
                translated = self.postprocessed_value(
                    content=content,
                    field_id=field_id,
                    value=translated,
                    target_language=target_language
                )
            except Exception as error:  # noqa: BLE001
                # The translation is already made and paid for; a failed link
                # rewrite may cost the rewritten links, never the content.
                logger.warning("Could not post process the field %s: %s", field_id, error)

            result[field_id] = translated
            # Only once the field itself came back: a companion on its own would
            # describe a value that was never written.
            result.update(self.companions_of(content, entry["value"]))

        # metadata
        result.update(self.copied_fields(content))
        result.update(self.mapped_metadata(content, target_language, source))

        return result
