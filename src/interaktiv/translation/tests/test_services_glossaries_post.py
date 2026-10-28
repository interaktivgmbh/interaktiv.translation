from unittest import mock

import requests
import transaction
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD

from interaktiv.translation.controlpanels.api_key import API_KEY_PLACEHOLDER
from interaktiv.translation.providers.mock import MockProvider
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING,
    RelativeSession,
    TestCase,
)
from interaktiv.translation.tests.test_integration import _records
from interaktiv.translation.tests.test_services_connection_post import _answer

GLOSSARIES = _answer(
    glossaries=[
        {
            "glossary_id": "glossary-id-a",
            "name": "glossary-name-a",
            "ready": True,
            "source_lang": "de",
            "target_lang": "en",
            "creation_time": "2026-10-01T00:00:00Z",
            "entry_count": 3,
        },
        {"glossary_id": "glossary-id-b", "name": "glossary-name-b", "source_lang": "EN", "target_lang": "DE"},
        {"name": "glossary-name-without-id"},
    ]
)


class TestGlossariesPost(TestCase):
    layer = INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        _records().api_key = "key-value-a"
        transaction.commit()
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def _list(self, **form):
        return self.api_session.post("/@translation-glossaries", json=form)

    def test_post__is_for_site_managers_only(self):
        # setup
        self.api_session.auth = None

        # do it
        response = self._list()

        # postcondition
        self.assertEqual(response.status_code, 401)

    def test_post__lists_the_glossaries_of_the_account(self):
        # do it
        with mock.patch("requests.get", return_value=GLOSSARIES) as get:
            response = self._list()

        # postcondition — lower case codes; an entry without an ID is left out
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "provider": "DeepL",
                "glossaries": [
                    {"id": "glossary-id-a", "name": "glossary-name-a", "source": "de", "target": "en", "entries": 3},
                    {"id": "glossary-id-b", "name": "glossary-name-b", "source": "en", "target": "de", "entries": None},
                ],
            },
        )
        self.assertTrue(get.call_args.args[0].endswith("/v2/glossaries"))
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "DeepL-Auth-Key key-value-a")

    def test_post__lists_with_the_key_of_the_form(self):
        # do it
        with mock.patch("requests.get", return_value=GLOSSARIES) as get:
            self._list(api_key="key-value-b:fx")

        # postcondition — a free key asks the free API
        self.assertIn("api-free.deepl.com", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "DeepL-Auth-Key key-value-b:fx")

    def test_post__lists_with_the_stored_key_for_the_placeholder(self):
        # do it
        with mock.patch("requests.get", return_value=GLOSSARIES) as get:
            self._list(api_key=API_KEY_PLACEHOLDER)

        # postcondition
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "DeepL-Auth-Key key-value-a")

    def test_post__tells_an_account_without_glossaries(self):
        # do it
        with mock.patch("requests.get", return_value=_answer(glossaries=[])):
            response = self._list()

        # postcondition
        self.assertEqual(response.json()["glossaries"], [])

    def test_post__tells_a_refused_key(self):
        # do it
        with mock.patch("requests.get", return_value=_answer(403)):
            response = self._list()

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(response.json()["code"], "key_refused")

    def test_post__tells_an_unreachable_service(self):
        # do it
        with mock.patch("requests.get", side_effect=requests.ConnectionError("no route")):
            response = self._list()

        # postcondition
        self.assertEqual(response.json()["code"], "unreachable")

    def test_post__tells_a_missing_key_without_asking_the_service(self):
        # do it
        with mock.patch("requests.get") as get:
            response = self._list(api_key="")

        # postcondition
        self.assertEqual(response.json()["code"], "not_configured")
        get.assert_not_called()

    def test_post__lists_none_for_a_provider_without_glossaries(self):
        # do it — the mock needs no key
        response = self._list(provider="mock", api_key="")

        # postcondition
        self.assertEqual(response.json(), {"ok": True, "provider": MockProvider.title, "glossaries": []})
