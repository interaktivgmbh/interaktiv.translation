from unittest import mock

import plone.api as api
import transaction
from interaktiv.translation.testing import TestCase
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD
from zope.annotation.interfaces import IAnnotations

from interaktiv.translation.storage import MACHINE_TRANSLATION_KEY
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING,
    RelativeSession,
)
from interaktiv.translation.tests.test_integration import _deepl, _records


class TestPublicationSubscriber(TestCase):
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

    def test_publish__records_the_review_on_the_marker(self):
        # setup
        self._translate_in_place()
        transaction.begin()

        # precondition
        self.assertNotIn("reviewed_by", IAnnotations(self.page)[MACHINE_TRANSLATION_KEY])

        # do it
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="publish")

        # postcondition
        marker = IAnnotations(self.page)[MACHINE_TRANSLATION_KEY]
        self.assertEqual(marker["reviewed_by"], SITE_OWNER_NAME)
        self.assertIn("reviewed", marker)

    def test_publish__of_an_ordinary_page_sets_no_marker(self):
        # do it
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="publish")

        # postcondition
        self.assertIsNone(IAnnotations(self.page).get(MACHINE_TRANSLATION_KEY))

    def test_submit__is_not_yet_the_review(self):
        # setup
        self._translate_in_place()
        transaction.begin()

        # do it
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="submit")

        # postcondition
        self.assertNotIn("reviewed_by", IAnnotations(self.page)[MACHINE_TRANSLATION_KEY])

    def _last_workflow_comment(self) -> str:
        workflow_tool = api.portal.get_tool("portal_workflow")

        return workflow_tool.getInfoFor(self.page, "comments")

    def test_publish__writes_the_review_into_the_workflow_entry(self):
        # setup
        self._translate_in_place()
        transaction.begin()

        # do it
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="publish")

        # postcondition
        expected_comment = f"Machine translation into en with DeepL, reviewed by {SITE_OWNER_NAME}"
        self.assertEqual(self._last_workflow_comment(), expected_comment)

    def test_publish__keeps_the_editors_own_comment_in_front(self):
        # setup
        self._translate_in_place()
        transaction.begin()
        workflow_tool = api.portal.get_tool("portal_workflow")

        # do it
        with api.env.adopt_user(SITE_OWNER_NAME):
            workflow_tool.doActionFor(self.page, "publish", comment="Passt so")

        # postcondition
        expected_comment = f"Passt so — Machine translation into en with DeepL, reviewed by {SITE_OWNER_NAME}"
        self.assertEqual(
            self._last_workflow_comment(), expected_comment)

    def test_submit__gets_no_review_note(self):
        # setup
        self._translate_in_place()
        transaction.begin()

        # do it
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="submit")

        # postcondition
        self.assertEqual(self._last_workflow_comment(), "")

    def test_publish__after_the_review_gets_no_second_note(self):
        # setup
        self._translate_in_place()
        transaction.begin()
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="publish")
            api.content.transition(obj=self.page, transition="retract")

            # do it
            api.content.transition(obj=self.page, transition="publish")

        # postcondition
        self.assertEqual(self._last_workflow_comment(), "")

    def test_publish__keeps_an_earlier_review(self):
        # setup
        self._translate_in_place()
        transaction.begin()
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="publish")
        first_review = dict(IAnnotations(self.page)[MACHINE_TRANSLATION_KEY])
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="retract")

            # do it
            api.content.transition(obj=self.page, transition="publish")

        # postcondition
        self.assertEqual(IAnnotations(self.page)[MACHINE_TRANSLATION_KEY], first_review)
