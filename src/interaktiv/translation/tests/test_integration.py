import json
from unittest import mock

import plone.api as api
import transaction
from Acquisition import aq_base
from interaktiv.translation.controlpanels.api_key import API_KEY_PLACEHOLDER
from interaktiv.translation.helpers.encryption import is_encrypted
from interaktiv.translation.helpers.field_selection import ALWAYS_FIELDS, COPIED_FIELDS, EXCLUDED_FIELDS
from interaktiv.translation.testing import TestCase
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD, TEST_USER_ID
from plone.protect.interfaces import IDisableCSRFProtection
from Products.statusmessages.interfaces import IStatusMessage
from plone.registry.interfaces import IRegistry
from zope.annotation.interfaces import IAnnotations
from plone.namedfile.file import NamedBlobFile, NamedBlobImage
from zope.component import getUtility
from zope.schema.interfaces import IVocabularyFactory

from interaktiv.translation.registry.translation import ITranslationSettings
from interaktiv.translation.settings import Settings
from interaktiv.translation.storage import MACHINE_TRANSLATION_KEY, TranslationStorage
from interaktiv.translation.services.translate.post import TranslatePost
from interaktiv.translation.views.translate import TranslateContentView, TranslationAvailableView
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING,
    INTERAKTIV_TRANSLATION_INTEGRATION_TESTING,
    INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING,
    INTERAKTIV_TRANSLATION_WORKING_COPY_FUNCTIONAL_TESTING,
    RelativeSession,
)


# The smallest valid GIF: one transparent pixel.
GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _records():
    return getUtility(IRegistry).forInterface(ITranslationSettings, check=False)


def _deepl(*texts):
    response = mock.Mock()
    response.status_code = 200
    response.ok = True
    response.json.return_value = {"translations": [{"text": t} for t in texts]}

    return response


class TestSettings(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def test_records__are_installed_and_empty_apart_from_the_defaults(self):
        # do it
        records = _records()

        # postcondition — nothing to talk to until someone pastes a key
        self.assertIsNone(records.api_key)
        self.assertIsNone(records.api_url)
        self.assertEqual(records.provider, "deepl")
        self.assertEqual(records.excluded_fields, list(EXCLUDED_FIELDS))
        self.assertEqual(records.always_fields, list(ALWAYS_FIELDS))
        self.assertEqual(records.copied_fields, list(COPIED_FIELDS))
        self.assertEqual(records.excluded_types, [])

    def test_provider__ships_deepl_and_the_mock(self):
        # do it
        vocabulary = self._providers()

        # postcondition
        self.assertEqual([term.value for term in vocabulary], ["deepl", "mock"])

    def _providers(self):
        from zope.schema.interfaces import IVocabularyFactory

        factory = getUtility(IVocabularyFactory, name="interaktiv.translation.Providers")

        return factory(self.portal)


class TestEditBarAction(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def _action(self):
        # Taken out of the category rather than by traversal: an ObjectManager
        # acquires whatever name it does not have, so a missing action would
        # come back as an unrelated object instead of as None.
        category = api.portal.get_tool("portal_actions")["object_buttons"]
        for action in category.objectValues():
            if action.getId() == "translate":
                return action

        return None

    def test_action__is_installed_where_both_front_ends_read_it(self):
        # postcondition — Classic draws object_buttons in the edit bar, and
        # Volto lists them in the toolbar. One entry, both UIs.
        action = self._action()

        self.assertIsNotNone(action)
        self.assertEqual(action.title, "Translate")
        self.assertIn("@@translate-content", action.getProperty("url_expr"))

    def test_action__asks_the_view_whether_it_can_work_at_all(self):
        # postcondition — the condition is what keeps an unusable entry out of
        # both edit bars, so it must point at the view that knows.
        condition = self._action().getProperty("available_expr")

        # A call, not an attribute read: restricted Python may publish a view
        # but may not read attributes off one.
        self.assertIn("@@translation-available", condition)
        self.assertTrue(condition.endswith("()"))

    def test_action__needs_the_permission_to_manage_translations(self):
        self.assertEqual(
            list(self._action().getProperty("permissions")),
            ["plone.app.multilingual: Manage Translations"],
        )


class TestTranslateService(TestCase):
    layer = INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
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

    def test_get__reports_what_the_site_can_translate_into(self):
        # do it
        response = self.api_session.get("/page/@translate")

        # postcondition
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["provider"], "deepl")
        self.assertEqual(body["languages"], [{"code": "en", "title": "en", "machine": True}])

    def test_get__offers_the_configured_target_languages_without_multilingual(self):
        # setup
        tool = api.portal.get_tool("portal_languages")
        tool.addSupportedLanguage("fr")
        tool.addSupportedLanguage("it")
        _records().target_languages = ["fr", "it"]
        transaction.commit()

        # do it
        response = self.api_session.get("/page/@translate")

        # postcondition — no language root folders, so nothing to check them against
        languages = response.json()["languages"]
        self.assertEqual([entry["code"] for entry in languages], ["fr", "it"])
        self.assertTrue(all(entry["machine"] for entry in languages))

    def test_post__answers_the_translation_without_writing_it(self):
        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day")):
            response = self.api_session.post("/page/@translate", json={"target_language": "en", "text": "Guten Tag"})

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "Good day")

    def test_post__refuses_a_request_that_names_no_language(self):
        response = self.api_session.post("/page/@translate", json={})

        self.assertEqual(response.status_code, 400)

    def test_post__reports_an_unconfigured_site_as_503(self):
        # setup
        _records().api_key = None
        transaction.commit()

        # do it
        response = self.api_session.post("/page/@translate", json={"target_language": "en", "text": "Hallo"})

        # postcondition
        self.assertEqual(response.status_code, 503)
        self.assertIn("API key", response.json()["message"])

    def test_post__translates_the_content_fields_when_asked_for_the_page(self):
        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            response = self.api_session.post("/page/@translate", json={"target_language": "en"})

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["fields"],
            {"title": "Good day", "description": "A page"},
        )
        # Nothing was written without `save`.
        transaction.begin()
        self.assertEqual(self.page.title, "Guten Tag")

    def test_post__saves_in_place_on_a_site_that_has_no_second_language(self):
        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            response = self.api_session.post("/page/@translate", json={"target_language": "en", "save": True})

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        transaction.begin()
        self.assertEqual(self.page.title, "Good day")

    def test_post__stores_plain_text_without_html_entities(self):
        # do it — DeepL reads every text as HTML and answers an apostrophe as
        # an entity
        with mock.patch("requests.post", return_value=_deepl("Good day", "Here&#x27;s a page")):
            self.api_session.post("/page/@translate", json={"target_language": "en", "save": True})

        # postcondition
        transaction.begin()
        self.assertEqual(self.page.description, "Here's a page")

    def test_post__marks_the_page_it_wrote_in_place(self):
        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            self.api_session.post("/page/@translate", json={"target_language": "en", "save": True})

        # postcondition
        transaction.begin()
        marker = IAnnotations(self.page).get(MACHINE_TRANSLATION_KEY)
        self.assertEqual(marker["provider"], "DeepL")
        self.assertEqual(marker["target_language"], "en")

    def test_post__leaves_a_version_the_editor_can_go_back_to(self):
        # setup
        before = len(api.portal.get_tool("portal_repository").getHistory(self.page))

        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            self.api_session.post("/page/@translate", json={"target_language": "en", "save": True})

        # postcondition — a machine translation replaces prose somebody wrote,
        # so the way back has to exist
        transaction.begin()
        history = api.portal.get_tool("portal_repository").getHistory(self.page)
        self.assertEqual(len(history), before + 1)
        self.assertEqual(history[0].comment, "Machine translation into en with DeepL")

    def test_post__records_the_language_the_page_now_holds(self):
        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            self.api_session.post("/page/@translate", json={"target_language": "en", "save": True})

        # postcondition — the page was German and now holds English, and the
        # catalogue and the front end both read that off the field. Nobody
        # else is going to set it: no new object was made here.
        transaction.begin()
        self.assertEqual(self.page.language, "en")

    def test_post__reports_what_it_did(self):
        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            response = self.api_session.post("/page/@translate", json={"target_language": "en", "save": True})

        # postcondition — the editor is shown a report instead of being
        # dropped on the result
        report = response.json()["report"]
        self.assertEqual(report["stored_as"], "in_place")
        self.assertFalse(report["created"])
        self.assertEqual(report["fields"], ["description", "title"])
        self.assertEqual(report["target_language"], "en")

    def test_post__reports_nothing_when_nothing_was_saved(self):
        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            response = self.api_session.post("/page/@translate", json={"target_language": "en"})

        # postcondition — a preview wrote nothing, so there is nothing to report
        self.assertNotIn("report", response.json())

    def test_post__needs_the_permission_to_change_the_page(self):
        # setup
        self.api_session.auth = None

        # do it
        response = self.api_session.post("/page/@translate", json={"target_language": "en"})

        # postcondition
        self.assertEqual(response.status_code, 401)


