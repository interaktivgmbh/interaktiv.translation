from unittest import TestCase

from interaktiv.translation.extractors import BlocksExtractor, TextExtractor, default_extractors

SLATE_PAGE = {
    "b1": {
        "@type": "slate",
        "value": [{"type": "p", "children": [{"text": "Guten Tag"}]}],
        "plaintext": "Guten Tag",
    },
    "b2": {
        "@type": "image",
        "url": "/bilder/hero.jpg",
        "alt": "Ein Bild",
        "align": "full",
        "size": "l",
        "styles": {"role": "showcase", "surface": "subtle"},
    },
    "b3": {
        "@type": "listing",
        "headline": "Aktuelles",
        "querystring": {
            "query": [{"i": "portal_type", "o": "any", "v": ["News Item"]}],
            "sort_on": "effective",
        },
    },
}


class TestBlocksExtractor(TestCase):
    def test_texts__finds_prose_wherever_it_sits_in_the_tree(self):
        # do it
        texts = BlocksExtractor().texts(SLATE_PAGE)

        # postcondition — the slate block travels as one HTML string, the
        # other blocks leaf by leaf.
        self.assertEqual(sorted(texts), sorted(["<p>Guten Tag</p>", "Ein Bild", "Aktuelles"]))

    def test_texts__leaves_structure_alone(self):
        # postcondition — a path, a portal type, a sort index and a size are
        # not prose, and a translated one breaks the page.
        texts = BlocksExtractor().texts(SLATE_PAGE)
        for structural in ("/bilder/hero.jpg", "full", "l", "News Item", "effective", "slate"):
            self.assertNotIn(structural, texts)

    def test_rebuild__puts_every_answer_back_where_it_came_from(self):
        # setup
        extractor = BlocksExtractor()
        texts = extractor.texts(SLATE_PAGE)

        # do it
        rebuilt = extractor.rebuild(SLATE_PAGE, [text.upper() for text in texts])

        # postcondition
        self.assertEqual(rebuilt["b1"]["value"][0]["children"][0]["text"], "GUTEN TAG")
        self.assertEqual(rebuilt["b2"]["alt"], "EIN BILD")
        self.assertEqual(rebuilt["b3"]["headline"], "AKTUELLES")
        # Structure untouched, and the original not mutated.
        self.assertEqual(rebuilt["b2"]["url"], "/bilder/hero.jpg")
        self.assertEqual(rebuilt["b3"]["querystring"]["sort_on"], "effective")
        self.assertEqual(SLATE_PAGE["b2"]["alt"], "Ein Bild")

    def test_texts__skips_whitespace(self):
        self.assertEqual(BlocksExtractor().texts({"b": {"title": "   "}}), [])

    def test_texts__never_reads_the_style_menus_values(self):
        # postcondition — the style menu's values are English words, and the
        # keys they sit under are prose elsewhere: a contact's `role` is a job
        # title, a block's `role` is how it should look.
        page = {
            "b": {
                "styles": {"role": "showcase", "surface": "subtle"},
                "people": [{"role": "Studienberatung"}],
            }
        }

        self.assertEqual(BlocksExtractor(["role", "surface"]).texts(page), ["Studienberatung"])

    def test_texts__reads_the_keys_it_was_given(self):
        # A block type a project writes itself names its fields as it likes,
        # and its prose is invisible to a reading that only knows the stock
        # names.
        page = {"b": {"@type": "ownCard", "eyebrow": "Forschung", "profile_label": "Beratung"}}

        self.assertEqual(BlocksExtractor().texts(page), ["Forschung"])
        self.assertEqual(
            sorted(BlocksExtractor(["eyebrow", "profile_label"]).texts(page)),
            ["Beratung", "Forschung"],
        )


class TestExtractorRegistry(TestCase):
    def test_for_value__reads_a_mapping_as_blocks_and_a_string_as_text(self):
        registry = default_extractors()

        self.assertIsInstance(registry.for_value({"b": {}}), BlocksExtractor)
        self.assertIsInstance(registry.for_value("Hallo"), TextExtractor)

    def test_for_value__answers_nothing_for_a_shape_it_does_not_know(self):
        self.assertIsNone(default_extractors().for_value(42))

    def test_register__lets_a_customer_shadow_a_stock_extractor(self):
        # setup
        class OwnText(TextExtractor):
            pass

        registry = default_extractors()

        # do it
        registry.register(OwnText())

        # postcondition
        self.assertIsInstance(registry.for_value("Hallo"), OwnText)


class TestTextExtractor(TestCase):
    def test_texts__escapes_a_plain_string_for_the_html_reading_provider(self):
        self.assertEqual(TextExtractor().texts("a < b & 'c'"), ["a &lt; b &amp; 'c'"])

    def test_rebuild__unescapes_the_answer(self):
        # DeepL answers an apostrophe in HTML mode as an entity
        self.assertEqual(TextExtractor().rebuild("", ["Here&#x27;s a picture"]), "Here's a picture")
