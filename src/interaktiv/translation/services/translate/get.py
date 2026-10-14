from typing import Any, Dict

from Acquisition import aq_base
from interaktiv.translation.providers.base import TranslationError
from interaktiv.translation.storage import TranslationStorage
from interaktiv.translation.storage import translation_status
from interaktiv.translation.translator import provider
from plone.restapi.services import Service
from zope.component import getUtility
from zope.schema.interfaces import IVocabularyFactory


class TranslateGet(Service):
    def reply(self) -> Dict[str, Any]:
        try:
            current = provider()
        except TranslationError:
            current = None

        factory = getUtility(IVocabularyFactory, name="interaktiv.translation.TargetLanguages")
        terms = list(factory(self.context))

        storage = TranslationStorage(self.context, self.request)
        translations: Dict[str, Dict[str, Any]] = {}

        for term in terms:
            sibling = storage.existing_translation(term.value)
            if sibling is not None and aq_base(sibling) is not aq_base(self.context):
                translations[term.value] = self._language_entry(sibling, storage)
            else:
                translations[term.value] = {"url": None, "status": None, "working_copy": None}

        own_language = getattr(aq_base(self.context), "language", None)
        if own_language:
            translations[own_language] = self._language_entry(self.context, storage)

        baseline = storage.baseline()

        return {
            "configured": bool(current and current.configured()),
            "provider": current.name if current else None,
            "target_languages": [{"code": term.value, "title": term.title} for term in terms],
            "working_copies_enabled": storage.uses_working_copies(self.context),
            "translations": translations,
            "is_working_copy": baseline is not None,
            "translatable": not storage.is_excluded_type,
            "baseline_url": baseline.absolute_url() if baseline is not None else None,
        }

    @staticmethod
    def _language_entry(content: Any, storage: TranslationStorage) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "url": content.absolute_url(),
            "status": translation_status(content),
            "working_copy": None,
        }
        working_copy = storage.working_copy_of(content)
        if working_copy is not None:
            entry["working_copy"] = {
                "url": working_copy.absolute_url(),
                "status": translation_status(working_copy),
            }

        return entry
