from typing import Any, Dict, Optional

from interaktiv.translation import logger
from interaktiv.translation.providers.base import TranslationError
from interaktiv.translation.storage import (
    EXCLUDED_TYPE_REFUSAL,
    WORKING_COPY_REFUSAL,
    TranslationStorage,
)
from interaktiv.translation.translator import ContentTranslator
from plone.protect.interfaces import IDisableCSRFProtection
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service
from zExceptions import BadRequest
from zope.interface import alsoProvides


class TranslatePost(Service):
    def reply(self) -> Dict[str, Any]:
        body = json_body(self.request)
        target = (body.get("target_language") or "").strip()
        if not target:
            raise BadRequest("target_language is required.")

        source = body.get("source_language") or None
        translator = ContentTranslator()

        try:
            if "text" in body:
                return self._reply_text(translator, body["text"], target, source)

            return self._reply_content(translator, body, target, source)
        except TranslationError as error:
            self.request.response.setStatus(error.status)

            return {"type": "TranslationError", "message": str(error)}

    def _reply_text(self, translator, texts, target: str, source) -> Dict[str, Any]:
        one = isinstance(texts, str)
        translated = translator.provider.translate([texts] if one else list(texts), target, source)

        return {"target_language": target, "text": translated[0] if one else translated}

    def _reply_content(self, translator, body: Dict, target: str, source: Optional[str]) -> Dict[str, Any]:
        overwrite = bool(body.get("overwrite"))

        storage = TranslationStorage(self.context, self.request)
        if storage.is_excluded_type:
            # Refused for a preview too: it would cost the provider all the same.
            raise TranslationError(EXCLUDED_TYPE_REFUSAL, status=409)

        if storage.is_working_copy:
            raise TranslationError(WORKING_COPY_REFUSAL, status=400)

        if body.get("save"):
            # Refused is refused — but before the provider was paid, not after.
            refusal = storage.refusal(target, overwrite)
            if refusal is not None:
                raise TranslationError(refusal, status=409)

        fields = translator.translate(self.context, target, source)
        result: Dict[str, Any] = {
            "target_language": target,
            "fields": {
                name: value if isinstance(value, (str, dict, list, tuple)) else str(value)
                for name, value in fields.items()
            },
        }

        if body.get("save"):
            # plone.protect guards writes made during a request it cannot tie to
            # a form token, and a REST client has none: without this the store
            # below runs, answers `saved`, and is then rolled back unwritten.
            alsoProvides(self.request, IDisableCSRFProtection)
            stored = storage.store(fields, target, overwrite=overwrite, source_language=source)
            result["saved"] = True
            result["@id"] = stored.absolute_url()
            result["report"] = {
                "source_language": source or None,
                "target_language": target,
                "fields": sorted(fields),
                "stored_as": storage.stored_as,
                "created": storage.created,
                "title": stored.title,
                "@id": stored.absolute_url(),
                "links": translator.link_report,
                "metadata": translator.metadata_report,
                "copied": translator.copied_report,
            }
            logger.info(
                "Translated %s into %s as %s",
                "/".join(self.context.getPhysicalPath()),
                target,
                "/".join(stored.getPhysicalPath()),
            )

        return result
