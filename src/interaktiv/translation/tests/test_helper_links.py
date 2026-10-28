import plone.api as api
from interaktiv.translation.testing import TestCase
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from interaktiv.translation.registry.translation import ITranslationSettings
from plone.app.multilingual.interfaces import ITranslationManager

from interaktiv.translation.helpers.links import (
    _get_translated_object_path,
    postprocess_links,
)
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING


class TestTranslatedObjectPath(TestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.source = api.content.create(container=self.portal["de"], type="Document", id="quelle", title="Quelle")
        self.target = api.content.create(container=self.portal["de"], type="Document", id="ziel", title="Ziel")
        manager = ITranslationManager(self.target)
        manager.add_translation("en")
        api.content.rename(obj=manager.get_translation("en"), new_id="target")

        self.lonely = api.content.create(container=self.portal["de"], type="Document", id="allein", title="Allein")

    def _translated(self, path, **kw):
        return _get_translated_object_path(path, "en", **kw)

    def assertResolves(self, result, suffix=""):
        uid = ITranslationManager(self.target).get_translation("en").UID()
        self.assertIsNotNone(result)
        self.assertTrue(
            result.endswith(f"resolveuid/{uid}{suffix}"),
            f"{result!r} endet nicht auf resolveuid/{uid}{suffix}",
        )

    def test_absolute_path__names_the_translation(self):
        self.assertResolves(self._translated("/de/ziel"))

    def test_path_naming_the_portal__is_understood(self):
        portal_path = "/".join(self.portal.getPhysicalPath())
        self.assertResolves(self._translated(f"{portal_path}/de/ziel"))

    def test_api_prefix__is_understood(self):
        self.assertResolves(self._translated("/++api++/de/ziel"))

    def test_full_url_of_this_site__is_understood(self):
        # The form becomes resolveuid — that is what Plone stores.
        self.assertResolves(self._translated(f"{self.portal.absolute_url()}/de/ziel"))

    def test_images_suffix__survives_untouched(self):
        self.assertResolves(
            self._translated("/de/ziel/@@images/image/preview"),
            suffix="/@@images/image/preview",
        )

    def test_view_suffix__survives_untouched(self):
        # `/de/ziel/view` traverses to the view, not to a deeper object.
        self.assertResolves(self._translated("/de/ziel/view"), suffix="/view")

    def test_query_and_fragment__survive_untouched(self):
        self.assertResolves(self._translated("/de/ziel?a=1#kapitel"), suffix="?a=1#kapitel")

    def test_the_answer_names_the_translation__not_the_original(self):
        # The translation was renamed on purpose: an answer built by patching
        # up the original would still name the German page.
        self.assertNotIn(self.target.UID(), self._translated("/de/ziel"))

    def test_untranslated_target__is_left_alone(self):
        self.assertIsNone(self._translated("/de/allein"))

    def test_unknown_path__is_left_alone(self):
        self.assertIsNone(self._translated("/de/gibt-es-nicht"))

    def test_relative_path__needs_the_page_that_holds_it(self):
        # Without a base there is nothing to count `../` from.
        self.assertIsNone(self._translated("../ziel"))

    def test_relative_path__resolves_against_that_page(self):
        self.assertResolves(self._translated("../ziel", content=self.source))

    def test_acquisition__does_not_pass_for_a_hit(self):
        # `/de/quelle/ziel` does not exist; acquisition would hand back
        # `/de/ziel` and it would look like a match.
        self.assertIsNone(self._translated("/de/quelle/ziel"))

    def test_path_climbing_out_of_the_site__is_refused(self):
        self.assertIsNone(self._translated("/de/../../etc/passwd"))

    def test_relative_path_climbing_out_of_the_site__is_refused(self):
        self.assertIsNone(self._translated("../../../etc", content=self.source))


class TestLinkReport(TestCase):
    """What the editor is told afterwards: one entry per internal link, with
    `after` empty for a link that had to be left as it was."""

    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.target = api.content.create(container=self.portal["de"], type="Document", id="ziel", title="Ziel")
        ITranslationManager(self.target).add_translation("en")
        self.lonely = api.content.create(container=self.portal["de"], type="Document", id="allein", title="Allein")

    def _report_for(self, url, text="Ziele 2035"):
        """Run the postprocessing over one slate link and hand back the report."""
        blocks = {
            "b1": {
                "@type": "slate",
                "value": [
                    {
                        "type": "link",
                        "data": {"url": url},
                        "children": [{"text": text}],
                    }
                ],
            }
        }
        report = []
        postprocess_links(self.portal["de"], "blocks", blocks, "en", report=report)

        return blocks, report

    def test_translated_target__is_reported_as_rewritten(self):
        blocks, report = self._report_for("/de/ziel")

        self.assertEqual(len(report), 1)
        entry = report[0]
        self.assertEqual(entry["text"], "Ziele 2035")
        self.assertEqual(entry["before"], "/de/ziel")
        # The report is for people: it names where the link now goes...
        translation = ITranslationManager(self.target).get_translation("en")
        self.assertEqual(entry["after"], translation.absolute_url())
        # ...while the block stores the uid, which survives a rename.
        self.assertIn(
            f"resolveuid/{translation.UID()}",
            blocks["b1"]["value"][0]["data"]["url"],
        )

    def test_untranslated_target__is_reported_as_left_alone(self):
        blocks, report = self._report_for("/de/allein")

        self.assertEqual(len(report), 1)
        self.assertIsNone(report[0]["after"])
        # the link stays exactly as it was
        self.assertEqual(blocks["b1"]["value"][0]["data"]["url"], "/de/allein")

    def test_external_link__is_not_reported_at_all(self):
        _blocks, report = self._report_for("https://www.example.org/x")

        self.assertEqual(report, [])

    def test_mailto__is_not_reported_at_all(self):
        _blocks, report = self._report_for("mailto:a@example.org")

        self.assertEqual(report, [])

    def test_anchor__is_not_reported_at_all(self):
        _blocks, report = self._report_for("#kapitel")

        self.assertEqual(report, [])

    def test_link_without_words__falls_back_to_the_enclosing_title(self):
        blocks = {
            "b1": {
                "@type": "teaser",
                "title": "Link Title",
                "url": "/de/ziel",
            }
        }
        report = []
        postprocess_links(self.portal["de"], "blocks", blocks, "en", report=report)

        self.assertEqual(report[0]["text"], "Link Title")

    def test_object_list_entry_ids__are_no_links_and_not_reported(self):
        # setup — the tabs of a tab block: Volto gives each entry a uuid as `@id`
        blocks = {
            "b1": {
                "@type": "tabBlock",
                "headline": "Tabs",
                "columns": [
                    {"@id": "cdde56fc-5346-4f9e-a01a-b9c11b3aebf4", "title": "Tab Eins"},
                    {"@id": "E597C38A-61DB-488C-946C-89BBCAE3B6A4", "title": "Tab Zwei"},
                ],
            }
        }
        report = []

        # do it
        postprocess_links(self.portal["de"], "blocks", blocks, "en", report=report)

        # postcondition — nothing rewritten, nothing for the editor to read
        self.assertEqual(report, [])
        self.assertEqual(blocks["b1"]["columns"][0]["@id"], "cdde56fc-5346-4f9e-a01a-b9c11b3aebf4")
        self.assertEqual(blocks["b1"]["columns"][1]["@id"], "E597C38A-61DB-488C-946C-89BBCAE3B6A4")

    def test_values_in_no_link_shape__are_left_alone_and_not_reported(self):
        # setup — short ids some add-ons give list entries, and a mail link
        blocks = {
            "b1": {
                "@type": "someblock",
                "items": [
                    {"@id": "1", "title": "Entry A"},
                    {"@id": "item-1", "title": "Entry B"},
                    {"@id": "x7Kq2", "title": "Entry C"},
                ],
                "url": "mailto:info@example.org",
            }
        }
        report = []

        # do it
        postprocess_links(self.portal["de"], "blocks", blocks, "en", report=report)

        # postcondition
        self.assertEqual(report, [])
        self.assertEqual([item["@id"] for item in blocks["b1"]["items"]], ["1", "item-1", "x7Kq2"])
        self.assertEqual(blocks["b1"]["url"], "mailto:info@example.org")


class TestObjectBrowserLinks(TestCase):
    """The shape a teaser block stores a link in: an array of entries that
    name the target by `@id` and carry the link text beside it."""

    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.target = api.content.create(container=self.portal["de"], type="Document", id="ziel", title="Ziel")
        ITranslationManager(self.target).add_translation("en")

    def _teaser(self, key="href", path="/de/ziel"):
        return {
            "b1": {
                "@type": "teaser",
                key: [
                    {
                        "@id": path,
                        "title": "Teaser Title",
                        "hasPreviewImage": True,
                    }
                ],
            }
        }

    def test_teaser_href__is_rewritten_and_reported(self):
        blocks = self._teaser()
        report = []
        postprocess_links(self.portal["de"], "blocks", blocks, "en", report=report)

        uid = ITranslationManager(self.target).get_translation("en").UID()
        entry = blocks["b1"]["href"][0]
        self.assertIn(f"resolveuid/{uid}", entry["@id"])
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["text"], "Teaser Title")

    def test_preview_image__is_treated_the_same_way(self):
        # Plone counts `preview_image` as a link field too. Whether it is
        # rewritten decides itself: only a target that HAS a translation moves.
        blocks = self._teaser(key="preview_image")
        report = []
        postprocess_links(self.portal["de"], "blocks", blocks, "en", report=report)

        self.assertEqual(len(report), 1)
        self.assertIsNotNone(report[0]["after"])

    def test_the_entry_keeps_everything_else_it_carries(self):
        blocks = self._teaser()
        postprocess_links(self.portal["de"], "blocks", blocks, "en", report=[])

        entry = blocks["b1"]["href"][0]
        self.assertTrue(entry["hasPreviewImage"])
        # Only the link moves: the title stored beside it still names the
        # source page, the translation does not touch it.
        self.assertEqual(entry["title"], "Teaser Title")


