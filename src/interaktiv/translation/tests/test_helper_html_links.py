import plone.api as api
from plone.app.multilingual.interfaces import ITranslationManager

from interaktiv.translation.helpers.links import postprocess_links
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING, TestCase


TEXT_KEYS = "interaktiv.translation.registry.translation.ITranslationSettings.block_text_keys"


class TestHtmlBlockLinks(TestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        folder = self.portal["de"]
        self.page = api.content.create(container=folder, type="Document", id="page-a", title="Page A")
        self.target = api.content.create(container=folder, type="Document", id="target-a", title="Target A")
        manager = ITranslationManager(self.target)
        manager.add_translation("en")
        self.target_en = api.content.rename(obj=manager.get_translation("en"), new_id="target-a-en")
        self.target_b = api.content.create(container=folder, type="Document", id="target-b", title="Target B")
        self.image = api.content.create(container=folder, type="Image", id="image-a", title="Image A")
        manager = ITranslationManager(self.image)
        manager.add_translation("en")
        api.content.rename(obj=manager.get_translation("en"), new_id="image-a-en")
        api.content.create(container=folder, type="Image", id="image-b", title="Image B")
        self.portal_url = self.portal.absolute_url()
        self.portal_path = "/".join(self.portal.getPhysicalPath())

    def _translated(self, markup, report=None, check=False):
        blocks = {"block-a": {"@type": "html", "html": markup}}
        result = postprocess_links(self.page, "blocks", blocks, "en", report=report, check=check)

        return result["block-a"]["html"]

    def test_path__points_at_the_translation(self):
        # do it
        markup = self._translated('<p class="class-a"><a href="/de/target-a">Text A</a> Text B</p>')

        # postcondition
        self.assertEqual(markup, '<p class="class-a"><a href="/en/target-a-en">Text A</a> Text B</p>')

    def test_path_with_the_portal__keeps_the_portal(self):
        # do it
        markup = self._translated(f'<a href="{self.portal_path}/de/target-a">Text A</a>')

        # postcondition
        self.assertEqual(markup, f'<a href="{self.portal_path}/en/target-a-en">Text A</a>')

    def test_full_url_of_the_site__stays_a_full_url(self):
        # do it
        markup = self._translated(f'<a href="{self.portal_url}/de/target-a">Text A</a>')

        # postcondition
        self.assertEqual(markup, f'<a href="{self.portal_url}/en/target-a-en">Text A</a>')

    def test_view_query_and_fragment__are_kept(self):
        # do it
        markup = self._translated('<a href="/de/target-a/@@view-a?a=1&amp;b=2#anchor-a">Text A</a>')

        # postcondition
        self.assertEqual(markup, '<a href="/en/target-a-en/@@view-a?a=1&amp;b=2#anchor-a">Text A</a>')

    def test_single_quotes_and_other_attributes__are_kept(self):
        # do it
        markup = self._translated("<a class='class-a' href='/de/target-a' title='Title A'>Text A</a>")

        # postcondition
        self.assertEqual(markup, "<a class='class-a' href='/en/target-a-en' title='Title A'>Text A</a>")

    def test_translation__is_reported_with_the_text_of_the_link(self):
        # setup
        report = []

        # do it
        self._translated('<p><a href="/de/target-a">Text <b>A</b> &amp; B</a></p>', report=report)

        # postcondition
        self.assertEqual(
            report,
            [
                {
                    "text": "Text A & B",
                    "before": "/de/target-a",
                    "after": "/en/target-a-en",
                    "kind": "link",
                    "status": "translated",
                }
            ],
        )

    def test_uid_link__gets_the_uid_of_the_translation_and_keeps_the_rest(self):
        # do it
        markup = self._translated(f'<a href="../resolveuid/{self.target.UID()}/@@view-a#anchor-a">Text A</a>')

        # postcondition
        self.assertEqual(markup, f'<a href="../resolveuid/{self.target_en.UID()}/@@view-a#anchor-a">Text A</a>')

    def test_uid_link__is_reported_by_the_addresses_of_its_targets(self):
        # setup
        report = []

        # do it
        self._translated(f'<a href="/resolveuid/{self.target.UID()}">Text A</a>', report=report)

        # postcondition
        self.assertEqual(report[0]["before"], self.target.absolute_url())
        self.assertEqual(report[0]["after"], self.target_en.absolute_url())
        self.assertEqual(report[0]["status"], "translated")

    def test_uid_link_without_translation__is_kept_and_reported(self):
        # setup
        report = []

        # do it
        markup = self._translated(f'<a href="/resolveuid/{self.target_b.UID()}">Text A</a>', report=report)

        # postcondition
        self.assertEqual(markup, f'<a href="/resolveuid/{self.target_b.UID()}">Text A</a>')
        self.assertEqual(report[0]["status"], "untranslated")

    def test_uid_link_of_another_site__stays_unreported(self):
        # setup
        markup = f'<a href="https://example.org/resolveuid/{self.target.UID()}">Text A</a>'
        report = []

        # do it
        translated = self._translated(markup, report=report)

        # postcondition
        self.assertEqual(translated, markup)
        self.assertEqual(report, [])

    def test_target_without_translation__is_kept_and_reported(self):
        # setup
        report = []

        # do it
        markup = self._translated('<a href="/de/target-b">Text A</a>', report=report)

        # postcondition
        self.assertEqual(markup, '<a href="/de/target-b">Text A</a>')
        self.assertEqual(report[0]["after"], None)
        self.assertEqual(report[0]["status"], "untranslated")

    def test_unknown_target__is_kept_and_reported_as_broken(self):
        # setup
        report = []

        # do it
        markup = self._translated('<a href="/de/target-unknown">Text A</a>', report=report)

        # postcondition
        self.assertEqual(markup, '<a href="/de/target-unknown">Text A</a>')
        self.assertEqual(report[0]["status"], "broken")

    def test_what_is_no_internal_link__stays_unreported(self):
        # setup
        markup = (
            '<a href="https://example.org/de/target-a">Text A</a>'
            '<a href="//example.org/de/target-a">Text B</a>'
            '<a href="mailto:a@example.org">Text C</a>'
            '<a href="#anchor-a">Text D</a>'
            '<a href="../target-a">Text E</a>'
            "<a href=/de/target-a>Text F</a>"
            '<p>href="/de/target-a"</p>'
        )
        report = []

        # do it
        translated = self._translated(markup, report=report)

        # postcondition
        self.assertEqual(translated, markup)
        self.assertEqual(report, [])

    def test_check__changes_nothing_and_names_external_links_as_well(self):
        # setup
        markup = '<a href="/de/target-a">Text A</a><a href="https://example.org">Text B</a>'
        report = []

        # do it
        translated = self._translated(markup, report=report, check=True)

        # postcondition
        self.assertEqual(translated, markup)
        self.assertEqual([entry["status"] for entry in report], ["translatable", "external"])

    def test_html_block_inside_another_block__is_found(self):
        # setup
        blocks = {"block-a": {"@type": "gridBlock", "blocks": {"block-b": {"@type": "html", "html": ""}}}}
        blocks["block-a"]["blocks"]["block-b"]["html"] = '<a href="/de/target-a">Text A</a>'

        # do it
        result = postprocess_links(self.page, "blocks", blocks, "en")

        # postcondition
        self.assertEqual(result["block-a"]["blocks"]["block-b"]["html"], '<a href="/en/target-a-en">Text A</a>')

    def test_html_key_of_another_block__stays(self):
        # setup
        blocks = {"block-a": {"@type": "block-a", "html": '<a href="/de/target-a">Text A</a>'}}

        # do it
        result = postprocess_links(self.page, "blocks", blocks, "en")

        # postcondition
        self.assertEqual(result["block-a"]["html"], '<a href="/de/target-a">Text A</a>')

    def test_image__points_at_the_translation_and_keeps_its_scale(self):
        # do it
        markup = self._translated('<img class="class-a" src="/de/image-a/@@images/image/preview" alt="Alt A">')

        # postcondition
        self.assertEqual(markup, '<img class="class-a" src="/en/image-a-en/@@images/image/preview" alt="Alt A">')

    def test_image_with_a_computed_scale__points_at_the_image_as_it_was_uploaded(self):
        # setup
        scale = "image-800-0123456789abcdef0123456789abcdef.png"

        # do it
        markup = self._translated(f'<img src="{self.portal_url}/de/image-a/@@images/{scale}" alt="Alt A">')

        # postcondition
        self.assertEqual(markup, f'<img src="{self.portal_url}/en/image-a-en/@@images/image" alt="Alt A">')

    def test_image__is_reported_as_an_image_named_by_its_alt(self):
        # setup
        report = []

        # do it
        self._translated('<img src="/de/image-a/@@images/image" alt="Alt A &amp; B">', report=report)

        # postcondition
        self.assertEqual(
            report,
            [
                {
                    "text": "Alt A & B",
                    "before": "/de/image-a/@@images/image",
                    "after": "/en/image-a-en/@@images/image",
                    "kind": "image",
                    "status": "translated",
                }
            ],
        )

    def test_image_without_alt__is_named_by_the_title_of_the_image(self):
        # setup
        report = []

        # do it
        self._translated('<img src="/de/image-a/@@images/image">', report=report)

        # postcondition
        self.assertEqual(report[0]["text"], "Image A")

    def test_image_without_translation__is_kept_and_reported(self):
        # setup
        scale = "image-800-0123456789abcdef0123456789abcdef.png"
        report = []

        # do it
        markup = self._translated(f'<img src="/de/image-b/@@images/{scale}" alt="Alt A">', report=report)

        # postcondition
        self.assertEqual(markup, f'<img src="/de/image-b/@@images/{scale}" alt="Alt A">')
        self.assertEqual(report[0]["kind"], "image")
        self.assertEqual(report[0]["status"], "untranslated")

    def test_linked_image__points_both_at_their_translations(self):
        # do it
        markup = self._translated('<a href="/de/target-a"><img src="/de/image-a/@@images/image" alt="Alt A"></a>')

        # postcondition
        self.assertEqual(markup, '<a href="/en/target-a-en"><img src="/en/image-a-en/@@images/image" alt="Alt A"></a>')

    def test_src_and_href_of_other_tags__stay_unreported(self):
        # setup
        markup = (
            '<script src="/de/target-a"></script>'
            '<link href="/de/target-a">'
            '<iframe src="/de/target-a"></iframe>'
            '<a src="/de/target-a">Text A</a>'
            '<img href="/de/image-a">'
        )
        report = []

        # do it
        translated = self._translated(markup, report=report)

        # postcondition
        self.assertEqual(translated, markup)
        self.assertEqual(report, [])


class TestBlockRichTextLinks(TestCase):
    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        folder = self.portal["de"]
        self.page = api.content.create(container=folder, type="Document", id="page-a", title="Page A")
        target = api.content.create(container=folder, type="Document", id="target-a", title="Target A")
        manager = ITranslationManager(target)
        manager.add_translation("en")
        api.content.rename(obj=manager.get_translation("en"), new_id="target-a-en")
        self.markup = '<p>Text A <a href="/de/target-a">Text B</a></p>'

    def _translated(self, block, report=None, check=False):
        result = postprocess_links(self.page, "blocks", {"block-a": block}, "en", report=report, check=check)

        return result["block-a"]

    def test_rich_text_under_a_text_key__points_its_links_at_the_translations(self):
        # setup
        block = {"@type": "block-a", "text": {"data": self.markup, "content-type": "text/html"}}

        # do it
        translated = self._translated(block)

        # postcondition
        self.assertEqual(
            translated["text"],
            {"data": '<p>Text A <a href="/en/target-a-en">Text B</a></p>', "content-type": "text/html"},
        )

    def test_rich_text_under_a_text_key__is_reported(self):
        # setup
        block = {"@type": "block-a", "text": {"data": self.markup}}
        report = []

        # do it
        self._translated(block, report=report)

        # postcondition
        self.assertEqual(report[0]["text"], "Text B")
        self.assertEqual(report[0]["after"], "/en/target-a-en")

    def test_rich_text_under_another_key__stays_unreported(self):
        # setup
        block = {"@type": "block-a", "field_a": {"data": self.markup}}
        report = []

        # do it
        translated = self._translated(block, report=report)

        # postcondition
        self.assertEqual(translated["field_a"], {"data": self.markup})
        self.assertEqual(report, [])

    def test_rich_text_under_a_key_named_in_the_settings__points_its_links_at_the_translations(self):
        # setup
        api.portal.set_registry_record(TEXT_KEYS, ["field_a"])
        block = {"@type": "block-a", "field_a": {"data": self.markup}}

        # do it
        translated = self._translated(block)

        # postcondition
        self.assertEqual(translated["field_a"], {"data": '<p>Text A <a href="/en/target-a-en">Text B</a></p>'})

    def test_check__changes_nothing_and_reports(self):
        # setup
        block = {"@type": "block-a", "text": {"data": self.markup}}
        report = []

        # do it
        translated = self._translated(block, report=report, check=True)

        # postcondition
        self.assertEqual(translated["text"], {"data": self.markup})
        self.assertEqual(report[0]["status"], "translatable")
