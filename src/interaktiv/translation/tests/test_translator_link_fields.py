import plone.api as api
from plone.app.multilingual.interfaces import ITranslationManager

from interaktiv.translation.providers.mock import MockProvider
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING, TestCase
from interaktiv.translation.translator import ContentTranslator

SELECTION = "interaktiv.translation.registry.translation.ITranslationSettings.metadata_selection"


class TestLinkFields(TestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        folder = self.portal["de"]
        self.target_a = api.content.create(container=folder, type="Document", id="target-a", title="Target A")
        self.target_b = api.content.create(container=folder, type="Document", id="target-b", title="Target B")
        manager = ITranslationManager(self.target_a)
        manager.add_translation("en")
        self.target_a_en = manager.get_translation("en")
        api.portal.set_registry_record(SELECTION, {"Link": ["remoteUrl"]})

    def _translate_link(self, remote_url):
        link = api.content.create(container=self.portal["de"], type="Link", id="link-a", title="Link A")
        link.remoteUrl = remote_url
        translator = ContentTranslator(translation_provider=MockProvider())

        return translator.translate(link, "en", "de"), translator

    def test_link__points_at_the_translation_of_its_target(self):
        # do it — Volto stores an internal address as resolveuid
        result, translator = self._translate_link(f"../resolveuid/{self.target_a.UID()}")

        # postcondition — not sent to the service (the mock would upper-case it)
        self.assertEqual(result["remoteUrl"], f"../resolveuid/{self.target_a_en.UID()}")
        self.assertEqual(len(translator.link_report), 1)

    def test_link__keeps_a_target_without_translation(self):
        # do it
        result, translator = self._translate_link(f"../resolveuid/{self.target_b.UID()}")

        # postcondition — the report tells
        self.assertEqual(result["remoteUrl"], f"../resolveuid/{self.target_b.UID()}")
        self.assertIsNone(translator.link_report[0]["after"])

    def test_link__keeps_an_external_address(self):
        # do it
        result, translator = self._translate_link("https://example.org/page-a")

        # postcondition
        self.assertEqual(result["remoteUrl"], "https://example.org/page-a")
        self.assertEqual(translator.link_report, [])
