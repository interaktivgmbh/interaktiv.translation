from typing import Any, Dict

from plone.restapi.services import Service

from interaktiv.translation.settings import settings


class TranslationConnectionGet(Service):
    """How the stored API key is kept, never the key, and without asking the service:
    ``stored``, ``encryption`` (``environment``, ``site`` or ``none``), ``readable``."""

    def reply(self) -> Dict[str, Any]:
        return {"api_key": settings().api_key_status}
