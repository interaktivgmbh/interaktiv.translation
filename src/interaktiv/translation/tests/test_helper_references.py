import plone.api as api
from plone.app.multilingual.interfaces import ITranslationManager
from z3c.relationfield import RelationValue
from zope.component import getUtility
from zope.intid.interfaces import IIntIds

from interaktiv.translation.helpers.field_access import set_field_value
from interaktiv.translation.helpers.links import translated_targets
from interaktiv.translation.providers.mock import MockProvider
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING, TestCase
from interaktiv.translation.translator import ContentTranslator

SELECTION = "interaktiv.translation.registry.translation.ITranslationSettings.metadata_selection"


class TestTranslatedTargets(TestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        folder = self.portal["de"]
        self.target_a = api.content.create(container=folder, type="Document", id="target-a", title="Target A")
        self.target_b = api.content.create(container=folder, type="Document", id="target-b", title="Target B")
        manager = ITranslationManager(self.target_a)
        manager.add_translation("en")
        self.target_a_en = manager.get_translation("en")

    def _document_with_references(self, *targets):
        document = api.content.create(container=self.portal["de"], type="Document", id="document-a", title="Title A")
        intids = getUtility(IIntIds)
        document.relatedItems = [RelationValue(intids.getId(target)) for target in targets]

        return document

    def test_targets__point_at_the_translation(self):
        # setup
        report = []

        # do it
        target = translated_targets("field_a", self.target_a, "en", report)

        # postcondition
        self.assertEqual(target, self.target_a_en)
        self.assertEqual(
            report,
            [{"text": "field_a", "before": self.target_a.absolute_url(), "after": self.target_a_en.absolute_url()}],
        )

    def test_targets__keep_a_target_without_translation(self):
        # setup
        report = []

        # do it
        target = translated_targets("field_a", self.target_b, "en", report)

        # postcondition — as an editor may point at another language too; the report tells
        self.assertEqual(target, self.target_b)
        self.assertEqual(report, [{"text": "field_a", "before": self.target_b.absolute_url(), "after": None}])

    def test_targets__of_a_list_each_and_without_a_broken_one(self):
        # do it — a broken reference is read as None
        targets = translated_targets("field_a", [self.target_a, None, self.target_b], "en")

        # postcondition
        self.assertEqual(targets, [self.target_a_en, self.target_b])

    def test_targets__of_none_are_none(self):
        self.assertIsNone(translated_targets("field_a", None, "en"))

    def test_translate__takes_the_chosen_references_along(self):
        # setup
        document = self._document_with_references(self.target_a, self.target_b)
        api.portal.set_registry_record(SELECTION, {"Document": ["relatedItems"]})
        translator = ContentTranslator(translation_provider=MockProvider())

        # do it
        result = translator.translate(document, "en", "de")

        # postcondition
        self.assertEqual(result["relatedItems"], [self.target_a_en, self.target_b])
        self.assertEqual([entry["after"] for entry in translator.link_report], [self.target_a_en.absolute_url(), None])

    def test_translate__writes_references_of_their_own(self):
        # setup
        document = self._document_with_references(self.target_a)
        api.portal.set_registry_record(SELECTION, {"Document": ["relatedItems"]})
        result = ContentTranslator(translation_provider=MockProvider()).translate(document, "en", "de")
        translation = api.content.create(container=self.portal["en"], type="Document", id="document-a", title="A")

        # do it
        set_field_value(translation, "relatedItems", result["relatedItems"])

        # postcondition — new relations; the source keeps its own
        self.assertEqual([relation.to_object for relation in translation.relatedItems], [self.target_a_en])
        self.assertIsNot(translation.relatedItems[0], document.relatedItems[0])
        self.assertEqual(document.relatedItems[0].to_object, self.target_a)

    def test_translate__leaves_references_out_unless_chosen(self):
        # setup
        document = self._document_with_references(self.target_a)

        # do it
        result = ContentTranslator(translation_provider=MockProvider()).translate(document, "en", "de")

        # postcondition — opt-in, as any field of the selection
        self.assertNotIn("relatedItems", result)
