from unittest import mock

import plone.api as api
import transaction
from interaktiv.translation.testing import TestCase
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD
from zope.annotation.interfaces import IAnnotations

from interaktiv.translation.storage import (
    MACHINE_TRANSLATION_KEY,
    STATUS_MACHINE_EDITED,
    STATUS_MACHINE_REVIEWED,
    STATUS_MACHINE_UNREVIEWED,
    STATUS_MANUAL,
    translation_status,
)
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING,
    RelativeSession,
)
from interaktiv.translation.tests.test_integration import _deepl, _records


class TestEditSubscriber(TestCase):
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
        self.api_session.headers.update({"Content-Type": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        transaction.commit()

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def _translate_in_place(self):
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            return self.api_session.post("/page/@translate", json={"target_language": "en", "save": True})

    def _edit(self, title):
        response = self.api_session.patch("/page", json={"title": title})
        transaction.begin()

        return response

    def test_translation_status__reads_the_marker(self):
        # precondition
        self.assertEqual(translation_status(self.page), STATUS_MANUAL)

        # do it
        self._translate_in_place()
        transaction.begin()

        # postcondition
        self.assertEqual(translation_status(self.page), STATUS_MACHINE_UNREVIEWED)

    def test_store__does_not_count_as_an_edit(self):
        # do it — the machine writes; the storing flag keeps the edit
        # subscriber quiet
        self._translate_in_place()
        transaction.begin()

        # postcondition
        self.assertNotIn("edited_by", IAnnotations(self.page)[MACHINE_TRANSLATION_KEY])

    def test_edit__records_editor_and_time_on_the_marker(self):
        # setup
        self._translate_in_place()

        # do it
        response = self._edit("Good day, edited")

        # postcondition
        self.assertEqual(response.status_code, 204)
        marker = IAnnotations(self.page)[MACHINE_TRANSLATION_KEY]
        self.assertEqual(marker["edited_by"], SITE_OWNER_NAME)
        self.assertIn("edited", marker)
        self.assertEqual(translation_status(self.page), STATUS_MACHINE_EDITED)

    def test_edit__after_the_review_changes_nothing(self):
        # setup — reviewed via publish
        self._translate_in_place()
        transaction.begin()
        with api.env.adopt_user(SITE_OWNER_NAME):
            api.content.transition(obj=self.page, transition="publish")
        transaction.commit()

        # do it
        self._edit("Good day, edited after review")

        # postcondition — reviewed stays reviewed
        marker = IAnnotations(self.page)[MACHINE_TRANSLATION_KEY]
        self.assertNotIn("edited_by", marker)
        self.assertEqual(translation_status(self.page), STATUS_MACHINE_REVIEWED)

    def test_edit__of_an_unmarked_page_stays_manual(self):
        # do it
        self._edit("Von Hand geändert")

        # postcondition
        self.assertIsNone(IAnnotations(self.page).get(MACHINE_TRANSLATION_KEY))
        self.assertEqual(translation_status(self.page), STATUS_MANUAL)
