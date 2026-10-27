import transaction
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD

from interaktiv.translation.helpers.field_selection import (
    EXCLUDED_TYPES,
    EXCLUDED_FIELDS,
    FieldRules,
    MODE_COPY,
    MODE_MAPPING,
    MODE_TRANSLATE,
    REASON_PRIMARY,
    ROLE_ALWAYS,
    ROLE_IMPOSSIBLE,
    get_handled_fields,
)
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING,
    INTERAKTIV_TRANSLATION_INTEGRATION_TESTING,
    INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING,
    RelativeSession,
    TestCase,
)
from interaktiv.translation.tests.test_integration import _records


class TranslationFieldsTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def _types(self):
        response = self.api_session.get("/@translation-fields")
        self.assertEqual(response.status_code, 200)

        return {entry["id"]: entry for entry in response.json()["types"]}

    def _fields(self, portal_type):
        return {field["id"]: field for field in self._types()[portal_type]["fields"]}


class TestTranslationFieldsGet(TranslationFieldsTestCase):
    layer = INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING

    def test_get__is_for_site_managers_only(self):
        # setup
        self.api_session.auth = None

        # do it
        response = self.api_session.get("/@translation-fields")

        # postcondition
        self.assertEqual(response.status_code, 401)

    def test_get__lists_the_types_an_editor_adds(self):
        # do it
        types = self._types()

        # postcondition
        self.assertIn("Document", types)
        self.assertIn("Image", types)
        self.assertTrue(types["Document"]["title"])

    def test_get__leaves_out_the_types_not_translated(self):
        # setup
        _records().excluded_types = ["Image"]
        transaction.commit()

        # do it
        types = self._types()

        # postcondition
        self.assertNotIn("Image", types)
        self.assertIn("Document", types)

    def test_get__lists_the_fields_in_the_order_of_the_edit_form(self):
        # do it
        fields = self._types()["Document"]["fields"]

        # postcondition
        self.assertEqual(fields[0]["id"], "title")
        self.assertEqual(fields[0]["fieldset"], "default")
        self.assertEqual(
            set(fields[0]),
            {"id", "title", "fieldset", "kind", "role", "mode", "reason", "mapped"},
        )

    def test_get__puts_the_page_content_after_title_and_description(self):
        # do it
        fields = self._types()["Event"]["fields"]

        # postcondition — "text" comes later in the edit form of an event
        self.assertEqual([field["id"] for field in fields[:3]], ["title", "description", "text"])

    def test_get__leaves_out_the_excluded_fields(self):
        # do it
        fields = self._fields("Document")

        # postcondition
        self.assertFalse(set(EXCLUDED_FIELDS) & set(fields))

    def test_get__title_always_goes_along_translated(self):
        # do it
        title = self._fields("Document")["title"]

        # postcondition
        self.assertEqual((title["role"], title["mode"]), (ROLE_ALWAYS, MODE_TRANSLATE))

    def test_get__a_reference_cannot_go_along(self):
        # do it
        related = self._fields("Document")["relatedItems"]

        # postcondition
        self.assertEqual((related["role"], related["mode"]), (ROLE_IMPOSSIBLE, None))

    def test_get__the_image_of_an_image_always_goes_along(self):
        # do it
        image = self._fields("Image")["image"]

        # postcondition
        self.assertEqual(
            (image["role"], image["mode"], image["reason"]),
            (ROLE_ALWAYS, MODE_COPY, REASON_PRIMARY),
        )

    def test_get__tells_a_field_of_the_mapping_and_keeps_its_own_mode(self):
        # setup
        _records().metadata_mapping_table = {"subjects": [{"de": "Wert A", "en": "Value A"}]}
        transaction.commit()

        # do it
        subjects = self._fields("Document")["subjects"]

        # postcondition — the control panel decides with the mapping it edits
        self.assertTrue(subjects["mapped"])
        self.assertEqual(subjects["mode"], MODE_COPY)

    def test_get__a_mapped_field_without_values_is_not_mapped(self):
        # setup
        _records().metadata_mapping_table = {"subjects": []}
        transaction.commit()

        # do it
        subjects = self._fields("Document")["subjects"]

        # postcondition
        self.assertFalse(subjects["mapped"])

    def test_get__a_reference_is_never_mapped(self):
        # setup
        _records().metadata_mapping_table = {"relatedItems": [{"de": "Wert A", "en": "Value A"}]}
        transaction.commit()

        # do it
        related = self._fields("Document")["relatedItems"]

        # postcondition
        self.assertFalse(related["mapped"])

    def test_get__goes_by_the_field_lists_of_the_site(self):
        # setup — the site leaves out "rights", takes "location" over, always translates "contact_name"
        _records().excluded_fields = list(EXCLUDED_FIELDS) + ["rights"]
        _records().copied_fields = ["location"]
        _records().always_fields = ["title", "contact_name"]
        transaction.commit()

        # do it
        event = self._fields("Event")

        # postcondition
        self.assertNotIn("rights", event)
        self.assertEqual(event["location"]["mode"], MODE_COPY)
        self.assertEqual(event["contact_name"]["role"], ROLE_ALWAYS)
        self.assertEqual(list(event)[:2], ["title", "contact_name"])
        # no longer named: back to its kind of field
        self.assertEqual(event["contact_email"]["mode"], MODE_TRANSLATE)


