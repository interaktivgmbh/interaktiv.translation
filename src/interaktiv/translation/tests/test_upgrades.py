from unittest import TestCase as UnitTestCase

import plone.api as api
from plone.registry import Record, field
from plone.registry.interfaces import IRegistry
from plone.schema import JSONField
from zope.component import getUtility

from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_INTEGRATION_TESTING, TestCase
from interaktiv.translation.upgrades import v1000_to_v1001
from interaktiv.translation.upgrades.v1000_to_v1001 import MAPPING_RECORD, csv_to_mapping


class TestUpgradeV1000ToV1001(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.registry = getUtility(IRegistry)

    def _install_1000_record(self, value: str) -> None:
        # the record as 1.0.0a1 left it: CSV text
        self.registry.records[MAPPING_RECORD] = Record(field.Text(title="Metadata mapping"), value)

    def test_upgrade__is_registered_for_the_profile(self):
        # do it
        steps = api.portal.get_tool("portal_setup").listUpgrades("interaktiv.translation:default", show_old=True)

        # postcondition
        self.assertIn(("1000", "1001"), [(step["ssource"], step["sdest"]) for step in steps])

    def test_upgrade__turns_the_csv_text_into_the_json_field(self):
        # setup
        self._install_1000_record("[field_a]\nde, en, fr\nWert A, value a, valeur a\nWert B, value b,")

        # precondition
        self.assertIsInstance(self.registry.records[MAPPING_RECORD].field, field.Text)

        # do it
        v1000_to_v1001.upgrade(None)

        # postcondition — the field is JSON, the values are kept, the empty cell is left out
        self.assertIsInstance(self.registry.records[MAPPING_RECORD].field, JSONField)
        self.assertEqual(
            self.registry[MAPPING_RECORD],
            {
                "field_a": [
                    {"de": "Wert A", "en": "value a", "fr": "valeur a"},
                    {"de": "Wert B", "en": "value b"},
                ]
            },
        )

    def test_upgrade__leaves_an_empty_mapping_for_empty_text(self):
        # setup
        self._install_1000_record("")

        # do it
        v1000_to_v1001.upgrade(None)

        # postcondition
        self.assertIsInstance(self.registry.records[MAPPING_RECORD].field, JSONField)
        self.assertEqual(self.registry[MAPPING_RECORD], {})

    def test_upgrade__keeps_a_mapping_that_is_json_already(self):
        # setup — the step runs on a site that has the JSON field
        mapping = {"field_a": [{"de": "Wert A", "en": "value a"}]}
        self.registry[MAPPING_RECORD] = mapping

        # do it
        v1000_to_v1001.upgrade(None)

        # postcondition
        self.assertEqual(self.registry[MAPPING_RECORD], mapping)


class TestCsvToMapping(UnitTestCase):
    def test_csv_to_mapping__reads_every_section(self):
        # setup
        table = "[field_a]\nde, en\nWert A, value a\n\n[field_b]\nde; en\nWert B; value b\n"

        # do it / postcondition
        self.assertEqual(
            csv_to_mapping(table),
            {
                "field_a": [{"de": "Wert A", "en": "value a"}],
                "field_b": [{"de": "Wert B", "en": "value b"}],
            },
        )

    def test_csv_to_mapping__keeps_a_quoted_value_with_the_delimiter(self):
        self.assertEqual(
            csv_to_mapping('[field_a]\nde,en\n"Wert A, Wert B",value a'),
            {"field_a": [{"de": "Wert A, Wert B", "en": "value a"}]},
        )

    def test_csv_to_mapping__drops_a_column_that_is_no_language_or_named_twice(self):
        self.assertEqual(
            csv_to_mapping("[field_a]\nde, Deutsch, en, DE\nWert A, Wert B, value a, Wert C"),
            {"field_a": [{"de": "Wert A", "en": "value a"}]},
        )

    def test_csv_to_mapping__leaves_out_rows_and_sections_without_values(self):
        self.assertEqual(csv_to_mapping("verirrt\n[field_a]\nde, en\n,\n[field_b]\nde, en"), {})
