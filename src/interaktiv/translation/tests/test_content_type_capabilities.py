"""The whole flow for content types that lack what a page has: versioning, a
workflow, or (on a site without plone.app.iterate) working copies. None of
them may make a translation fail; what they lack only costs their history."""

from unittest import mock

import plone.api as api
import transaction
from plone.app.iterate.interfaces import ICheckinCheckoutPolicy
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD

from interaktiv.translation.storage import (
    STATUS_MACHINE_EDITED,
    STATUS_MACHINE_REVIEWED,
    STATUS_MACHINE_UNREVIEWED,
    translation_status,
)
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING,
    INTERAKTIV_TRANSLATION_WORKING_COPY_FUNCTIONAL_TESTING,
    RelativeSession,
    TestCase,
)
from interaktiv.translation.tests.test_integration import _deepl, _records


class CapabilitiesTestCase(TestCase):
    portal_type = "Folder"
    workflow = "simple_publication_workflow"

    def setUp(self) -> None:
        super().setUp()
        workflow_tool = api.portal.get_tool("portal_workflow")
        workflow_tool.setChainForPortalTypes([self.portal_type], (self.workflow,) if self.workflow else ())
        self.source = api.content.create(
            container=self.portal["de"],
            type=self.portal_type,
            id="item",
            title="Titel",
            description="Beschreibung",
        )
        _records().api_key = "test-key"
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        transaction.commit()

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def _translate(self, **body):
        payload = {"target_language": "en", "save": True}
        payload.update(body)
        with mock.patch("requests.post", return_value=_deepl("Title", "Description")):
            response = self.api_session.post("/de/item/@translate", json=payload)
        transaction.begin()

        return response

    def _translation(self):
        return self.portal["en"]["item"]

    def _status_over_rest(self, path):
        return self.api_session.get(f"{path}/@machine-translation").json()["status"]


class TestWithoutVersioningWithWorkingCopies(CapabilitiesTestCase):
    """A folder: workflow yes, versioning and locking no, on a site with
    working copies. iterate cannot check out what it cannot lock, so the
    folder's translation is overwritten as on a site without iterate."""

    layer = INTERAKTIV_TRANSLATION_WORKING_COPY_FUNCTIONAL_TESTING

    def test_second_translation__asks_for_overwrite(self):
        # setup
        self._translate()

        # do it
        response = self._translate()

        # postcondition — refused like on a site without working copies, not
        # with a checkout that could never succeed
        self.assertEqual(response.status_code, 409)
        self.assertIn("Ask for overwrite", response.json()["message"])

    def test_overwrite__replaces_the_translation_without_a_working_copy(self):
        # setup
        self._translate()

        # do it
        response = self._translate(overwrite=True)

        # postcondition
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["report"]["stored_as"], "translation")
        self.assertIsNone(ICheckinCheckoutPolicy(self._translation()).getWorkingCopy())

    def test_publish__marks_the_translation_as_reviewed(self):
        # setup
        self._translate()

        # do it
        api.content.transition(obj=self._translation(), transition="publish")
        transaction.commit()

        # postcondition
        self.assertEqual(translation_status(self._translation()), STATUS_MACHINE_REVIEWED)

    def test_get__offers_no_working_copies_for_the_folder(self):
        # do it
        response = self.api_session.get("/de/item/@translate")

        # postcondition — the front end asks for overwrite instead
        self.assertFalse(response.json()["working_copies_enabled"])

    def test_status_endpoints__answer_for_the_translation(self):
        # setup
        self._translate()

        # do it / postcondition
        self.assertEqual(self._status_over_rest("/en/item"), STATUS_MACHINE_UNREVIEWED)
        response = self.api_session.get("/de/item/@translate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["translations"]["en"]["status"], STATUS_MACHINE_UNREVIEWED)


class TestWithoutVersioningWithoutWorkingCopies(CapabilitiesTestCase):
    """A folder on a multilingual site without plone.app.iterate."""

    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def test_overwrite__succeeds_without_a_version_to_fall_back_on(self):
        # setup
        self._translate()

        # do it
        response = self._translate(overwrite=True)

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report"]["stored_as"], "translation")
        self.assertEqual(self._translation().title, "Title")

    def test_publish__marks_the_translation_as_reviewed(self):
        # setup
        self._translate()

        # do it
        api.content.transition(obj=self._translation(), transition="publish")
        transaction.commit()

        # postcondition
        self.assertEqual(translation_status(self._translation()), STATUS_MACHINE_REVIEWED)

    def test_edit__marks_the_translation_as_edited(self):
        # setup
        self._translate()

        # do it
        response = self.api_session.patch("/en/item", json={"title": "Edited"})
        transaction.begin()

        # postcondition
        self.assertEqual(response.status_code, 204)
        self.assertEqual(translation_status(self._translation()), STATUS_MACHINE_EDITED)


class TestWithoutWorkflowWithWorkingCopies(CapabilitiesTestCase):
    """A versioned page type bound to no workflow, on a site with working
    copies: review happens by checking in."""

    layer = INTERAKTIV_TRANSLATION_WORKING_COPY_FUNCTIONAL_TESTING
    portal_type = "Document"
    workflow = None

    def test_get__offers_working_copies_for_the_page(self):
        # do it
        response = self.api_session.get("/de/item/@translate")

        # postcondition
        self.assertTrue(response.json()["working_copies_enabled"])

    def test_translate_edit_and_checkin__succeed(self):
        # setup
        self._translate()
        self._translate()

        # do it
        edit = self.api_session.patch("/en/copy_of_item", json={"title": "Edited"})
        checkin = self.api_session.patch("/en/item/@workingcopy")
        transaction.begin()

        # postcondition
        self.assertEqual(edit.status_code, 204)
        self.assertEqual(checkin.status_code, 204)
        self.assertEqual(translation_status(self._translation()), STATUS_MACHINE_REVIEWED)


class TestWithoutWorkflowWithoutWorkingCopies(CapabilitiesTestCase):
    """A page type bound to no workflow on a site without working copies:
    nothing can mark it reviewed, but nothing fails either."""

    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING
    portal_type = "Document"
    workflow = None

    def test_translate_and_overwrite__succeed(self):
        # do it
        first = self._translate()
        second = self._translate(overwrite=True)

        # postcondition
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

    def test_status__stays_unreviewed_and_is_reported(self):
        # setup
        self._translate()

        # do it / postcondition — known gap: without workflow and working
        # copies there is no review step
        self.assertEqual(self._status_over_rest("/en/item"), STATUS_MACHINE_UNREVIEWED)
        self.assertEqual(self.api_session.get("/en/item").status_code, 200)
