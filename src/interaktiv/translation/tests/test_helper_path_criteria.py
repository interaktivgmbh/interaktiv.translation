import plone.api as api
from plone.app.multilingual.interfaces import ITranslationManager

from interaktiv.translation.helpers.links import ABSOLUTE_PATH_OPERATION, postprocess_links
from interaktiv.translation.providers.mock import MockProvider
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING, TestCase
from interaktiv.translation.translator import ContentTranslator

SELECTION = "interaktiv.translation.registry.translation.ITranslationSettings.metadata_selection"
RELATIVE_PATH_OPERATION = "plone.app.querystring.operation.string.relativePath"


def _criterion(value, operation=ABSOLUTE_PATH_OPERATION):
    return {"i": "path", "o": operation, "v": value}


class TestPathCriteria(TestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        folder = self.portal["de"]
        self.folder_a = api.content.create(container=folder, type="Folder", id="folder-a", title="Folder A")
        self.folder_b = api.content.create(container=folder, type="Folder", id="folder-b", title="Folder B")
        manager = ITranslationManager(self.folder_a)
        manager.add_translation("en")
        self.folder_a_en = manager.get_translation("en")
        self.portal_path = "/".join(self.portal.getPhysicalPath())
        self.document = api.content.create(container=folder, type="Document", id="document-a", title="Document A")

    def _path(self, obj):
        return "/".join(obj.getPhysicalPath())[len(self.portal_path) :]

    def _translated(self, *criteria, report=None):
        blocks = {"block-a": {"@type": "listing", "querystring": {"query": list(criteria)}}}
        result = postprocess_links(self.document, "blocks", blocks, "en", report=report)

        return result["block-a"]["querystring"]["query"]

    def test_uid__points_at_the_translation_and_keeps_its_depth(self):
        # do it — as Volto stores it
        query = self._translated(_criterion(f"{self.folder_a.UID()}::1"))

        # postcondition
        self.assertEqual(query[0]["v"], f"{self.folder_a_en.UID()}::1")

    def test_uid_without_depth__points_at_the_translation(self):
        self.assertEqual(self._translated(_criterion(self.folder_a.UID()))[0]["v"], self.folder_a_en.UID())

    def test_path__points_at_the_translation_and_keeps_its_depth(self):
        # do it
        query = self._translated(_criterion(f"{self._path(self.folder_a)}::2"))

        # postcondition — a path stays a path
        self.assertEqual(query[0]["v"], f"{self._path(self.folder_a_en)}::2")

    def test_path_with_the_portal__keeps_the_portal(self):
        # do it
        query = self._translated(_criterion("/".join(self.folder_a.getPhysicalPath())))

        # postcondition
        self.assertEqual(query[0]["v"], "/".join(self.folder_a_en.getPhysicalPath()))

    def test_folder_without_translation__is_kept_and_reported(self):
        # setup
        report = []

        # do it
        query = self._translated(_criterion(f"{self.folder_b.UID()}::1"), report=report)

        # postcondition — the listing still lists the source language; the report tells
        self.assertEqual(query[0]["v"], f"{self.folder_b.UID()}::1")
        self.assertEqual(
            report,
            [
                {
                    "text": "query",
                    "before": self.folder_b.absolute_url(),
                    "after": None,
                    "kind": "link",
                    "status": "untranslated",
                }
            ],
        )

    def test_translation__is_reported(self):
        # setup
        report = []

        # do it
        self._translated(_criterion(self.folder_a.UID()), report=report)

        # postcondition
        self.assertEqual(report[0]["after"], self.folder_a_en.absolute_url())

    def test_relative_path_and_other_criteria__stay(self):
        # setup
        criteria = [
            _criterion("../folder-a::1", RELATIVE_PATH_OPERATION),
            {"i": "portal_type", "o": "plone.app.querystring.operation.selection.any", "v": ["Document"]},
        ]
        report = []

        # do it
        query = self._translated(*[dict(criterion) for criterion in criteria], report=report)

        # postcondition — it resolves inside the translation's own folder already
        self.assertEqual(query, criteria)
        self.assertEqual(report, [])

    def test_unknown_folder__stays_unreported(self):
        # setup
        report = []

        # do it
        query = self._translated(_criterion("uid-unknown::1"), report=report)

        # postcondition
        self.assertEqual(query[0]["v"], "uid-unknown::1")
        self.assertEqual(report, [])

    def test_collection__takes_its_search_along_pointed_at_the_translation(self):
        # setup
        collection = api.content.create(container=self.portal["de"], type="Collection", id="collection-a", title="A")
        collection.query = [_criterion(f"{self.folder_a.UID()}::1")]
        api.portal.set_registry_record(SELECTION, {"Collection": ["query"]})

        # do it
        result = ContentTranslator(translation_provider=MockProvider()).translate(collection, "en", "de")

        # postcondition — the source keeps its own search
        self.assertEqual(result["query"][0]["v"], f"{self.folder_a_en.UID()}::1")
        self.assertEqual(collection.query[0]["v"], f"{self.folder_a.UID()}::1")
