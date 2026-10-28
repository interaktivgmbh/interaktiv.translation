from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from interaktiv.translation import logger


class TranslationError(Exception):
    def __init__(self, message: str, status: int = 502, code: str = "error") -> None:
        super().__init__(message)
        self.status = status
        # what went wrong, for a front end to say in its own language
        self.code = code


class TranslationProvider(ABC):
    name: str = ""
    title: str = ""

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None) -> None:
        # a provider without access data of its own ignores them
        pass

    @abstractmethod
    def translate(self, texts: List[str], target_language: str, source_language: Optional[str] = None) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def languages(self) -> List[Dict[str, str]]:
        raise NotImplementedError

    @abstractmethod
    def configured(self) -> bool:
        raise NotImplementedError

    def check(self) -> Dict[str, Any]:
        """Whether the service answers with the access it is given; raises TranslationError if not.

        Answers what it knows of the account: ``plan``, ``character_count``, ``character_limit``.
        """
        if not self.configured():
            raise TranslationError("The translation service is not configured.", status=503, code="not_configured")

        return {}

    def glossaries(self) -> List[Dict[str, Any]]:
        """The glossaries the service offers: ``id``, ``name``, ``source``, ``target``, ``entries``.
        A service without glossaries offers none."""
        return []

    def translate_texts_by_key(
        self, texts_by_key: Dict[str, List[str]], target_language: str, source_language: Optional[str] = None
    ) -> Dict[str, List[str]]:
        # place for provider specific chunking
        return {key: self.translate(texts, target_language, source_language) for key, texts in texts_by_key.items()}


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, Type[TranslationProvider]] = {}

    def register(self, provider: Type[TranslationProvider]) -> None:
        if not provider.name:
            raise ValueError("A translation provider needs a name.")
        if provider.name in self._providers:
            logger.info("Replacing the %s translation provider.", provider.name)
        self._providers[provider.name] = provider

    def get(self, name: str) -> Optional[Type[TranslationProvider]]:
        return self._providers.get(name)

    def names(self) -> List[str]:
        return sorted(self._providers)

    def titles(self) -> List[Dict[str, str]]:
        return [{"name": name, "title": self._providers[name].title or name} for name in self.names()]


PROVIDERS = ProviderRegistry()
