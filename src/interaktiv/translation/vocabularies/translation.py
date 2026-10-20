from typing import List, Optional

from Acquisition import aq_base
from plone import api
from zope.interface import implementer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm, SimpleVocabulary

from interaktiv.translation.providers.base import PROVIDERS
from interaktiv.translation.settings import settings
from interaktiv.translation.storage import TranslationStorage


@implementer(IVocabularyFactory)
class ProvidersVocabularyFactory:
    def __call__(self, context: Optional[object] = None) -> SimpleVocabulary:
        return SimpleVocabulary(
            [SimpleTerm(value=entry["name"], token=entry["name"], title=entry["title"]) for entry in PROVIDERS.titles()]
        )


def site_languages() -> List[str]:
    try:
        tool = api.portal.get_tool("portal_languages")
    except Exception:  # noqa: BLE001
        return []

    return list(tool.getSupportedLanguages() or [])


@implementer(IVocabularyFactory)
class TargetLanguagesVocabularyFactory:
    def __call__(self, context: Optional[object] = None) -> SimpleVocabulary:
        site = site_languages()
        codes = settings().target_languages or site
        if TranslationStorage(context).multilingual:
            # a translation needs a language root folder of its language
            codes = [code for code in codes if code in site]
        context_language = self._context_language(context)

        return SimpleVocabulary(
            [SimpleTerm(value=code, token=code, title=code) for code in codes if code != context_language]
        )

    @staticmethod
    def _context_language(context: Optional[object]) -> Optional[str]:
        if context is None or not TranslationStorage(context).multilingual:
            return None

        return getattr(aq_base(context), "language", None)
