from unittest import TestCase, mock

from interaktiv.translation.providers.base import TranslationError
from interaktiv.translation.providers.deepl import DeepLProvider
from interaktiv.translation.settings import Settings
from interaktiv.translation.tests.test_providers import _response

TRANSLATED = {"translations": [{"text": "Hello"}]}


class TestGlossaryId(TestCase):
    def _settings(self, glossaries, default="de"):
        settings = Settings(records=mock.Mock(glossary_ids=glossaries))
        patcher = mock.patch.object(Settings, "default_source_language", new_callable=mock.PropertyMock)
        patcher.start().return_value = default
        self.addCleanup(patcher.stop)

        return settings

    def test_glossary_id__names_the_glossary_of_the_direction_from_the_default_language(self):
        settings = self._settings({"en": "glossary-a", "fr": "glossary-b"})

        self.assertEqual(settings.glossary_id("de", "en"), "glossary-a")
        self.assertEqual(settings.glossary_id("DE", "FR"), "glossary-b")

    def test_glossary_id__names_none_from_another_language(self):
        settings = self._settings({"en": "glossary-a"})

        self.assertIsNone(settings.glossary_id("fr", "en"))
        self.assertIsNone(settings.glossary_id(None, "en"))

    def test_glossary_id__names_none_for_a_direction_without_one(self):
        settings = self._settings({"en": " "})

        self.assertIsNone(settings.glossary_id("de", "en"))
        self.assertIsNone(settings.glossary_id("de", "fr"))


class TestDeepLGlossary(TestCase):
    def setUp(self):
        self.settings = mock.Mock()
        self.settings.glossary_id.side_effect = lambda source, target: "glossary-a" if source == "de" else None
        patcher = mock.patch("interaktiv.translation.providers.deepl.settings", return_value=self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_translate__sends_the_glossary_of_the_direction(self):
        # do it
        with mock.patch("requests.post", return_value=_response(payload=TRANSLATED)) as post:
            DeepLProvider(api_key="abc").translate(["Hallo"], "en", "de")

        # postcondition — with the source language DeepL needs for it
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["glossary_id"], "glossary-a")
        self.assertEqual(payload["source_lang"], "DE")

    def test_translate__sends_no_glossary_from_another_language(self):
        # do it
        with mock.patch("requests.post", return_value=_response(payload=TRANSLATED)) as post:
            DeepLProvider(api_key="abc").translate(["Hello"], "de", "en")

        # postcondition
        self.assertNotIn("glossary_id", post.call_args.kwargs["json"])

    def test_translate__goes_on_without_a_glossary_deepl_refuses(self):
        # setup — the glossary unknown, the translation without it fine
        answers = [_response(status=404, payload={}), _response(payload=TRANSLATED)]

        # do it
        with mock.patch("requests.post", side_effect=answers) as post:
            result = DeepLProvider(api_key="abc").translate(["Hallo"], "en", "de")

        # postcondition
        self.assertEqual(result, ["Hello"])
        self.assertIn("glossary_id", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("glossary_id", post.call_args_list[1].kwargs["json"])

    def test_translate__fails_for_a_refused_key_glossary_or_not(self):
        # do it, postcondition — not a matter of the glossary: no second try
        with mock.patch("requests.post", return_value=_response(status=403, payload={})) as post:
            with self.assertRaises(TranslationError):
                DeepLProvider(api_key="abc").translate(["Hallo"], "en", "de")
        self.assertEqual(post.call_count, 1)
