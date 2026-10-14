from unittest import TestCase, mock

from interaktiv.translation.providers.base import (
    PROVIDERS,
    ProviderRegistry,
    TranslationError,
    TranslationProvider,
)
from interaktiv.translation.providers.mock import MockProvider
from interaktiv.translation.providers.deepl import (
    FREE_API,
    MAX_REQUEST_BYTES,
    MAX_TEXTS_PER_REQUEST,
    PRO_API,
    RETRY_ATTEMPTS,
    DeepLProvider,
)


class Fake(TranslationProvider):
    name = "fake"
    title = "Fake"

    def translate(self, texts, target_language, source_language=None):
        return [f"{text}!" for text in texts]

    def languages(self):
        return []

    def configured(self):
        return True


class TestProviderRegistry(TestCase):
    def test_register__serves_the_provider_under_its_name(self):
        # setup
        registry = ProviderRegistry()

        # do it
        registry.register(Fake)

        # postcondition
        self.assertIs(registry.get("fake"), Fake)
        self.assertEqual(registry.names(), ["fake"])

    def test_register__refuses_a_provider_without_a_name(self):
        # setup
        class Nameless(Fake):
            name = ""

        # do it / postcondition
        with self.assertRaises(ValueError):
            ProviderRegistry().register(Nameless)

    def test_get__answers_nothing_for_an_unknown_provider(self):
        self.assertIsNone(ProviderRegistry().get("nope"))

    def test_titles__pairs_every_name_with_something_readable(self):
        # setup
        registry = ProviderRegistry()
        registry.register(Fake)

        # do it / postcondition
        self.assertEqual(registry.titles(), [{"name": "fake", "title": "Fake"}])


def _response(status=200, payload=None, text=""):
    response = mock.Mock()
    response.status_code = status
    response.ok = 200 <= status < 300
    response.json.return_value = payload or {}
    response.text = text

    return response