class TestTranslationFieldsGetMultilingual(TranslationFieldsTestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def test_get__leaves_out_the_language_folders(self):
        # do it
        types = self._types()

        # postcondition
        self.assertFalse(set(EXCLUDED_TYPES) & set(types))
        self.assertIn("Document", types)

    def test_vocabulary__leaves_out_the_language_folders(self):
        # do it
        response = self.api_session.get("/@vocabularies/interaktiv.translation.ContentTypes")

        # postcondition
        tokens = [item["token"] for item in response.json()["items"]]
        self.assertFalse(set(EXCLUDED_TYPES) & set(tokens))
        self.assertIn("Document", tokens)

    def test_get__copies_what_plone_app_multilingual_keeps_language_independent(self):
        # do it
        start = self._fields("Event")["start"]

        # postcondition
        self.assertEqual((start["mode"], start["reason"]), (MODE_COPY, "language_independent"))


class TestHandledFields(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def test_handled_fields__without_a_choice_takes_what_always_goes_along(self):
        # do it
        modes = get_handled_fields("Document", {})

        # postcondition
        self.assertEqual(list(modes)[:3], ["title", "description", "text"])
        self.assertNotIn("subjects", modes)

    def test_handled_fields__takes_the_chosen_fields_by_their_mode(self):
        # do it
        modes = get_handled_fields("Document", {"Document": ["subjects", "rights"]})

        # postcondition
        self.assertEqual(modes["subjects"], MODE_COPY)
        self.assertEqual(modes["rights"], MODE_TRANSLATE)

    def test_handled_fields__a_mapped_field_goes_along_unchosen(self):
        # do it
        modes = get_handled_fields("Document", {}, mapped_fields=["subjects"])

        # postcondition
        self.assertEqual(modes["subjects"], MODE_MAPPING)

    def test_handled_fields__never_takes_an_excluded_field_or_a_reference(self):
        # do it
        modes = get_handled_fields("Document", {"Document": ["id", "relatedItems"]})

        # postcondition
        self.assertNotIn("id", modes)
        self.assertNotIn("relatedItems", modes)

    def test_handled_fields__ignores_the_choice_of_another_type(self):
        # do it
        modes = get_handled_fields("Document", {"Event": ["subjects"]})

        # postcondition
        self.assertNotIn("subjects", modes)

    def test_handled_fields__goes_by_the_rules_given(self):
        # do it
        modes = get_handled_fields(
            "Document", {"Document": ["rights"]}, rules=FieldRules(excluded=("rights",), always=("title",), copied=())
        )

        # postcondition — "text", the main field of a page, goes along all the same
        self.assertEqual(list(modes), ["title", "text"])

    def test_handled_fields__translates_the_title_of_a_type_dexterity_does_not_know(self):
        self.assertEqual(get_handled_fields("type_unknown", {})["title"], MODE_TRANSLATE)
