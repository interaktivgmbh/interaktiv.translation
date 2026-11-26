import plone.api as api
from plone.app.multilingual.interfaces import ITranslationManager

from interaktiv.translation.helpers.links import postprocess_links
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING, TestCase


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
        api.content.create(container=folder, type="Document", id="target-b", title="Target B")
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