class TestDeepLProvider(TestCase):
    def test_api_url__free_key_goes_to_the_free_host(self):
        self.assertEqual(DeepLProvider(api_key="abc:fx").api_url, FREE_API)

    def test_api_url__any_other_key_goes_to_the_pro_host(self):
        self.assertEqual(DeepLProvider(api_key="abc").api_url, PRO_API)

    def test_api_url__an_explicit_url_wins(self):
        provider = DeepLProvider(api_key="abc:fx", api_url="http://proxy.test/v2/")
        self.assertEqual(provider.api_url, "http://proxy.test/v2")

    def test_configured__is_the_key_and_nothing_else(self):
        self.assertFalse(DeepLProvider(api_key="").configured())
        self.assertTrue(DeepLProvider(api_key="abc").configured())

    def test_translate__refuses_before_asking_when_unconfigured(self):
        # setup
        provider = DeepLProvider(api_key="")

        # do it / postcondition — a 503 the caller can act on, no request made
        with mock.patch("requests.post") as post:
            with self.assertRaises(TranslationError) as caught:
                provider.translate(["Hallo"], "EN")
        self.assertEqual(caught.exception.status, 503)
        post.assert_not_called()

    def test_translate__sends_html_handling_and_the_normalised_language(self):
        # setup
        provider = DeepLProvider(api_key="abc:fx")

        # do it
        with mock.patch(
            "requests.post",
            return_value=_response(payload={"translations": [{"text": "Hello"}]}),
        ) as post:
            result = provider.translate(["Hallo"], "en-gb", "de")

        # postcondition
        self.assertEqual(result, ["Hello"])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["target_lang"], "EN-GB")
        # DeepL refuses a regional code as a source.
        self.assertEqual(payload["source_lang"], "DE")
        self.assertEqual(payload["tag_handling"], "html")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "DeepL-Auth-Key abc:fx")

    def test_translate__leaves_the_source_out_when_it_only_repeats_the_target(self):
        # setup — an in-place site whose `language` field mirrors the target:
        # no information, DeepL should detect the real language itself
        provider = DeepLProvider(api_key="abc")

        # do it
        with mock.patch(
            "requests.post",
            return_value=_response(payload={"translations": [{"text": "Hello"}]}),
        ) as post:
            provider.translate(["Hallo"], "en-gb", "en")

        # postcondition
        self.assertNotIn("source_lang", post.call_args.kwargs["json"])

    def test_translate__keeps_empty_texts_in_place_without_sending_them(self):
        # setup
        provider = DeepLProvider(api_key="abc")

        # do it
        with mock.patch(
            "requests.post",
            return_value=_response(payload={"translations": [{"text": "Hello"}]}),
        ) as post:
            result = provider.translate(["", "Hallo", "   "], "EN")

        # postcondition — one answer per input, and only one text billed
        self.assertEqual(result, ["", "Hello", "   "])
        self.assertEqual(post.call_args.kwargs["json"]["text"], ["Hallo"])

    def test_translate__does_not_call_at_all_when_there_is_nothing_to_say(self):
        with mock.patch("requests.post") as post:
            result = DeepLProvider(api_key="abc").translate(["", " "], "EN")

        self.assertEqual(result, ["", " "])
        post.assert_not_called()

    def test_translate__refuses_a_single_text_over_the_budget(self):
        # setup
        provider = DeepLProvider(api_key="abc")

        # do it / postcondition — splitting one text would cut through markup
        # or sentences, so it is refused instead of sent
        with mock.patch("requests.post") as post:
            with self.assertRaises(TranslationError) as caught:
                provider.translate(["x" * (MAX_REQUEST_BYTES + 1)], "EN")
        self.assertEqual(caught.exception.status, 413)
        post.assert_not_called()

    def test_translate__splits_more_texts_than_deepl_takes_into_two_requests(self):
        # setup — one text more than a single request may carry
        provider = DeepLProvider(api_key="abc")
        texts = [f"text {index}" for index in range(MAX_TEXTS_PER_REQUEST + 1)]
        first = _response(
            payload={"translations": [{"text": f"TEXT {index}"} for index in range(MAX_TEXTS_PER_REQUEST)]}
        )
        second = _response(payload={"translations": [{"text": f"TEXT {MAX_TEXTS_PER_REQUEST}"}]})

        # do it
        with mock.patch("requests.post", side_effect=[first, second]) as post:
            result = provider.translate(texts, "EN")

        # postcondition — two requests, every answer back in its place
        self.assertEqual(post.call_count, 2)
        self.assertEqual(len(post.call_args_list[0].kwargs["json"]["text"]), MAX_TEXTS_PER_REQUEST)
        self.assertEqual(post.call_args_list[1].kwargs["json"]["text"], [f"text {MAX_TEXTS_PER_REQUEST}"])
        self.assertEqual(result[0], "TEXT 0")
        self.assertEqual(result[-1], f"TEXT {MAX_TEXTS_PER_REQUEST}")

    def test_translate__cuts_a_new_request_when_the_byte_budget_is_full(self):
        # setup — a budget that fits two of the three texts
        provider = DeepLProvider(api_key="abc")
        first = _response(payload={"translations": [{"text": "TEXT A"}, {"text": "TEXT B"}]})
        second = _response(payload={"translations": [{"text": "TEXT C"}]})

        # do it
        with mock.patch("interaktiv.translation.providers.deepl.MAX_REQUEST_BYTES", 12):
            with mock.patch("requests.post", side_effect=[first, second]) as post:
                result = provider.translate(["text a", "text b", "text c"], "EN")

        # postcondition
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["text"], ["text a", "text b"])
        self.assertEqual(result, ["TEXT A", "TEXT B", "TEXT C"])

    def test_translate_texts_by_key__bundles_all_fields_into_one_request(self):
        # setup
        provider = DeepLProvider(api_key="abc")
        answers = {"translations": [{"text": "TITLE"}, {"text": "TEXT A"}, {"text": "TEXT B"}]}

        # do it
        with mock.patch("requests.post", return_value=_response(payload=answers)) as post:
            result = provider.translate_texts_by_key(
                {"field_a": ["title"], "field_b": ["text a", "text b"]}, "EN"
            )

        # postcondition — one request, the answers sliced back per field
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["text"], ["title", "text a", "text b"])
        self.assertEqual(result, {"field_a": ["TITLE"], "field_b": ["TEXT A", "TEXT B"]})

    def test_translate__names_a_refused_key_rather_than_a_generic_failure(self):
        with mock.patch("requests.post", return_value=_response(status=403)):
            with self.assertRaises(TranslationError) as caught:
                DeepLProvider(api_key="abc").translate(["Hallo"], "EN")

        self.assertEqual(caught.exception.status, 403)
        self.assertIn("refused the API key", str(caught.exception))

    def test_translate__reports_a_used_up_quota_as_a_rate_limit(self):
        with mock.patch("requests.post", return_value=_response(status=456)):
            with self.assertRaises(TranslationError) as caught:
                DeepLProvider(api_key="abc").translate(["Hallo"], "EN")

        self.assertEqual(caught.exception.status, 429)
        self.assertIn("quota", str(caught.exception))

    def test_translate__retries_a_rate_limited_request(self):
        # setup — the first answer is a 429, the second succeeds
        provider = DeepLProvider(api_key="abc")
        answers = [
            _response(status=429),
            _response(payload={"translations": [{"text": "Hello"}]}),
        ]

        # do it
        with mock.patch("interaktiv.translation.providers.deepl.time.sleep") as sleep:
            with mock.patch("requests.post", side_effect=answers) as post:
                result = provider.translate(["Hallo"], "EN")

        # postcondition — one wait, one retry, then the answer
        self.assertEqual(result, ["Hello"])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(sleep.call_count, 1)

    def test_translate__gives_up_when_the_rate_limit_stays(self):
        # setup
        provider = DeepLProvider(api_key="abc")

        # do it / postcondition — all attempts used, then the 429 surfaces
        with mock.patch("interaktiv.translation.providers.deepl.time.sleep") as sleep:
            with mock.patch("requests.post", return_value=_response(status=429)) as post:
                with self.assertRaises(TranslationError) as caught:
                    provider.translate(["Hallo"], "EN")

        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(post.call_count, RETRY_ATTEMPTS)
        self.assertEqual(sleep.call_count, RETRY_ATTEMPTS - 1)

    def test_translate__reports_an_unreachable_deepl_as_such(self):
        import requests

        with mock.patch("requests.post", side_effect=requests.ConnectionError("no route")):
            with self.assertRaises(TranslationError) as caught:
                DeepLProvider(api_key="abc").translate(["Hallo"], "EN")

        self.assertIn("not reachable", str(caught.exception))

    def test_translate__refuses_an_answer_that_lost_a_text(self):
        with mock.patch("requests.post", return_value=_response(payload={"translations": []})):
            with self.assertRaises(TranslationError):
                DeepLProvider(api_key="abc").translate(["Hallo"], "EN")

    def test_languages__is_empty_rather_than_broken_when_deepl_is_down(self):
        import requests

        with mock.patch("requests.post", side_effect=requests.ConnectionError("no route")):
            self.assertEqual(DeepLProvider(api_key="abc").languages(), [])

    def test_languages__asks_only_when_there_is_a_key(self):
        with mock.patch("requests.post") as post:
            self.assertEqual(DeepLProvider(api_key="").languages(), [])
        post.assert_not_called()

    def test_languages__reads_the_codes_and_names_deepl_offers(self):
        with mock.patch(
            "requests.post",
            return_value=_response(payload=[{"language": "EN-GB", "name": "English (British)"}]),
        ):
            self.assertEqual(
                DeepLProvider(api_key="abc").languages(),
                [{"code": "EN-GB", "title": "English (British)"}],
            )


class TestMockProvider(TestCase):
    def setUp(self):
        super().setUp()

        self.provider = MockProvider()

    def test_registered__is_in_the_stock_registry(self):
        self.assertIs(PROVIDERS.get("mock"), MockProvider)

    def test_configured__needs_no_key(self):
        self.assertTrue(self.provider.configured())

    def test_languages__offers_the_codes_without_asking_anyone(self):
        self.assertEqual(
            self.provider.languages(),
            [{"code": "DE", "title": "Deutsch"}, {"code": "EN", "title": "English"}],
        )

    def test_translate__uppercases_each_text(self):
        # do it
        result = self.provider.translate(["some text", "other text"], "EN")

        # postcondition
        self.assertEqual(result, ["SOME TEXT", "OTHER TEXT"])

    def test_translate__leaves_tags_and_entities_untouched(self):
        # setup
        html = '<p>some <strong>text</strong> &amp; <a href="https://interaktiv.de">link</a></p>'

        # do it
        result = self.provider.translate([html], "EN")

        # postcondition
        self.assertEqual(
            result,
            ['<p>SOME <strong>TEXT</strong> &amp; <a href="https://interaktiv.de">LINK</a></p>'],
        )
