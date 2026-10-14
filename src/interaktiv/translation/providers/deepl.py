import random
import time
from typing import Dict, List, Optional, Tuple

import requests

from interaktiv.translation import logger
from interaktiv.translation.providers.base import PROVIDERS, TranslationError, TranslationProvider
from interaktiv.translation.settings import settings

FREE_API = "https://api-free.deepl.com/v2"
PRO_API = "https://api.deepl.com/v2"
FREE_KEY_SUFFIX = ":fx"

REQUEST_TIMEOUT = 20

# Retry rate-limited request (429)
# Retries have a growing delay plus jitter
RETRY_ATTEMPTS = 4
RETRY_BASE_SECONDS = 1.0

# DeepL payload restrictions
MAX_TEXTS_PER_REQUEST = 50
MAX_REQUEST_BYTES = 100_000


class DeepLProvider(TranslationProvider):
    name = "deepl"
    title = "DeepL"

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None) -> None:
        self._api_key = settings().api_key if api_key is None else api_key
        self._api_url = settings().api_url if api_url is None else api_url

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def api_url(self) -> str:
        if self._api_url:
            return self._api_url.rstrip("/")

        return FREE_API if self._api_key.endswith(FREE_KEY_SUFFIX) else PRO_API

    def configured(self) -> bool:
        return bool(self._api_key)

    def _post(self, path: str, payload: Dict) -> Dict:
        if not self.configured():
            raise TranslationError("No DeepL API key is configured for this site.", status=503)

        response = None
        for attempt in range(RETRY_ATTEMPTS):
            if attempt:
                delay = RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.info("DeepL is rate-limiting; retry %s/%s in %.1fs.", attempt, RETRY_ATTEMPTS - 1, delay)
                time.sleep(delay)

            try:
                response = requests.post(
                    f"{self.api_url}{path}",
                    headers={"Authorization": f"DeepL-Auth-Key {self._api_key}"},
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )
            except requests.RequestException as error:
                logger.warning("DeepL is not reachable: %s", error)
                raise TranslationError("DeepL is not reachable.") from error

            if response.status_code != 429:
                break

        if response.status_code == 403:
            raise TranslationError("DeepL refused the API key.", status=403)
        if response.status_code == 456:
            raise TranslationError("The DeepL quota for this key is used up.", status=429)
        if response.status_code == 429:
            raise TranslationError("DeepL is rate-limiting this site.", status=429)
        if not response.ok:
            logger.warning("DeepL answered %s: %s", response.status_code, response.text[:200])
            raise TranslationError(f"DeepL answered {response.status_code}.")

        return response.json()

    def translate(self, texts: List[str], target_language: str, source_language: Optional[str] = None) -> List[str]:
        sendable = [(index, text) for index, text in enumerate(texts) if text.strip()]
        if not sendable:
            return list(texts)

        source = self.normalise_language(source_language, source=True) if source_language else ""
        # if source equals target DeepL needs to detect the real language per text.
        if source == self.normalise_language(target_language, source=True):
            source = ""

        result = list(texts)
        for chunk in self._chunked(sendable):
            payload = {
                "text": [text for _index, text in chunk],
                "target_lang": self.normalise_language(target_language),
                "tag_handling": "html",
            }
            if source:
                payload["source_lang"] = source

            data = self._post("/translate", payload)
            translated = [entry.get("text", "") for entry in data.get("translations", [])]
            if len(translated) != len(chunk):
                raise TranslationError("DeepL answered with a different number of texts.")

            for (index, _text), answer in zip(chunk, translated):
                result[index] = answer

        return result

    @staticmethod
    def _chunked(sendable: List[Tuple[int, str]]) -> List[List[Tuple[int, str]]]:
        # chunk texts according to payload restrictions
        # a single text that is larger than the size limit will raise an error and break the translation process
        chunks: List[List[Tuple[int, str]]] = []
        chunk: List[Tuple[int, str]] = []
        chunk_bytes = 0
        for index, text in sendable:
            size = len(text.encode("utf-8"))
            if size > MAX_REQUEST_BYTES:
                raise TranslationError("One text alone is more than DeepL takes in one request.", status=413)
            if chunk and (len(chunk) == MAX_TEXTS_PER_REQUEST or chunk_bytes + size > MAX_REQUEST_BYTES):
                chunks.append(chunk)
                chunk = []
                chunk_bytes = 0
            chunk.append((index, text))
            chunk_bytes += size
        chunks.append(chunk)

        return chunks

    def translate_texts_by_key(
        self, texts_by_key: Dict[str, List[str]], target_language: str, source_language: Optional[str] = None
    ) -> Dict[str, List[str]]:
        # merge texts to one flat list
        flat: List[str] = []
        counts: Dict[str, int] = {}
        for key, texts in texts_by_key.items():
            counts[key] = len(texts)
            flat.extend(texts)

        translated = self.translate(flat, target_language, source_language)

        result: Dict[str, List[str]] = {}
        consumed = 0
        for key, count in counts.items():
            result[key] = translated[consumed: consumed + count]
            consumed += count

        return result

    def languages(self) -> List[Dict[str, str]]:
        if not self.configured():
            return []

        try:
            data = self._post("/languages", {"type": "target"})
        except TranslationError:
            return []

        return [
            {"code": entry["language"], "title": entry.get("name", entry["language"])}
            for entry in data
            if entry.get("language")
        ]

    @staticmethod
    def normalise_language(language: str, source: bool = False) -> str:
        code = (language or "").replace("_", "-").upper()
        if source:
            return code.split("-")[0]

        return code


PROVIDERS.register(DeepLProvider)
