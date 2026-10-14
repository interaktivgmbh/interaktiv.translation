from unittest import TestCase, mock

from zope.interface import Invalid

from interaktiv.translation.helpers.metadata import parse_metadata_mapping, validate_metadata_mapping_table
from interaktiv.translation.settings import Settings

TABLE = (
    "[field_a]\n"
    "de, en, fr\n"
    "Wert A, value a, valeur a\n"
    "Wert B, value b, valeur b\n"
    "\n"
    "[field_b]\n"
    "de; en\n"
    "Wert C; value c\n"
)


class TestParseMetadataMapping(TestCase):
    def test_parse__reads_one_direction_for_every_field(self):
        # do it
        mapping = parse_metadata_mapping(TABLE, "de", "en")

        # postcondition
        self.assertEqual(
            mapping,
            {
                "field_a": {"Wert A": "value a", "Wert B": "value b"},
                "field_b": {"Wert C": "value c"},
            },
        )

    def test_parse__reads_the_reverse_direction_from_the_same_table(self):
        # do it
        mapping = parse_metadata_mapping(TABLE, "en", "de")

        # postcondition
        self.assertEqual(mapping["field_a"], {"value a": "Wert A", "value b": "Wert B"})

    def test_parse__leaves_out_a_field_that_does_not_know_the_language(self):
        # do it — field_b has no fr column
        mapping = parse_metadata_mapping(TABLE, "de", "fr")

        # postcondition — its values carry over unchanged later
        self.assertIn("field_a", mapping)
        self.assertNotIn("field_b", mapping)

    def test_parse__tolerates_spacing_and_header_case(self):
        # setup
        table = "[field_a]\n DE ,  En \n  Wert A  , value a "

        # do it
        mapping = parse_metadata_mapping(table, "de", "en")

        # postcondition
        self.assertEqual(mapping, {"field_a": {"Wert A": "value a"}})

    def test_parse__skips_rows_with_an_empty_cell(self):
        # setup — no mapping without both sides
        table = "[field_a]\nde, en\nWert A, value a\nWert B, \n, value c"

        # do it
        mapping = parse_metadata_mapping(table, "de", "en")

        # postcondition
        self.assertEqual(mapping, {"field_a": {"Wert A": "value a"}})

    def test_parse__ignores_lines_before_the_first_section(self):
        # setup
        table = "de, en\nverirrt, lost\n[field_a]\nde, en\nWert A, value a"

        # do it
        mapping = parse_metadata_mapping(table, "de", "en")

        # postcondition
        self.assertEqual(mapping, {"field_a": {"Wert A": "value a"}})

    def test_parse__answers_nothing_for_an_empty_table(self):
        self.assertEqual(parse_metadata_mapping("", "de", "en"), {})

    def test_parse__answers_nothing_without_a_direction(self):
        # setup — no source language configured anywhere: there is no
        # direction to look up, values carry over unchanged
        self.assertEqual(parse_metadata_mapping(TABLE, None, "en"), {})
        self.assertEqual(parse_metadata_mapping(TABLE, "de", ""), {})


class TestSettingsMetadataMapping(TestCase):
    def test_get_metadata_mapping__parses_the_registry_record(self):
        # setup
        records = mock.Mock(metadata_mapping_table=TABLE)

        # do it
        mapping = Settings(records=records).get_metadata_mapping("de", "en")

        # postcondition
        self.assertEqual(mapping["field_b"], {"Wert C": "value c"})


class TestValidateMetadataMappingTable(TestCase):
    def test_validate__accepts_a_well_formed_table(self):
        self.assertTrue(validate_metadata_mapping_table(TABLE))

    def test_validate__accepts_an_empty_table(self):
        self.assertTrue(validate_metadata_mapping_table(""))

    def test_validate__names_a_line_outside_any_section(self):
        # setup
        table = "de, en\n[field_a]\nde, en\nWert A, value a"

        # do it / postcondition
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping_table(table)
        self.assertIn("line 1", str(caught.exception))
        self.assertIn("no [field] section", str(caught.exception))

    def test_validate__names_a_header_that_is_no_language_code(self):
        # setup
        table = "[field_a]\nDeutsch, en\nWert A, value a"

        # do it / postcondition
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping_table(table)
        self.assertIn("'Deutsch' is no language code", str(caught.exception))

    def test_validate__names_a_duplicated_language(self):
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping_table("[field_a]\nde, DE\nWert A, Wert B")
        self.assertIn("twice", str(caught.exception))

    def test_validate__wants_at_least_two_languages(self):
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping_table("[field_a]\nde\nWert A")
        self.assertIn("at least two languages", str(caught.exception))

    def test_validate__names_a_row_that_does_not_match_the_header(self):
        # setup
        table = "[field_a]\nde, en, fr\nWert A, value a"

        # do it / postcondition
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping_table(table)
        self.assertIn("line 3: 2 cells, but the header names 3 languages", str(caught.exception))

    def test_validate__collects_every_problem_at_once(self):
        # setup — a fixable paste is named completely, not error by error
        table = "verirrt\n[field_a]\nde, Deutsch\nWert A"

        # do it / postcondition
        with self.assertRaises(Invalid) as caught:
            validate_metadata_mapping_table(table)
        message = str(caught.exception)
        self.assertIn("line 1", message)
        self.assertIn("line 3", message)
        self.assertIn("line 4", message)


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
