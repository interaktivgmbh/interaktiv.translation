import os
from unittest import mock

import requests
import transaction
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD

from interaktiv.translation.controlpanels.api_key import API_KEY_PLACEHOLDER
from interaktiv.translation.helpers.encryption import SECRET_VARIABLE, is_encrypted
from interaktiv.translation.settings import Settings
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING,
    RelativeSession,
    TestCase,
)
from interaktiv.translation.tests.test_integration import _records


def _answer(status_code=200, **body):
    response = mock.Mock()
    response.status_code = status_code
    response.ok = status_code < 400
    response.json.return_value = body
    response.text = ""

    return response


USAGE = _answer(character_count=12480, character_limit=1000000)


class TestConnectionPost(TestCase):
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

    def _test(self, **form):
        return self.api_session.post("/@translation-connection", json=form)

    def test_post__is_for_site_managers_only(self):
        # setup
        self.api_session.auth = None

        # do it
        response = self._test()

        # postcondition
        self.assertEqual(response.status_code, 401)

    def test_post__tells_the_account_of_the_stored_key(self):
        # do it
        with mock.patch("requests.post", return_value=USAGE) as post:
            response = self._test()

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "provider": "DeepL", "plan": "pro", "character_count": 12480, "character_limit": 1000000},
        )
        self.assertTrue(post.call_args.args[0].endswith("/usage"))
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "DeepL-Auth-Key key-value-a")

    def test_post__tests_the_key_of_the_form_before_it_is_saved(self):
        # do it — a free key, as the form holds it
        with mock.patch("requests.post", return_value=USAGE) as post:
            response = self._test(api_key="key-value-b:fx")

        # postcondition — the stored key is untouched
        self.assertEqual(response.json()["plan"], "free")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "DeepL-Auth-Key key-value-b:fx")
        transaction.begin()
        self.assertEqual(Settings().api_key, "key-value-a")
        self.assertTrue(is_encrypted(_records().api_key))

    def test_post__tests_the_stored_key_for_the_placeholder(self):
        # do it
        with mock.patch("requests.post", return_value=USAGE) as post:
            self._test(api_key=API_KEY_PLACEHOLDER)

        # postcondition
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "DeepL-Auth-Key key-value-a")

    def test_post__tells_a_refused_key(self):
        # do it
        with mock.patch("requests.post", return_value=_answer(403)):
            response = self._test()

        # postcondition — an answer, not an error of the request
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(response.json()["code"], "key_refused")

    def test_post__tells_a_used_up_quota(self):
        # do it
        with mock.patch("requests.post", return_value=_answer(456)):
            response = self._test()

        # postcondition
        self.assertEqual(response.json()["code"], "quota_exceeded")

    def test_post__tells_an_unreachable_service(self):
        # do it
        with mock.patch("requests.post", side_effect=requests.ConnectionError("no route")):
            response = self._test()

        # postcondition
        self.assertEqual(response.json()["code"], "unreachable")

    def test_post__tells_a_missing_key_without_asking_the_service(self):
        # do it — the key emptied in the form
        with mock.patch("requests.post") as post:
            response = self._test(api_key="")

        # postcondition
        self.assertEqual(response.json()["code"], "not_configured")
        post.assert_not_called()

    def test_post__answers_for_the_provider_of_the_form(self):
        # do it — the mock needs no key
        response = self._test(provider={"token": "mock", "title": "Mock"}, api_key="")

        # postcondition
        self.assertTrue(response.json()["ok"])

    def test_post__tells_an_unknown_provider(self):
        # do it
        response = self._test(provider="provider_unknown")

        # postcondition
        self.assertEqual(response.json()["code"], "unknown_provider")

    def test_get__tells_how_the_stored_key_is_kept_never_the_key(self):
        # do it
        response = self.api_session.get("/@translation-connection")

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"api_key": {"stored": True, "encryption": "site", "readable": True}})
        self.assertNotIn("key-value-a", response.text)

    def test_get__is_for_site_managers_only(self):
        # setup
        self.api_session.auth = None

        # do it
        response = self.api_session.get("/@translation-connection")

        # postcondition
        self.assertEqual(response.status_code, 401)

    def test_post__tells_a_stored_key_that_cannot_be_decrypted(self):
        # setup — encrypted with a secret of the environment that changed since
        with mock.patch.dict(os.environ, {SECRET_VARIABLE: "secret-a"}):
            _records().api_key = "key-value-b"
            transaction.commit()

        # do it
        with mock.patch.dict(os.environ, {SECRET_VARIABLE: "secret-b"}), mock.patch("requests.post") as post:
            response = self._test()

        # postcondition
        self.assertEqual(response.json()["code"], "key_unreadable")
        post.assert_not_called()

