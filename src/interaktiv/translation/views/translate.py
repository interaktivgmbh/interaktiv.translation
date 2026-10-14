from typing import Any, Dict, List

import plone.api as api
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.statusmessages.interfaces import IStatusMessage
from zope.component import getUtility
from zope.schema.interfaces import IVocabularyFactory

from interaktiv.translation import _, logger
from interaktiv.translation.providers.base import TranslationError
from interaktiv.translation.storage import TranslationStorage
from interaktiv.translation.translator import ContentTranslator, provider


class TranslationAvailableView(BrowserView):
    def __call__(self) -> bool:
        storage = TranslationStorage(self.context, self.request)
        if storage.is_working_copy or storage.is_excluded_type:
            return False

        try:
            return provider().configured()
        except TranslationError:
            return False


class TranslateContentView(BrowserView):
    template = ViewPageTemplateFile("templates/translate.pt")

    def __call__(self) -> str:
        if self.request.method == "POST" and self.request.form.get("form.submitted"):
            return self.translate()

        return self.template(self)

    @property
    def configured(self) -> bool:
        return TranslationAvailableView(self.context, self.request)()

    def target_languages(self) -> List[Dict[str, str]]:
        factory = getUtility(IVocabularyFactory, name="interaktiv.translation.TargetLanguages")

        return [
            {"code": term.value, "title": term.title}
            for term in factory(self.context)
            if term.value != api.portal.get_current_language()
        ]

    def fields(self) -> List[str]:
        return ContentTranslator().fields_of(self.context)

    def existing_translations(self) -> List[str]:
        storage = TranslationStorage(self.context, self.request)

        return [
            language["code"]
            for language in self.target_languages()
            if storage.existing_translation(language["code"]) is not None
        ]

    def _message(self, message: Any, kind: str = "info") -> None:
        IStatusMessage(self.request).add(message, type=kind)

    def translate(self) -> str:
        target = (self.request.form.get("target_language") or "").strip()
        if not target:
            self._message(_("Choose a language to translate into."), "warning")

            return self.template(self)

        overwrite = bool(self.request.form.get("overwrite"))
        storage = TranslationStorage(self.context, self.request)

        refusal = storage.refusal(target, overwrite)
        if refusal is not None:
            self._message(refusal, "warning")

            return self.template(self)

        try:
            fields = ContentTranslator().translate(self.context, target)
            stored = storage.store(fields, target, overwrite=overwrite)
        except TranslationError as error:
            self._message(str(error), "error")

            return self.template(self)

        logger.info("Translated %s into %s", "/".join(self.context.getPhysicalPath()), target)
        self._message(_("The translation is ready."))
        self.request.response.redirect(f"{stored.absolute_url()}/edit")

        return ""
