import copy

import plone.api as api
from plone.app.multilingual.interfaces import ITranslationManager

from interaktiv.translation.helpers.links import postprocess_links
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING, TestCase


class TestTargetEntries(TestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        folder = self.portal["de"]
        self.page = api.content.create(container=folder, type="Document", id="page-a", title="Page A")
        self.target = api.content.create(
            container=folder, type="Document", id="target-a", title="Titel A", description="Beschreibung A"
        )
        manager = ITranslationManager(self.target)
        manager.add_translation("en")
        self.target_en = api.content.rename(obj=manager.get_translation("en"), new_id="target-a-en")
        self.target_en.title = "Title A"
        self.target_en.reindexObject()
        self.target_b = api.content.create(container=folder, type="Document", id="target-b", title="Titel B")

    def _entry(self, target, **more):
        return {
            "@id": "/".join(target.getPhysicalPath())[len("/".join(self.portal.getPhysicalPath())) :],
            "title": target.title,
            "Title": target.title,
            "Description": target.description,
            "UID": target.UID(),
            "getPath": "/".join(target.getPhysicalPath()),
            "Language": "de",
            **more,
        }

    def _translated(self, entry, check=False):
        blocks = {"block-a": {"@type": "block-a", "link": [entry]}}
        result = postprocess_links(self.page, "blocks", blocks, "en", check=check)

        return result["block-a"]["link"][0]

    def test_entry__is_told_anew_of_the_translation(self):
        # do it
        entry = self._translated(self._entry(self.target))

        # postcondition
        self.assertEqual(
            entry,
            {
                "@id": entry["@id"],
                "title": "Title A",
                "Title": "Title A",
                "Description": "",
                "UID": self.target_en.UID(),
                "getPath": "/".join(self.target_en.getPhysicalPath()),
                "Language": "en",
            },
        )

    def test_entry__still_points_at_the_translation(self):
        # do it
        entry = self._translated(self._entry(self.target))

        # postcondition
        self.assertTrue(entry["@id"].endswith(f"resolveuid/{self.target_en.UID()}"))

    def test_what_the_translation_does_not_tell__is_kept_without_a_value(self):
        # setup
        entry = self._entry(self.target, getRemoteUrl="/de/target-c")

        # do it
        translated = self._translated(entry)

        # postcondition
        self.assertIsNone(translated["getRemoteUrl"])
        self.assertEqual(list(translated), list(entry))

    def test_entry_of_a_target_without_translation__stays_as_it_is(self):
        # setup
        entry = self._entry(self.target_b)

        # do it
        translated = self._translated(copy.deepcopy(entry))

        # postcondition
        self.assertEqual(translated, entry)

    def test_entry_with_a_key_the_catalog_does_not_know__keeps_all_but_its_target(self):
        # setup
        entry = self._entry(self.target, field_a="Text A")

        # do it
        translated = self._translated(copy.deepcopy(entry))

        # postcondition
        self.assertTrue(translated.pop("@id").endswith(f"resolveuid/{self.target_en.UID()}"))
        entry.pop("@id")
        self.assertEqual(translated, entry)

    def test_check__changes_nothing(self):
        # setup
        entry = self._entry(self.target)

        # do it
        translated = self._translated(copy.deepcopy(entry), check=True)

        # postcondition
        self.assertEqual(translated, entry)
