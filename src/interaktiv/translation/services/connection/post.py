from typing import Any, Dict, Optional, Tuple

from plone.protect.interfaces import IDisableCSRFProtection
from plone.restapi.deserializer import json_body
from plone.restapi.services import Service
from zope.interface import alsoProvides

from interaktiv.translation.controlpanels.api_key import API_KEY_PLACEHOLDER
from interaktiv.translation.providers.base import PROVIDERS, TranslationError, TranslationProvider
from interaktiv.translation.settings import settings


def _token(value: Any) -> Optional[str]:
    # a choice comes back from the form as {"token": ..., "title": ...}
    if isinstance(value, dict):
        return value.get("token")

    return value or None


class FormProviderService(Service):
    """Asks the translation service with the settings as the form holds them: what
    the form leaves out, or the placeholder of the key, is taken as stored. A failure
    is an answer too (``ok: false``), not an error of the request; nothing is written.

    POST, not GET, although it only asks: the form may hold a new API key, which
    must not go into a URL (access logs, proxies, browser history).
    """

    def form_provider(self) -> Tuple[Optional[TranslationProvider], Optional[Dict[str, Any]]]:
        """The provider of the form, or the answer that says why there is none."""
        # nothing is written: a test may be made before the form is saved
        alsoProvides(self.request, IDisableCSRFProtection)

        data = json_body(self.request) or {}
        current = settings()
        name = _token(data.get("provider")) or current.provider
        api_key = data.get("api_key")
        if api_key in (None, API_KEY_PLACEHOLDER):
            if not current.api_key_status["readable"] and current.api_key_status["stored"]:
                message = "The stored API key cannot be decrypted; enter it again."
                return None, {"ok": False, "provider": name, "code": "key_unreadable", "message": message}
            api_key = current.api_key
        api_url = data["api_url"] if "api_url" in data else current.api_url

        factory = PROVIDERS.get(name)
        if factory is None:
            message = f"No translation provider named '{name}'."
            return None, {"ok": False, "provider": name, "code": "unknown_provider", "message": message}

        return factory(api_key=api_key or "", api_url=api_url or ""), None

    @staticmethod
    def refusal(provider: TranslationProvider, error: TranslationError) -> Dict[str, Any]:
        return {"ok": False, "provider": provider.title, "code": error.code, "message": str(error)}


class TranslationConnectionPost(FormProviderService):
    """Whether the translation service answers, and what it tells of the account."""

    def reply(self) -> Dict[str, Any]:
        provider, refusal = self.form_provider()
        if provider is None:
            return refusal

        try:
            account = provider.check()
        except TranslationError as error:
            return self.refusal(provider, error)

        return {"ok": True, "provider": provider.title, **account}


class TranslationGlossariesPost(FormProviderService):
    """The glossaries of the translation service's account, to choose their IDs from."""

    def reply(self) -> Dict[str, Any]:
        provider, refusal = self.form_provider()
        if provider is None:
            return refusal

        try:
            glossaries = provider.glossaries()
        except TranslationError as error:
            return self.refusal(provider, error)

        return {"ok": True, "provider": provider.title, "glossaries": glossaries}
