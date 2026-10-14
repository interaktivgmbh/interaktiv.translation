from unittest import mock

import plone.api as api
import transaction
from interaktiv.translation.testing import TestCase
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD
from zope.annotation.interfaces import IAnnotations

from interaktiv.translation.storage import MACHINE_TRANSLATION_KEY
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_WORKING_COPY_FUNCTIONAL_TESTING,
    RelativeSession,
)
from interaktiv.translation.tests.test_integration import _deepl, _records


class TestCheckin(TestCase):
    layer = INTERAKTIV_TRANSLATION_WORKING_COPY_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.page = api.content.create(
            container=self.portal["de"],
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

    def _translate(self):
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            return self.api_session.post("/de/page/@translate", json={"target_language": "en", "save": True})

    def _working_copy(self):
        from plone.app.iterate.interfaces import ICheckinCheckoutPolicy

        return ICheckinCheckoutPolicy(self.portal["en"]["page"]).getWorkingCopy()

    def _translate_into_working_copy(self):
        # setup helper: first translation creates the sibling, the second
        # lands in a working copy of it
        self._translate()
        self._translate()
        transaction.begin()

        return self._working_copy()

    def _checkin(self):
        response = self.api_session.patch("/en/page/@workingcopy")
        transaction.begin()

        return response

    def _history(self):
        return api.portal.get_tool("portal_repository").getHistory(self.portal["en"]["page"])

    def test_store__marks_the_working_copy_as_machine_translated(self):
        # do it
        working_copy = self._translate_into_working_copy()

        # postcondition
        marker = IAnnotations(working_copy).get(MACHINE_TRANSLATION_KEY)
        self.assertIsNotNone(marker)
        self.assertEqual(marker["provider"], "DeepL")
        self.assertEqual(marker["target_language"], "en")
        self.assertIn("translated", marker)

    def test_checkin__labels_both_versions_it_cuts(self):
        # setup
        self._translate_into_working_copy()
        versions_before = len(self._history())

        # do it
        response = self._checkin()

        # postcondition
        self.assertEqual(response.status_code, 204)
        history = self._history()
        self.assertEqual(len(history), versions_before + 2)

        # Comment from Version created by Iterate
        self.assertEqual(history[1].comment, "Checked in")

        # Comment from Version created by modified event
        expected_comment = f"Machine translation into en with DeepL, reviewed by {SITE_OWNER_NAME}"
        self.assertEqual(history[0].comment, expected_comment)


    def test_checkin__records_the_review_on_the_new_baseline(self):
        # setup
        self._translate_into_working_copy()

        # do it
        self._checkin()

        # postcondition
        marker = IAnnotations(self.portal["en"]["page"]).get(MACHINE_TRANSLATION_KEY)
        self.assertEqual(marker["reviewed_by"], SITE_OWNER_NAME)
        self.assertIn("reviewed", marker)

    def test_checkin__of_an_ordinary_working_copy_stays_silent(self):
        # setup
        from plone.app.iterate.interfaces import ICheckinCheckoutPolicy

        with api.env.adopt_user(SITE_OWNER_NAME):
            working_copy = ICheckinCheckoutPolicy(self.page).checkout(self.portal["de"])
            working_copy.title = "Von Hand bearbeitet"
        transaction.commit()

        # do it
        response = self.api_session.patch("/de/page/@workingcopy")
        transaction.begin()

        # postcondition
        self.assertEqual(response.status_code, 204)
        history = api.portal.get_tool("portal_repository").getHistory(self.page)
        self.assertNotIn("Machine translation", history[0].comment or "")
        self.assertIsNone(IAnnotations(self.page).get(MACHINE_TRANSLATION_KEY))

    def test_checkin__without_a_working_copy_is_a_bad_request_not_a_crash(self):
        # do it
        response = self.api_session.patch("/de/page/@workingcopy")

        # postcondition
        self.assertEqual(response.status_code, 400)
        self.assertIn("no working copy", response.json()["error"]["message"])

    def test_checkin__restores_translation_management_on_the_new_baseline(self):
        # setup
        from AccessControl import getSecurityManager

        from interaktiv.translation.subscribers.events import MANAGE_TRANSLATIONS_PERMISSION

        self._translate_into_working_copy()

        # do it — the copy becomes the new baseline
        self._checkin()

        # postcondition — the denial did not travel along
        with api.env.adopt_user(SITE_OWNER_NAME):
            security = getSecurityManager()
            self.assertTrue(
                security.checkPermission(MANAGE_TRANSLATIONS_PERMISSION, self.portal["en"]["page"])
            )

    def test_checkin__after_the_review_tells_the_story_only_once(self):
        # setup
        from plone.app.iterate.interfaces import ICheckinCheckoutPolicy

        self._translate_into_working_copy()
        self._checkin()
        with api.env.adopt_user(SITE_OWNER_NAME):
            second_copy = ICheckinCheckoutPolicy(self.portal["en"]["page"]).checkout(self.portal["en"])
            second_copy.title = "Edited by hand"
        transaction.commit()

        # do it
        self._checkin()

        # postcondition
        self.assertNotIn("Machine translation", self._history()[0].comment or "")
