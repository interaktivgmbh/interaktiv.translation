from unittest import mock

import plone.api as api
import transaction
from interaktiv.translation.testing import TestCase
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD

from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING,
    RelativeSession,
)
from interaktiv.translation.tests.test_integration import _deepl, _records


class TestMachineTranslationGet(TestCase):
    layer = INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.portal.portal_workflow.setDefaultChain("simple_publication_workflow")
        self.page = api.content.create(
            container=self.portal,
            type="Document",
            id="page",
            title="Guten Tag",
            description="Eine Seite",
        )
        _records().api_key = "test-key"
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        transaction.commit()

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def _translate_in_place(self):
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            return self.api_session.post("/page/@translate", json={"target_language": "en", "save": True})

    def test_get__answers_false_for_a_page_nobody_machine_translated(self):
        # do it
        response = self.api_session.get("/page/@machine-translation")

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["machine_translated"])
        self.assertEqual(response.json()["status"], "manual")

    def test_get__tells_tool_and_language_after_a_translation(self):
        # setup
        self._translate_in_place()

        # do it
        response = self.api_session.get("/page/@machine-translation")

        # postcondition
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["machine_translated"])
        self.assertEqual(body["status"], "machine_unreviewed")
        self.assertEqual(body["provider"], "DeepL")
        self.assertEqual(body["target_language"], "en")
        self.assertIn("translated", body)
        self.assertNotIn("reviewed_by", body)

    def test_expand__rides_along_on_the_content_get(self):
        # setup
        self._translate_in_place()

        # do it
        response = self.api_session.get("/page?expand=machine_translation")

        # postcondition — one request serves the page and the banner
        self.assertEqual(response.status_code, 200)
        component = response.json()["@components"]["machine_translation"]
        self.assertTrue(component["machine_translated"])
        self.assertEqual(component["provider"], "DeepL")

    def test_get__collapsed_component_names_only_its_url(self):
        # do it
        response = self.api_session.get("/page")

        # postcondition
        component = response.json()["@components"]["machine_translation"]
        self.assertEqual(list(component), ["@id"])

    def _publish_and_visit_anonymously(self):
        # setup helper: the page goes public, the visitor carries no login
        transaction.begin()
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="publish")
        transaction.commit()
        visitor = RelativeSession(self.portal.absolute_url(), test=self)
        visitor.headers.update({"Accept": "application/json"})

        return visitor

    def test_get__is_not_for_visitors(self):
        # setup
        self._translate_in_place()
        visitor = self._publish_and_visit_anonymously()

        # do it
        response = visitor.get("/page/@machine-translation")
        visitor.close()

        # postcondition — review state is editorial, the service needs the
        # permission to change the page
        self.assertEqual(response.status_code, 401)

    def test_expand__answers_visitors_only_the_component_url(self):
        # setup — the marker exists, but the visitor may not edit the page
        self._translate_in_place()
        visitor = self._publish_and_visit_anonymously()

        # do it
        response = visitor.get("/page?expand=machine_translation")
        visitor.close()

        # postcondition — no reviewer id, no timestamps: only the URL
        self.assertEqual(response.status_code, 200)
        component = response.json()["@components"]["machine_translation"]
        self.assertEqual(list(component), ["@id"])