class TestContentTypeLinkFields(TestCase):
    """Links that sit on the object itself rather than inside a block. Which
    fields those are is a project's answer, given in the control panel."""

    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.target = api.content.create(container=self.portal["de"], type="Document", id="ziel", title="Ziel")
        ITranslationManager(self.target).add_translation("en")
        self.records = getUtility(IRegistry).forInterface(ITranslationSettings, check=False)

    def test_a_named_field__is_rewritten_and_reported(self):
        # setup
        self.records.link_fields = ["website_link"]

        # do it
        report = []
        value = postprocess_links(self.portal["de"], "website_link", "/de/ziel", "en", report=report)

        # postcondition
        uid = ITranslationManager(self.target).get_translation("en").UID()
        self.assertIn(f"resolveuid/{uid}", value)
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["before"], "/de/ziel")

    def test_a_field_nobody_named__is_left_alone(self):
        # setup — the site knows of no link fields at all
        self.records.link_fields = []

        # do it
        report = []
        value = postprocess_links(self.portal["de"], "website_link", "/de/ziel", "en", report=report)

        # postcondition
        self.assertEqual(value, "/de/ziel")
        self.assertEqual(report, [])

    def test_block_keys__are_configurable_too(self):
        # setup — a block type of one's own keeping its target under `ziel_url`
        self.records.block_link_fields = ["ziel_url"]

        # do it
        blocks = {"b1": {"@type": "eigenerBlock", "ziel_url": "/de/ziel"}}
        report = []
        postprocess_links(self.portal["de"], "blocks", blocks, "en", report=report)

        # postcondition
        self.assertEqual(len(report), 1)
        self.assertIsNotNone(report[0]["after"])
