from interaktiv.translation.controlpanels.classic import TranslationSettingsForm
from interaktiv.translation.settings import Settings
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_INTEGRATION_TESTING, TestCase
from interaktiv.translation.tests.test_integration import _records


class TestClassicControlPanel(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def setUp(self) -> None:
        super().setUp()
        _records().api_key = "key-value-a"
        self.form = TranslationSettingsForm(self.portal, self.request)
        self.form.update()

    def test_save__keeps_the_api_key_for_an_empty_field(self):
        # do it — the password field shows no value, so it comes back empty
        self.form.applyChanges({"api_key": None, "api_url": "https://proxy.test/v2"})

        # postcondition — the other field is saved, the key stays
        self.assertEqual(Settings().api_key, "key-value-a")
        self.assertEqual(_records().api_url, "https://proxy.test/v2")

    def test_save__takes_a_new_api_key(self):
        # do it
        self.form.applyChanges({"api_key": "key-value-b"})

        # postcondition
        self.assertEqual(Settings().api_key, "key-value-b")
