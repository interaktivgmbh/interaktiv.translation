"""The short name of a machine translation, chosen while it is created."""

from typing import Any

from plone.app.multilingual.factory import DefaultTranslationIdChooser
from plone.i18n.normalizer.interfaces import IURLNormalizer
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility
from zope.container.interfaces import INameChooser
from zope.globalrequest import getRequest

# the translated title of the translation being created, on the request
TRANSLATED_TITLE_KEY = "interaktiv.translation.translated_title"


class TranslatedTitleIdChooser(DefaultTranslationIdChooser):
    """Names a machine translation after its translated title, as Plone names
    content created by hand; anything else plone.app.multilingual creates keeps
    its own way (the id of the original)."""

    def __call__(self, parent: Any, language: str) -> str:
        request = getRequest()
        annotations = IAnnotations(request, None) if request is not None else None
        title = annotations.get(TRANSLATED_TITLE_KEY) if annotations is not None else None

        if isinstance(title, str) and title.strip():
            # By the rules of the target language, as for content created by
            # hand in its folder; the name chooser alone would take those of
            # the request, which is on the source.
            name = getUtility(IURLNormalizer).normalize(title, locale=language)
            if name:
                return INameChooser(parent).chooseName(name, self.context)

        return super().__call__(parent, language)