class TestTranslateServiceOnAMultilingualSite(TestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.portal.portal_workflow.setDefaultChain("simple_publication_workflow")
        # Inside the German language root folder: a page outside one belongs
        # to no language, and there is no sibling to make for it.
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

    def test_get__reports_status_per_language(self):
        # setup
        self._translate()
        transaction.begin()

        # do it
        response = self.api_session.get("/de/page/@translate")

        # postcondition — one entry per language, the page's own included
        translations = response.json()["translations"]
        self.assertEqual(translations["de"]["status"], "manual")
        self.assertEqual(translations["de"]["url"], self.page.absolute_url())
        self.assertEqual(translations["en"]["status"], "machine_unreviewed")
        self.assertIsNone(translations["en"]["working_copy"])

    def test_post__marks_the_sibling_as_machine_translated(self):
        # do it
        self._translate()

        # postcondition — the marker sits on the machine-written sibling, not
        # on the hand-written original
        transaction.begin()
        marker = IAnnotations(self.portal["en"]["page"]).get(MACHINE_TRANSLATION_KEY)
        self.assertEqual(marker["provider"], "DeepL")
        self.assertEqual(marker["source_language"], "de")
        self.assertEqual(marker["target_language"], "en")
        self.assertIsNone(IAnnotations(self.page).get(MACHINE_TRANSLATION_KEY))

    def test_post__marks_the_source_language_it_was_given(self):
        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            self.api_session.post(
                "/de/page/@translate",
                json={"target_language": "en", "source_language": "fr", "save": True},
            )

        # postcondition
        transaction.begin()
        marker = IAnnotations(self.portal["en"]["page"]).get(MACHINE_TRANSLATION_KEY)
        self.assertEqual(marker["source_language"], "fr")

    def test_post__writes_into_the_language_sibling_instead_of_over_the_page(self):
        # do it
        response = self._translate()

        # postcondition — what the editor wrote is still where it was, and
        # the translation is a second page in the other language's folder
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        transaction.begin()
        self.assertEqual(self.page.title, "Guten Tag")
        self.assertEqual(self.portal["en"]["page"].title, "Good day")

    def test_post__gives_the_sibling_the_order_its_blocks_are_shown_in(self):
        # setup — a page whose text lives in blocks, as a Volto page's does
        api.content.create(
            container=self.portal["de"],
            type="Document",
            id="startseite",
            title="Startseite",
            blocks={"b1": {"@type": "slate", "plaintext": "Guten Tag"}},
            blocks_layout={"items": ["b1"]},
        )
        transaction.commit()

        # do it
        with mock.patch("requests.post", return_value=_deepl("Home", "Good day")):
            response = self.api_session.post("/de/startseite/@translate", json={"target_language": "en", "save": True})

        # postcondition — the sibling holds blocks and the order to show them
        # in. With translated blocks and an empty order it would answer every
        # request with a page that renders nothing.
        self.assertEqual(response.status_code, 200)
        transaction.begin()
        sibling = self.portal["en"]["startseite"]
        self.assertEqual(sibling.blocks_layout, {"items": ["b1"]})
        self.assertEqual(set(sibling.blocks), {"b1"})
        self.assertEqual(sibling.blocks["b1"]["plaintext"], "Good day")

    def test_post__gives_each_of_the_two_pages_its_own_language(self):
        # do it
        self._translate()

        # postcondition — plone.app.multilingual sets the new page's language
        # when it creates it, and the page it was made from keeps its own
        transaction.begin()
        self.assertEqual(self.portal["en"]["page"].language, "en")
        self.assertEqual(self.page.language, "de")

    def test_post__reports_the_translation_it_created(self):
        # do it
        response = self._translate()

        # postcondition
        report = response.json()["report"]
        self.assertEqual(report["stored_as"], "translation")
        self.assertTrue(report["created"])
        self.assertEqual(report["title"], "Good day")

    def test_post__refuses_to_replace_an_existing_translation_unasked(self):
        # setup — the sibling exists, and an editor may have worked on it
        self._translate()
        transaction.begin()
        self.portal["en"]["page"].title = "Edited by hand"
        transaction.commit()

        # do it — the same translation again, without asking to overwrite
        response = self._translate()

        # postcondition — refused as a conflict, and the editor's work is
        # still there
        self.assertEqual(response.status_code, 409)
        self.assertIn("already", response.json()["message"])
        transaction.begin()
        self.assertEqual(self.portal["en"]["page"].title, "Edited by hand")

    def test_post__refuses_before_the_provider_is_paid(self):
        # setup
        self._translate()

        # do it — no DeepL mock: a request that reaches the provider fails loudly
        response = self.api_session.post("/de/page/@translate", json={"target_language": "en", "save": True})

        # postcondition — refused without ever calling DeepL
        self.assertEqual(response.status_code, 409)

    def test_post__replaces_the_translation_when_asked_to(self):
        # setup
        self._translate()

        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            response = self.api_session.post(
                "/de/page/@translate", json={"target_language": "en", "save": True, "overwrite": True}
            )

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        transaction.begin()
        self.assertEqual(self.portal["en"]["page"].title, "Good day")

    def test_get__reports_which_languages_already_hold_a_translation(self):
        # setup
        self._translate()

        # do it
        response = self.api_session.get("/de/page/@translate")

        # postcondition — a front end has to know before it lets an editor
        # overwrite somebody's work, and the page's own entry names the page
        # itself, not a translation of it
        translations = response.json()["translations"]
        self.assertIsNotNone(translations["en"]["url"])
        self.assertEqual(translations["de"]["url"], self.page.absolute_url())

    def test_get__reports_no_translations_where_none_exist(self):
        response = self.api_session.get("/de/page/@translate")

        translations = response.json()["translations"]
        self.assertEqual(translations["en"], {"url": None, "status": None, "working_copy": None})

    def test_get__does_not_offer_the_pages_own_language(self):
        # do it
        response = self.api_session.get("/de/page/@translate")

        # postcondition — "de" is what the page already is
        codes = [entry["code"] for entry in response.json()["languages"]]
        self.assertIn("en", codes)
        self.assertNotIn("de", codes)

    def test_get__offers_every_site_language_and_marks_the_machine_ones(self):
        # setup — French is a site language, but not offered for machine translation
        api.portal.get_tool("portal_languages").addSupportedLanguage("fr")
        _records().target_languages = ["en"]
        transaction.commit()

        # do it
        response = self.api_session.get("/de/page/@translate")

        # postcondition
        body = response.json()
        machine = {entry["code"]: entry["machine"] for entry in body["languages"]}
        self.assertEqual(machine, {"en": True, "fr": False})
        self.assertEqual(body["translations"]["fr"], {"url": None, "status": None, "working_copy": None})

    def test_get__drops_target_languages_the_site_does_not_have(self):
        # setup — Italian was offered, then removed from the site
        tool = api.portal.get_tool("portal_languages")
        tool.addSupportedLanguage("it")
        _records().target_languages = ["en", "it"]
        tool.removeSupportedLanguages(["it"])
        transaction.commit()

        # do it
        response = self.api_session.get("/de/page/@translate")

        # postcondition
        codes = [entry["code"] for entry in response.json()["languages"]]
        self.assertEqual(codes, ["en"])

    def test_vocabulary__drops_target_languages_the_site_does_not_have(self):
        # setup — the vocabulary feeds the Classic form and the machine flags;
        # Italian was offered, then removed from the site
        tool = api.portal.get_tool("portal_languages")
        tool.addSupportedLanguage("it")
        _records().target_languages = ["en", "it"]
        tool.removeSupportedLanguages(["it"])
        factory = getUtility(IVocabularyFactory, name="interaktiv.translation.TargetLanguages")

        # do it
        codes = [term.value for term in factory(self.page)]

        # postcondition
        self.assertEqual(codes, ["en"])

    def test_classic_view__shows_the_refusal_it_was_given(self):
        # setup — an English translation already exists
        self._translate()
        transaction.begin()
        request = self.portal.REQUEST
        request.form = {"target_language": "en"}
        view = TranslateContentView(self.portal["de"]["page"], request)
        view.template = mock.Mock(return_value="")

        # do it — ask again without overwrite, through the Classic form
        view.translate()

        # postcondition — the editor reads what refusal() decided, not a
        # generic overwrite hint
        messages = IStatusMessage(request).show()
        self.assertIn("There is already a en translation", messages[-1].message)

    def test_translation_into_the_own_language__is_refused(self):
        # do it — "de" is the language the page itself holds; pam would have
        # answered the page itself as its "translation"
        response = self.api_session.post(
            "/de/page/@translate", json={"target_language": "de", "save": True, "overwrite": True}
        )

        # postcondition — refused before the original was overwritten
        self.assertEqual(response.status_code, 409)
        self.assertIn("already in de", response.json()["message"])
        transaction.begin()
        self.assertEqual(self.page.title, "Guten Tag")

    def test_post__maps_metadata_and_reports_it(self):
        # setup — a mapping table for the keywords, keywords on the page
        _records().metadata_mapping_table = {"subjects": [{"de": "Wert A", "en": "value a"}]}
        self.page.setSubject(("Wert A", "Wert X"))
        transaction.commit()

        # do it
        response = self._translate()

        # postcondition — mapped where the table knows the value, carried
        # over unchanged where it does not, and the report says which is which
        transaction.begin()
        translation = self.portal["en"]["page"]
        self.assertEqual(tuple(translation.Subject()), ("value a", "Wert X"))
        self.assertEqual(
            response.json()["report"]["metadata"],
            [
                {"field": "subjects", "before": "Wert A", "after": "value a"},
                {"field": "subjects", "before": "Wert X", "after": None},
            ],
        )

    def test_post__carries_the_chosen_fields_over_and_reports_them(self):
        # setup
        _records().metadata_selection = {"Document": ["subjects", "exclude_from_nav"]}
        self.page.setSubject(("Wert A", "Wert B"))
        self.page.exclude_from_nav = True
        transaction.commit()

        # do it
        response = self._translate()

        # postcondition — taken over as they are, named in the report
        transaction.begin()
        translation = self.portal["en"]["page"]
        self.assertEqual(tuple(translation.Subject()), ("Wert A", "Wert B"))
        self.assertTrue(translation.exclude_from_nav)
        self.assertCountEqual(response.json()["report"]["copied"], ["subjects", "exclude_from_nav"])

    def test_post__carries_over_nothing_that_was_not_chosen(self):
        # setup
        self.page.setSubject(("Wert A",))
        transaction.commit()

        # do it
        response = self._translate()

        # postcondition
        transaction.begin()
        self.assertEqual(tuple(self.portal["en"]["page"].Subject()), ())
        self.assertEqual(response.json()["report"]["copied"], [])

    def test_post__translates_a_chosen_text_field(self):
        # setup
        _records().metadata_selection = {"Document": ["rights"]}
        self.page.rights = "Rechte"
        transaction.commit()

        # do it
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page", "Rights")):
            response = self.api_session.post("/de/page/@translate", json={"target_language": "en", "save": True})

        # postcondition
        self.assertEqual(response.status_code, 200)
        transaction.begin()
        self.assertEqual(self.portal["en"]["page"].rights, "Rights")

    def test_post__does_not_take_metadata_over_from_the_folder(self):
        # setup — the fields sit on the language folder, not on the page
        _records().metadata_selection = {"Document": ["field_a"]}
        _records().metadata_mapping_table = {"field_b": [{"de": "Wert B", "en": "value b"}]}
        self.portal["de"].field_a = "Wert A"
        self.portal["de"].field_b = "Wert B"
        transaction.commit()

        # do it
        response = self._translate()

        # postcondition — nothing acquired, nothing written, nothing reported
        transaction.begin()
        translation = aq_base(self.portal["en"]["page"])
        self.assertFalse(hasattr(translation, "field_a"))
        self.assertFalse(hasattr(translation, "field_b"))
        self.assertEqual(response.json()["report"]["copied"], [])
        self.assertEqual(response.json()["report"]["metadata"], [])


class TestWorkingCopyStorage(TestCase):
    """A multilingual site with plone.app.iterate installed: an existing
    translation is checked out, not overwritten."""

    layer = INTERAKTIV_TRANSLATION_WORKING_COPY_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.portal.portal_workflow.setDefaultChain("simple_publication_workflow")
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

    def _translate(self, **body):
        payload = {"target_language": "en", "save": True}
        payload.update(body)
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            return self.api_session.post("/de/page/@translate", json=payload)

    def _working_copy_of(self, translation):
        from plone.app.iterate.interfaces import ICheckinCheckoutPolicy

        return ICheckinCheckoutPolicy(translation).getWorkingCopy()

    def test_first_translation__is_created_without_a_working_copy(self):
        # do it — nothing to protect yet, so the translation is made directly
        response = self._translate()

        # postcondition
        self.assertEqual(response.status_code, 200)
        transaction.begin()
        translation = self.portal["en"]["page"]
        self.assertEqual(translation.title, "Good day")
        self.assertIsNone(self._working_copy_of(translation))

    def test_second_translation__lands_in_a_working_copy_not_the_live_one(self):
        # setup — a translation exists and an editor has worked on it
        self._translate()
        transaction.begin()
        self.portal["en"]["page"].title = "Edited by hand"
        transaction.commit()

        # do it — translate again; iterate is on, so no overwrite is needed
        response = self._translate()

        # postcondition — the live translation is untouched, and the machine
        # translation sits in a working copy waiting to be checked in
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        transaction.begin()
        translation = self.portal["en"]["page"]
        self.assertEqual(translation.title, "Edited by hand")
        working_copy = self._working_copy_of(translation)
        self.assertIsNotNone(working_copy)
        self.assertEqual(working_copy.title, "Good day")

    def test_translation_into_the_own_language__checks_nothing_out(self):
        # do it — with iterate on, the "existing translation" pam answers is
        # the original itself, and translating would check it out
        response = self.api_session.post("/de/page/@translate", json={"target_language": "de", "save": True})

        # postcondition — refused, and the original stands untouched
        self.assertEqual(response.status_code, 409)
        transaction.begin()
        self.assertIsNone(self._working_copy_of(self.portal["de"]["page"]))

    def test_second_translation__is_refused_while_the_translation_is_locked(self):
        # setup — a translation exists and an editor is working on it right
        # now, holding a lock
        from plone.locking.interfaces import ILockable

        self._translate()
        transaction.begin()
        ILockable(self.portal["en"]["page"]).lock()
        transaction.commit()

        # do it
        response = self._translate()

        # postcondition — refused before a checkout would have cleared the
        # editor's lock and thrown their unsaved work away
        self.assertEqual(response.status_code, 409)
        self.assertIn("being edited by someone", response.json()["message"])
        transaction.begin()
        self.assertIsNone(self._working_copy_of(self.portal["en"]["page"]))

    def test_second_translation__names_a_missing_checkout_permission(self):
        # setup — a translation exists, but nobody may check it out
        from AccessControl.Permission import Permission
        from plone.app.iterate.permissions import CheckoutPermission

        self._translate()
        transaction.begin()
        Permission(CheckoutPermission, (), self.portal["en"]["page"]).setRoles(())
        transaction.commit()

        # do it
        response = self._translate()

        # postcondition — the refusal names the permission, not a lock
        self.assertEqual(response.status_code, 409)
        self.assertIn("not allowed to check out", response.json()["message"])
        transaction.begin()
        self.assertIsNone(self._working_copy_of(self.portal["en"]["page"]))

    def test_second_translation__says_why_the_baseline_was_snapshotted(self):
        # setup — a translation exists and an editor has worked on it since
        self._translate()
        transaction.begin()
        self.portal["en"]["page"].title = "Edited by hand"
        transaction.commit()

        # do it
        self._translate()

        # postcondition — the checkout snapshot names its reason instead of
        # iterate's stock "Baseline created"
        transaction.begin()
        history = api.portal.get_tool("portal_repository").getHistory(self.portal["en"]["page"])
        self.assertEqual(history[0].comment, "Baseline before machine translation into en with DeepL")

    def _working_copy_path(self):
        transaction.begin()
        working_copy = self._working_copy_of(self.portal["en"]["page"])

        return "/" + "/".join(working_copy.getPhysicalPath()[2:])

    def test_post__on_a_working_copy_is_refused(self):
        # setup — a translation and its working copy
        self._translate()
        self._translate()
        working_copy_path = self._working_copy_path()

        # do it — preview and save alike, no overwrite makes this valid; the
        # revoked pam permission answers before our own guard does
        preview = self.api_session.post(f"{working_copy_path}/@translate", json={"target_language": "de"})
        save = self.api_session.post(
            f"{working_copy_path}/@translate",
            json={"target_language": "de", "save": True, "overwrite": True},
        )

        # postcondition — and the storage guard stands behind it for copies
        # made before the permission subscriber existed
        self.assertEqual(preview.status_code, 401)
        self.assertEqual(save.status_code, 401)
        transaction.begin()
        working_copy = self._working_copy_of(self.portal["en"]["page"])
        refusal = TranslationStorage(working_copy).refusal("de", overwrite=True)
        self.assertIn("working copy", refusal)

    def test_get__points_a_working_copy_at_its_original(self):
        # setup
        self._translate()
        self._translate()
        working_copy_path = self._working_copy_path()

        # do it
        response = self.api_session.get(f"{working_copy_path}/@translate")

        # postcondition
        body = response.json()
        self.assertTrue(body["is_working_copy"])
        self.assertEqual(body["baseline_url"], self.portal["en"]["page"].absolute_url())

    def test_get__the_original_is_no_working_copy(self):
        # setup
        self._translate()
        transaction.begin()

        # do it
        response = self.api_session.get("/en/page/@translate")

        # postcondition
        body = response.json()
        self.assertFalse(body["is_working_copy"])
        self.assertIsNone(body["baseline_url"])

    def test_available_view__answers_false_on_a_working_copy(self):
        # setup
        self._translate()
        self._translate()
        transaction.begin()
        working_copy = self._working_copy_of(self.portal["en"]["page"])

        # do it / postcondition — the edit-bar condition hides the button
        request = self.layer["request"]
        self.assertFalse(api.content.get_view("translation-available", working_copy, request)())
        self.assertTrue(api.content.get_view("translation-available", self.page, request)())

    def test_link_translations__on_a_working_copy_is_refused(self):
        # setup — the stock pam road: POST @translations links content; the
        # checkout revoked pam's permission on the copy, so the road is shut
        self._translate()
        self._translate()
        working_copy_path = self._working_copy_path()

        # do it
        response = self.api_session.post(
            f"{working_copy_path}/@translations",
            json={"id": self.page.absolute_url()},
        )

        # postcondition — denied for everyone, the admin included
        self.assertEqual(response.status_code, 401)

    def test_translation_locator__on_a_working_copy_is_refused(self):
        # setup — the stock road of a hand-made translation starts at the
        # locator; denied here, no orphan content is ever created
        self._translate()
        self._translate()
        working_copy_path = self._working_copy_path()

        # do it
        refused = self.api_session.get(f"{working_copy_path}/@translation-locator", params={"target_language": "de"})
        allowed = self.api_session.get("/en/page/@translation-locator", params={"target_language": "de"})

        # postcondition — the original keeps the stock behaviour
        self.assertEqual(refused.status_code, 401)
        self.assertEqual(allowed.status_code, 200)

    def test_checkout__revokes_translation_management_on_the_copy(self):
        # setup
        from AccessControl import getSecurityManager

        from interaktiv.translation.subscribers.events import MANAGE_TRANSLATIONS_PERMISSION

        self._translate()
        self._translate()
        transaction.begin()
        translation = self.portal["en"]["page"]
        working_copy = self._working_copy_of(translation)

        # postcondition — nobody translates the copy, the original is free
        with api.env.adopt_user(SITE_OWNER_NAME):
            security = getSecurityManager()
            self.assertFalse(security.checkPermission(MANAGE_TRANSLATIONS_PERMISSION, working_copy))
            self.assertTrue(security.checkPermission(MANAGE_TRANSLATIONS_PERMISSION, translation))

    def test_get__names_the_open_working_copy_per_language(self):
        # setup — a translation and a working copy holding the next one
        self._translate()
        self._translate()
        transaction.begin()

        # do it
        response = self.api_session.get("/de/page/@translate")

        # postcondition
        entry = response.json()["translations"]["en"]
        self.assertEqual(entry["status"], "machine_unreviewed")
        self.assertIsNotNone(entry["working_copy"])
        self.assertIn("copy_of_page", entry["working_copy"]["url"])
        self.assertEqual(entry["working_copy"]["status"], "machine_unreviewed")

    def test_third_translation__is_refused_while_a_working_copy_stands(self):
        # setup — a translation and its working copy both exist
        self._translate()
        self._translate()

        # do it
        response = self._translate()

        # postcondition
        self.assertEqual(response.status_code, 409)
        self.assertIn("working copy", response.json()["message"])

    def test_overwrite__leaves_the_standing_working_copy_alone(self):
        # setup
        self._translate()
        self._translate()
        transaction.begin()
        working_copy = self._working_copy_of(self.portal["en"]["page"])
        title = working_copy.title

        # do it
        with mock.patch("requests.post", return_value=_deepl("Hello again", "A page")) as deepl:
            response = self.api_session.post(
                "/de/page/@translate",
                json={"target_language": "en", "save": True, "overwrite": True},
            )

        # postcondition — refused before DeepL is asked, the working copy unchanged
        self.assertEqual(response.status_code, 409)
        self.assertIn("working copy", response.json()["message"])
        deepl.assert_not_called()
        transaction.begin()
        self.assertEqual(self._working_copy_of(self.portal["en"]["page"]).title, title)

    def test_post__reports_that_it_used_a_working_copy(self):
        # setup — a translation exists, so the next run goes to a working copy
        self._translate()

        # do it
        response = self._translate()

        # postcondition
        report = response.json()["report"]
        self.assertEqual(report["stored_as"], "working_copy")
        self.assertTrue(report["created"])

    def test_get__reports_the_working_copy_state(self):
        # setup
        self._translate()

        # do it — before a working copy exists
        first = self.api_session.get("/de/page/@translate").json()

        # postcondition — the feature is on, no working copy yet
        self.assertTrue(first["working_copies_enabled"])
        self.assertIsNotNone(first["translations"]["en"]["url"])
        self.assertIsNone(first["translations"]["en"]["working_copy"])

        # once a second translation has made a working copy, it is reported
        self._translate()
        second = self.api_session.get("/de/page/@translate").json()
        self.assertIsNotNone(second["translations"]["en"]["working_copy"])


class TestControlPanels(TestCase):
    layer = INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        transaction.commit()

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def test_patch__refuses_a_mapping_with_a_wrong_language(self):
        # do it
        response = self.api_session.patch(
            "/@controlpanels/translation",
            json={"metadata_mapping_table": {"field_a": [{"de": "Wert A", "Deutsch": "Wert B"}]}},
        )

        # postcondition — the editor reads what is wrong, nothing is stored
        self.assertEqual(response.status_code, 400)
        self.assertIn("no language code", response.text)
        transaction.begin()
        self.assertFalse(_records().metadata_mapping_table)

    def test_patch__refuses_a_mapping_of_the_wrong_shape(self):
        # do it — a field holds a list of rows, not a single row
        response = self.api_session.patch(
            "/@controlpanels/translation",
            json={"metadata_mapping_table": {"field_a": {"de": "Wert A", "en": "value a"}}},
        )

        # postcondition
        self.assertEqual(response.status_code, 400)
        transaction.begin()
        self.assertFalse(_records().metadata_mapping_table)

    def test_patch__accepts_a_well_formed_mapping(self):
        # setup
        mapping = {"field_a": [{"de": "Wert A", "en": "value a"}, {"de": "Wert B"}]}

        # do it
        response = self.api_session.patch("/@controlpanels/translation", json={"metadata_mapping_table": mapping})

        # postcondition — stored as it came, read back the same way
        self.assertEqual(response.status_code, 204)
        transaction.begin()
        self.assertEqual(_records().metadata_mapping_table, mapping)
        response = self.api_session.get("/@controlpanels/translation")
        self.assertEqual(response.json()["data"]["metadata_mapping_table"], mapping)

    def test_patch__accepts_a_selection_of_fields_per_type(self):
        # setup
        selection = {"type_a": ["field_a", "field_b"], "type_b": []}

        # do it
        response = self.api_session.patch("/@controlpanels/translation", json={"metadata_selection": selection})

        # postcondition
        self.assertEqual(response.status_code, 204)
        transaction.begin()
        self.assertEqual(_records().metadata_selection, selection)

    def test_patch__refuses_a_selection_of_the_wrong_shape(self):
        for selection in ({"type_a": "field_a"}, {"type_a": ["field_a", "field_a"]}, {"type_a": [""]}):
            with self.subTest(selection=selection):
                # do it
                response = self.api_session.patch("/@controlpanels/translation", json={"metadata_selection": selection})

                # postcondition
                self.assertEqual(response.status_code, 400)
                transaction.begin()
                self.assertFalse(_records().metadata_selection)

    def test_get__shows_a_type_the_site_no_longer_has(self):
        # setup — stored while the type was there; it went away since
        records = getUtility(IRegistry).records
        records._values[f"{ITranslationSettings.__identifier__}.excluded_types"] = ["Image", "type_unknown"]
        transaction.commit()

        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition — kept and shown, so saving the form loses nothing
        self.assertEqual(response.status_code, 200)
        tokens = [entry["token"] for entry in response.json()["data"]["excluded_types"]]
        self.assertEqual(tokens, ["Image", "type_unknown"])

    def test_get__shows_a_target_language_the_site_no_longer_has(self):
        # setup — offered while the site had it; the language went away since
        records = getUtility(IRegistry).records
        records._values[f"{ITranslationSettings.__identifier__}.target_languages"] = ["language_unknown"]
        transaction.commit()

        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition — kept and shown, to be chosen off
        self.assertEqual(response.status_code, 200)
        tokens = [entry["token"] for entry in response.json()["data"]["target_languages"]]
        self.assertEqual(tokens, ["language_unknown"])

    def test_patch__accepts_a_type_the_site_has(self):
        # do it
        response = self.api_session.patch("/@controlpanels/translation", json={"excluded_types": ["Image"]})

        # postcondition
        self.assertEqual(response.status_code, 204)
        transaction.begin()
        self.assertEqual(_records().excluded_types, ["Image"])

    def test_configlet__is_installed_for_classic(self):
        action_ids = [action.getId() for action in api.portal.get_tool("portal_controlpanel").listActions()]

        self.assertIn("translation_controlpanel", action_ids)

    def test_volto_panel__serves_the_same_records(self):
        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertIn("api_key", response.json()["schema"]["properties"])
        self.assertIsNone(response.json()["data"]["api_key"])

    def test_volto_panel__never_hands_out_the_api_key(self):
        # setup
        _records().api_key = "key-value-a"
        transaction.commit()

        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition — that a key is stored, not which
        self.assertEqual(response.json()["data"]["api_key"], API_KEY_PLACEHOLDER)
        self.assertNotIn("key-value-a", response.text)

    def test_patch__keeps_the_api_key_for_the_placeholder(self):
        # setup
        _records().api_key = "key-value-a"
        transaction.commit()

        # do it — the form comes back as it was shown
        response = self.api_session.patch("/@controlpanels/translation", json={"api_key": API_KEY_PLACEHOLDER})

        # postcondition
        self.assertEqual(response.status_code, 204)
        transaction.begin()
        self.assertEqual(Settings().api_key, "key-value-a")
        self.assertTrue(is_encrypted(_records().api_key))

    def test_patch__takes_a_new_api_key(self):
        # setup
        _records().api_key = "key-value-a"
        transaction.commit()

        # do it
        response = self.api_session.patch("/@controlpanels/translation", json={"api_key": "key-value-b"})

        # postcondition
        self.assertEqual(response.status_code, 204)
        transaction.begin()
        self.assertEqual(Settings().api_key, "key-value-b")
        self.assertTrue(is_encrypted(_records().api_key))

    def test_patch__removes_the_api_key_for_an_empty_value(self):
        # setup
        _records().api_key = "key-value-a"
        transaction.commit()

        # do it
        response = self.api_session.patch("/@controlpanels/translation", json={"api_key": ""})

        # postcondition
        self.assertEqual(response.status_code, 204)
        transaction.begin()
        self.assertFalse(_records().api_key)

    def test_volto_panel__names_the_widget_of_the_api_key(self):
        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition — the front end picks the widget with the connection test by this name
        field = response.json()["schema"]["properties"]["api_key"]
        self.assertEqual(field["widgetOptions"]["frontendOptions"]["widget"], "translation_api_key")

    def test_mail_panel__keeps_its_own_password_field(self):
        # setup — another password field of the site is none of the add-on's business
        api.portal.set_registry_record("plone.smtp_pass", "password-a")
        transaction.commit()

        # do it
        response = self.api_session.get("/@controlpanels/mail")

        # postcondition
        self.assertEqual(response.json()["data"]["smtp_pass"], "password-a")

    def test_volto_panel__names_the_widget_of_the_metadata_mapping(self):
        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition — the front end picks its mapping widget by this name
        field = response.json()["schema"]["properties"]["metadata_mapping_table"]
        self.assertEqual(field["widget"], "translation_metadata_mapping")
        self.assertEqual(field["type"], "dict")
        self.assertEqual(field["factory"], "JSONField")

    def test_volto_panel__offers_the_site_languages_as_target_languages(self):
        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition — the front end fills its selection from the site languages
        field = response.json()["schema"]["properties"]["target_languages"]
        self.assertTrue(
            field["items"]["vocabulary"]["@id"].endswith("@vocabularies/interaktiv.translation.SiteLanguages")
        )
        languages = self.api_session.get("/@vocabularies/interaktiv.translation.SiteLanguages")
        self.assertEqual(languages.status_code, 200)
        self.assertTrue(languages.json()["items"])

    def test_volto_panel__offers_the_content_types_to_leave_out(self):
        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition
        field = response.json()["schema"]["properties"]["excluded_types"]
        self.assertTrue(
            field["items"]["vocabulary"]["@id"].endswith("@vocabularies/interaktiv.translation.ContentTypes")
        )
        types = self.api_session.get("/@vocabularies/interaktiv.translation.ContentTypes")
        self.assertEqual(types.status_code, 200)
        self.assertIn("Document", [item["token"] for item in types.json()["items"]])

    def test_volto_panel__has_no_source_language_setting(self):
        # do it
        response = self.api_session.get("/@controlpanels/translation")

        # postcondition — the source language is the site's default language
        self.assertNotIn("default_source_language", response.json()["schema"]["properties"])

    def test_patch__refuses_a_target_language_the_site_does_not_have(self):
        # do it
        response = self.api_session.patch("/@controlpanels/translation", json={"target_languages": ["it"]})

        # postcondition
        self.assertEqual(response.status_code, 400)
        transaction.begin()
        self.assertEqual(_records().target_languages, [])

    def test_patch__accepts_a_site_language_as_target_language(self):
        # setup
        api.portal.get_tool("portal_languages").addSupportedLanguage("it")
        transaction.commit()

        # do it
        response = self.api_session.patch("/@controlpanels/translation", json={"target_languages": ["it"]})

        # postcondition
        self.assertEqual(response.status_code, 204)
        transaction.begin()
        self.assertEqual(_records().target_languages, ["it"])

    def test_volto_panel__writes_the_key(self):
        # do it
        response = self.api_session.patch("/@controlpanels/translation", json={"api_key": "abc:fx"})

        # postcondition
        self.assertEqual(response.status_code, 204)
        transaction.begin()
        self.assertEqual(Settings().api_key, "abc:fx")
        self.assertTrue(is_encrypted(_records().api_key))

    def test_classic_form__is_reachable_for_a_manager(self):
        view = self.get_view("translation-controlpanel", self.portal)

        self.assertIsNotNone(view)


class TestSettingsSourceLanguage(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def test_default_source_language__is_the_site_default_language(self):
        # setup
        api.portal.set_registry_record("plone.default_language", "it")

        # do it / postcondition
        self.assertEqual(Settings().default_source_language, "it")


class TestActionCondition(TestCase):
    layer = INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.page = api.content.create(container=self.portal, type="Document", id="page", title="Seite")

    def _evaluate(self):
        from Products.CMFCore.Expression import Expression, getExprContext

        category = api.portal.get_tool("portal_actions")["object_buttons"]
        action = [a for a in category.objectValues() if a.getId() == "translate"][0]
        expression = Expression(action.getProperty("available_expr"))

        return expression(getExprContext(self.portal, self.page))

    def test_condition__evaluates_where_it_actually_runs(self):
        # The condition is TALES in restricted Python, and reading an
        # attribute off a view there raises "the container has no security
        # assertions" — which only shows up when the action is really
        # evaluated, never when the expression is merely read.
        # do it — unconfigured, so the entry stays out of both edit bars
        available = self._evaluate()

        # postcondition
        self.assertFalse(available)

    def test_condition__is_true_once_a_key_is_configured(self):
        # setup
        _records().api_key = "abc:fx"

        # do it
        available = self._evaluate()

        # postcondition
        self.assertTrue(available)


class TestCsrf(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def setUp(self) -> None:
        super().setUp()
        api.user.grant_roles(username=TEST_USER_ID, roles=["Manager"])
        self.page = api.content.create(
            container=self.portal, type="Document", id="page", title="Guten Tag", description="Eine Seite"
        )
        _records().api_key = "test-key"

    def _reply(self, body):
        request = self.layer["request"]
        request["BODY"] = json.dumps(body).encode("utf-8")
        # plone.rest builds its services as views and assigns the two
        # attributes rather than passing them to a constructor.
        service = TranslatePost()
        service.context = self.page
        service.request = request
        with mock.patch("requests.post", return_value=_deepl("Good day", "A page")):
            service.reply()

        return request

    def test_reply__stands_down_csrf_for_the_request_that_writes(self):
        # A REST client carries no form token, so plone.protect would roll the
        # store back and leave the service answering `saved` for nothing. The
        # functional layer does not run that transform, which is why this is
        # asserted on the request rather than on the page.
        request = self._reply({"target_language": "en", "save": True})

        self.assertTrue(IDisableCSRFProtection.providedBy(request))

    def test_reply__leaves_csrf_alone_when_nothing_is_written(self):
        request = self._reply({"target_language": "en"})

        self.assertFalse(IDisableCSRFProtection.providedBy(request))


class TestExcludedTypes(TestCase):
    """A content type named in the control panel is never translated by
    machine."""

    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.image = api.content.create(container=self.portal["de"], type="Image", id="image", title="Bild")
        _records().api_key = "test-key"
        _records().excluded_types = ["Image"]
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        transaction.commit()

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def _translate(self, **body):
        payload = {"target_language": "en"}
        payload.update(body)
        with mock.patch("requests.post", return_value=_deepl("Picture")) as post:
            return self.api_session.post("/de/image/@translate", json=payload), post

    def test_post__refuses_an_image_before_the_provider_is_called(self):
        # do it
        response, post = self._translate(save=True)

        # postcondition — no call, no half-made translation without its file
        self.assertEqual(response.status_code, 409)
        self.assertIn("not translated by machine", response.json()["message"])
        post.assert_not_called()
        transaction.begin()
        self.assertNotIn("image", self.portal["en"].objectIds())

    def test_post__refuses_a_preview_as_well(self):
        response, post = self._translate()

        self.assertEqual(response.status_code, 409)
        post.assert_not_called()

    def test_get__reports_the_type_as_not_translatable(self):
        response = self.api_session.get("/de/image/@translate")

        self.assertFalse(response.json()["translatable"])

    def test_available_view__hides_the_action_for_an_image(self):
        transaction.begin()
        view = TranslationAvailableView(self.portal["de"]["image"], self.portal.REQUEST)

        self.assertFalse(view())

    def test_an_emptied_setting__lets_images_be_translated(self):
        # setup — the list is a project decision, empty means every type
        _records().excluded_types = []
        transaction.commit()

        # do it
        response, post = self._translate()

        # postcondition
        self.assertEqual(response.status_code, 200)
        post.assert_called_once()


class TestImagesAndFiles(TestCase):
    """An image or a file is translated like a page; its file, the type's
    main field, always comes along as a copy of its own."""

    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.image = api.content.create(
            container=self.portal["de"],
            type="Image",
            id="image",
            title="Bild",
            image=NamedBlobImage(data=GIF, contentType="image/gif", filename="bild.gif"),
        )
        self.file = api.content.create(
            container=self.portal["de"],
            type="File",
            id="file",
            title="Datei",
            file=NamedBlobFile(data=b"Inhalt", contentType="text/plain", filename="datei.txt"),
        )
        _records().api_key = "test-key"
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        transaction.commit()

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def _translate(self, path, answer):
        with mock.patch("requests.post", return_value=_deepl(answer)):
            return self.api_session.post(f"{path}/@translate", json={"target_language": "en", "save": True})

    def test_post__translates_an_image_and_copies_its_file(self):
        # do it
        response = self._translate("/de/image", "Picture")

        # postcondition — the title translated, the image the same data in a
        # file of its own
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report"]["copied"], ["image"])
        transaction.begin()
        translation = self.portal["en"]["image"]
        self.assertEqual(translation.title, "Picture")
        self.assertEqual(translation.image.data, GIF)
        self.assertEqual(translation.image.filename, "bild.gif")
        self.assertIsNot(aq_base(translation.image), aq_base(self.portal["de"]["image"].image))

    def test_post__translates_a_file_and_copies_its_file(self):
        # do it
        response = self._translate("/de/file", "File")

        # postcondition
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report"]["copied"], ["file"])
        transaction.begin()
        translation = self.portal["en"]["file"]
        self.assertEqual(translation.title, "File")
        self.assertEqual(translation.file.data, b"Inhalt")
        self.assertEqual(translation.file.contentType, "text/plain")
        self.assertIsNot(aq_base(translation.file), aq_base(self.portal["de"]["file"].file))
