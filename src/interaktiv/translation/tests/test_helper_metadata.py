from unittest import TestCase, mock

from zope.interface import Invalid
from zope.schema.interfaces import WrongContainedType

from interaktiv.translation.helpers.metadata import parse_metadata_mapping, validate_metadata_mapping
from interaktiv.translation.registry.translation import ITranslationSettings
from interaktiv.translation.settings import Settings

MAPPING = {
    "field_a": [
        {"de": "Wert A", "en": "value a", "fr": "valeur a"},
        {"de": "Wert B", "en": "value b", "fr": "valeur b"},
    ],
    "field_b": [
        {"de": "Wert C", "en": "value c"},
    ],
}


class TestParseMetadataMapping(TestCase):
    def test_parse__reads_one_direction_for_every_field(self):
        # do it
        mapping = parse_metadata_mapping(MAPPING, "de", "en")

        # postcondition
        self.assertEqual(
            mapping,
            {
                "field_a": {"Wert A": "value a", "Wert B": "value b"},
                "field_b": {"Wert C": "value c"},
            },
        )

    def test_parse__reads_the_reverse_direction_from_the_same_mapping(self):
        # do it
        mapping = parse_metadata_mapping(MAPPING, "en", "de")

        # postcondition
        self.assertEqual(mapping["field_a"], {"value a": "Wert A", "value b": "Wert B"})

    def test_parse__leaves_out_a_field_that_does_not_know_the_language(self):
        # do it — field_b has no fr values
        mapping = parse_metadata_mapping(MAPPING, "de", "fr")

        # postcondition — its values carry over unchanged later
        self.assertIn("field_a", mapping)
        self.assertNotIn("field_b", mapping)

    def test_parse__tolerates_spacing_and_language_case(self):
        # setup
        mapping = {" field_a ": [{" DE ": "  Wert A  ", "En": " value a "}]}

        # do it / postcondition
        self.assertEqual(parse_metadata_mapping(mapping, "de", "EN"), {"field_a": {"Wert A": "value a"}})

    def test_parse__skips_rows_with_an_empty_or_missing_value(self):
        # setup — no mapping without both sides
        mapping = {
            "field_a": [
                {"de": "Wert A", "en": "value a"},
                {"de": "Wert B", "en": ""},
                {"de": "Wert C"},
                {"de": "", "en": "value d"},
                {},
            ]
        }

        # do it / postcondition
        self.assertEqual(parse_metadata_mapping(mapping, "de", "en"), {"field_a": {"Wert A": "value a"}})

    def test_parse__answers_nothing_for_an_empty_mapping(self):
        self.assertEqual(parse_metadata_mapping({}, "de", "en"), {})
        self.assertEqual(parse_metadata_mapping(None, "de", "en"), {})

    def test_parse__answers_nothing_for_a_value_that_is_no_mapping(self):
        # setup — e.g. a record still holding text from before the JSON format
        self.assertEqual(parse_metadata_mapping("[field_a]\nde, en\nWert A, value a", "de", "en"), {})

    def test_parse__answers_nothing_without_a_direction(self):
        # setup — no source language configured anywhere: there is no
        # direction to look up, values carry over unchanged
        self.assertEqual(parse_metadata_mapping(MAPPING, None, "en"), {})
        self.assertEqual(parse_metadata_mapping(MAPPING, "de", ""), {})


class TestSettingsMetadataMapping(TestCase):
    def test_get_metadata_mapping__parses_the_registry_record(self):
        # setup
        records = mock.Mock(metadata_mapping_table=MAPPING)

        # do it
        mapping = Settings(records=records).get_metadata_mapping("de", "en")

        # postcondition
        self.assertEqual(mapping["field_b"], {"Wert C": "value c"})

    def test_get_metadata_mapping__answers_nothing_without_a_site(self):
        self.assertEqual(Settings(records=None).get_metadata_mapping("de", "en"), {})


class TestValidateMetadataMapping(TestCase):
    def test_validate__accepts_a_well_formed_mapping(self):
        self.assertTrue(validate_metadata_mapping(MAPPING))

    def test_validate__accepts_an_empty_mapping(self):
        self.assertTrue(validate_metadata_mapping({}))

    def test_validate__accepts_a_row_with_a_single_language(self):
        # setup — a value without translations yet: every target keeps it
        self.assertTrue(validate_metadata_mapping({"field_a": [{"de": "Wert A"}]}))

    def test_validate__names_a_field_without_an_id(self):
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping({" ": [{"de": "Wert A"}]})
        self.assertIn("needs an id", str(caught.exception))

    def test_validate__names_a_key_that_is_no_language_code(self):
        # setup
        mapping = {"field_a": [{"de": "Wert A"}, {"Deutsch": "Wert B"}]}

        # do it / postcondition
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping(mapping)
        self.assertIn("field_a, row 2: 'Deutsch' is no language code", str(caught.exception))

    def test_validate__names_a_language_twice_in_one_row(self):
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping({"field_a": [{"de": "Wert A", "DE": "Wert B"}]})
        self.assertIn("field_a, row 1: a language appears twice", str(caught.exception))

    def test_validate__collects_every_problem_at_once(self):
        # setup — a fixable mapping is named completely, not error by error
        mapping = {
            "field_a": [{"Deutsch": "Wert A"}],
            "field_b": [{"de": "Wert B"}, {"de": "Wert C", "De": "Wert D"}],
        }

        # do it / postcondition
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping(mapping)
        message = str(caught.exception)
        self.assertIn("field_a, row 1", message)
        self.assertIn("field_b, row 2", message)


class TestMetadataMappingField(TestCase):
    def setUp(self) -> None:
        self.field = ITranslationSettings["metadata_mapping_table"]

    def test_field__accepts_a_well_formed_mapping(self):
        self.field.validate(MAPPING)

    def test_field__refuses_a_field_that_holds_no_rows(self):
        with self.assertRaises(WrongContainedType):
            self.field.validate({"field_a": {"de": "Wert A"}})

    def test_field__refuses_a_value_that_is_no_text(self):
        with self.assertRaises(WrongContainedType):
            self.field.validate({"field_a": [{"de": 1}]})

    def test_field__runs_the_language_check(self):
        with self.assertRaises(Invalid):
            self.field.validate({"field_a": [{"Deutsch": "Wert A"}]})


class TestSettingsExcludedTypes(TestCase):
    def test_excluded_types__defaults_to_none_without_a_site(self):
        self.assertEqual(Settings(records=None).excluded_types, [])

    def test_excluded_types__keeps_an_emptied_list(self):
        # setup — emptied on purpose: every type may be translated
        records = mock.Mock(excluded_types=[])

        # do it / postcondition
        self.assertEqual(Settings(records=records).excluded_types, [])


class TestSettingsCopyFields(TestCase):
    def test_copy_fields__default_to_the_file_fields_without_a_site(self):
        self.assertEqual(Settings(records=None).copy_fields, ["image", "file"])

    def test_copy_fields__keep_an_emptied_list(self):
        # setup — emptied on purpose: nothing is carried over
        records = mock.Mock(copy_fields=[])

        # do it / postcondition
        self.assertEqual(Settings(records=records).copy_fields, [])
