from typing import List, Optional

from Acquisition import aq_base
from plone import api
from zope.component import queryUtility
from zope.interface import implementer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm, SimpleVocabulary

from interaktiv.translation.helpers.field_selection import EXCLUDED_TYPES
from interaktiv.translation.providers.base import PROVIDERS
from interaktiv.translation.settings import settings
from interaktiv.translation.storage import TranslationStorage


@implementer(IVocabularyFactory)
class ProvidersVocabularyFactory:
    def __call__(self, context: Optional[object] = None) -> SimpleVocabulary:
        return SimpleVocabulary(
            [SimpleTerm(value=entry["name"], token=entry["name"], title=entry["title"]) for entry in PROVIDERS.titles()]
        )


@implementer(IVocabularyFactory)
class ContentTypesVocabularyFactory:
    """The content types an editor adds, as Plone lists them, and the types the settings
    still name though the site no longer has them.

    A stored value must always find its term: plone.restapi cannot show the control
    panel otherwise. A type that went away stays to be chosen off, under its id.
    """

    def __call__(self, context: Optional[object] = None) -> SimpleVocabulary:
        factory = queryUtility(IVocabularyFactory, name="plone.app.vocabularies.ReallyUserFriendlyTypes")
        # plone.app.multilingual's language folders are no content to translate
        terms = [
            SimpleTerm(term.value, term.token, term.title)
            for term in (factory(context) if factory else [])
            if term.value not in EXCLUDED_TYPES
        ]
        known = {term.value for term in terms}
        terms.extend(SimpleTerm(name, name, name) for name in settings().excluded_types if name not in known)

        return SimpleVocabulary(terms)


@implementer(IVocabularyFactory)
class SiteLanguagesVocabularyFactory:
    """The languages of the site, as Plone lists them, and the languages the offered
    target languages still name though the site no longer has them.

    A stored value must always find its term: plone.restapi cannot show the control
    panel otherwise. A language that went away stays to be chosen off, under its code.
    """

    def __call__(self, context: Optional[object] = None) -> SimpleVocabulary:
        factory = queryUtility(IVocabularyFactory, name="plone.app.vocabularies.SupportedContentLanguages")
        terms = [SimpleTerm(term.value, term.token, term.title) for term in factory(context)] if factory else []
        known = {term.value for term in terms}
        terms.extend(SimpleTerm(code, code, code) for code in settings().target_languages if code not in known)

        return SimpleVocabulary(terms)


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
