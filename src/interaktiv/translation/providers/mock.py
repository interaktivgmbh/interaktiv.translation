import re

from typing import Dict, List, Optional

from interaktiv.translation.providers.base import PROVIDERS, TranslationProvider

# regex for tags and entities
MARKUP = re.compile(r"(<[^>]+>|&[a-zA-Z]+;|&#\d+;)")


class MockProvider(TranslationProvider):
    name = "mock"
    title = "Mock (uppercases instead of translating)"

    def configured(self) -> bool:
        return True

    def translate(self, texts: List[str], target_language: str, source_language: Optional[str] = None) -> List[str]:
        return [self._shout(text) for text in texts]

    def languages(self) -> List[Dict[str, str]]:
        return [
            {"code": "DE", "title": "Deutsch"},
            {"code": "EN", "title": "English"},
        ]

    @staticmethod
    def _shout(text: str) -> str:
        parts = MARKUP.split(text)
        parts[0::2] = [part.upper() for part in parts[0::2]]

        return "".join(parts)


PROVIDERS.register(MockProvider)
