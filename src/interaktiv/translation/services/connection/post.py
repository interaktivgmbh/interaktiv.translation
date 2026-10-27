from typing import Any, Dict, Optional

from plone.restapi.deserializer import json_body
from plone.restapi.services import Service
from plone.protect.interfaces import IDisableCSRFProtection
from zope.interface import alsoProvides

from interaktiv.translation.controlpanels.api_key import API_KEY_PLACEHOLDER
from interaktiv.translation.providers.base import PROVIDERS, TranslationError
from interaktiv.translation.settings import settings


def _token(value: Any) -> Optional[str]:
    # a choice comes back from the form as {"token": ..., "title": ...}
    if isinstance(value, dict):
        return value.get("token")

    return value or None


class TranslationConnectionPost(Service):
    """Asks the translation service whether it answers, with the settings as the form
    holds them: what the form leaves out, or the placeholder of the key, is taken as
    stored. A failure is an answer too (``ok: false``), not an error of the request.
    """

    def reply(self) -> Dict[str, Any]:
        # nothing is written: a test may be made before the form is saved
        alsoProvides(self.request, IDisableCSRFProtection)

        data = json_body(self.request) or {}
        current = settings()
        name = _token(data.get("provider")) or current.provider
        api_key = data.get("api_key")
        if api_key in (None, API_KEY_PLACEHOLDER):
            api_key = current.api_key
        api_url = data["api_url"] if "api_url" in data else current.api_url

        factory = PROVIDERS.get(name)
        if factory is None:
            message = f"No translation provider named '{name}'."
            return {"ok": False, "provider": name, "code": "unknown_provider", "message": message}

        provider = factory(api_key=api_key or "", api_url=api_url or "")
        try:
            account = provider.check()
        except TranslationError as error:
            return {"ok": False, "provider": provider.title, "code": error.code, "message": str(error)}

        return {"ok": True, "provider": provider.title, **account}
