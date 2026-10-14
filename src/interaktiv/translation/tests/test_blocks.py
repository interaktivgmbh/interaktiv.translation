from types import SimpleNamespace
from unittest import TestCase, mock

from interaktiv.translation.blocks import (
    BLOCK_HANDLERS,
    BlockHandler,
    BlockHandlerRegistry,
    DefaultBlockHandler,
)
from interaktiv.translation.settings import Settings
from interaktiv.translation.extractors import BlocksExtractor
from interaktiv.translation.registry.translation import DEFAULT_BLOCK_TEXT_KEYS


class TestBlockHandler(BlockHandler):
    def texts(self, block):
        return [(("some_block_key",), block["some_block_key"])]

    def rebuild(self, block, translated):
        return dict(block, some_block_key=translated[0])


class TestBlockHandlerRegistry(TestCase):
    def test_register__hands_the_handler_back_by_type(self):
        # setup
        registry = BlockHandlerRegistry()
        handler = DefaultBlockHandler()

        # do it
        registry.register("teaser", handler)

        # postcondition
        self.assertIs(registry.get("teaser"), handler)
        self.assertEqual(registry.names(), ["teaser"])

    def test_register__refuses_a_handler_without_a_type(self):
        with self.assertRaises(ValueError):
            BlockHandlerRegistry().register("", DefaultBlockHandler())

    def test_get__answers_nothing_for_a_type_nobody_registered(self):
        self.assertIsNone(BlockHandlerRegistry().get("nope"))
        self.assertIsNone(BlockHandlerRegistry().get(None))

    def test_register__lets_a_project_replace_a_handler(self):
        # setup
        registry = BlockHandlerRegistry()
        registry.register("teaser", DefaultBlockHandler())
        replacement = DefaultBlockHandler()

        # do it
        registry.register("teaser", replacement)

        # postcondition
        self.assertIs(registry.get("teaser"), replacement)


class TestDefaultBlockHandler(TestCase):
    def test__init___gets_default_fields(self):
        # setup
        handler = DefaultBlockHandler()

        # do it
        text_keys = handler.text_keys

        # postcondition
        self.assertTupleEqual(text_keys, tuple(DEFAULT_BLOCK_TEXT_KEYS))

    def test_text_keys__reads_the_configured_registry_values(self):
        # setup
        handler = DefaultBlockHandler()
        configured = Settings(records=SimpleNamespace(block_text_keys=["field_a"]))

        # do it
        with mock.patch("interaktiv.translation.blocks.settings", return_value=configured):
            text_keys = handler.text_keys

        # postcondition
        self.assertTupleEqual(text_keys, ("field_a",))

    def test_text_keys__own_keys_win_over_the_configured_ones(self):
        # setup
        handler = DefaultBlockHandler(["field_b"])
        configured = Settings(records=SimpleNamespace(block_text_keys=["field_a"]))

        # do it
        with mock.patch("interaktiv.translation.blocks.settings", return_value=configured):
            text_keys = handler.text_keys

        # postcondition
        self.assertTupleEqual(text_keys, ("field_b",))

    def test_texts__reads_only_its_own_keys(self):
        # setup
        handler = DefaultBlockHandler(["field_a"])
        block = {"@type": "someblocktype", "field_a": "Value A", "field_b": "Value B"}

        # do it
        pairs = handler.texts(block)

        # postcondition
        self.assertEqual(pairs, [(("field_a",), "Value A")])

    def test_rebuild__writes_along_the_paths_texts_named(self):
        # setup
        handler = DefaultBlockHandler(["field_a", "field_b"])
        block = {
            "@type": "someblocktype",
            "value": [{"children": [{"field_a": "Haus"}]}], "field_b": "Maus"
        }

        # do it
        rebuilt = handler.rebuild(block, ["House", "Mouse"])

        # postcondition
        self.assertEqual(block["value"][0]["children"][0]["field_a"], "Haus")
        self.assertEqual(rebuilt["value"][0]["children"][0]["field_a"], "House")
        self.assertEqual(block["field_b"], "Maus")
        self.assertEqual(rebuilt["field_b"], "Mouse")


class TestDefaultBlockHandlerEscaping(TestCase):
    def test_texts__escapes_plain_leaves(self):
        # setup
        handler = DefaultBlockHandler(["title"])

        # do it
        pairs = handler.texts({"@type": "default_block_type", "title": "Value & more"})

        # postcondition
        self.assertEqual(pairs, [(("title",), "Value &amp; more")])

    def test_rebuild__unescapes_the_answers(self):
        # setup
        handler = DefaultBlockHandler(["title"])
        block = {"@type": "default_block_type", "title": "Value"}

        # do it
        rebuilt = handler.rebuild(block, ["Here&#x27;s a value"])

        # postcondition
        self.assertEqual(rebuilt["title"], "Here's a value")


class TestDefaultBlockHandlerSlateValue(TestCase):
    # The text block itself: a slate `value` beside its `plaintext`.

    def setUp(self):
        super().setUp()

        self.handler = DefaultBlockHandler()
        self.block = {
            "@type": "slate",
            "value": [
                {
                    "type": "p",
                    "children": [
                        {"text": "some "},
                        {"type": "strong", "children": [{"text": "text"}]}
                    ]
                }
            ],
            "plaintext": "some text"
        }

    def test_texts__serializes_the_whole_value_into_one_pair(self):
        # do it
        pairs = self.handler.texts(self.block)

        # postcondition
        self.assertEqual(pairs, [(("value",), "<p>some <strong>text</strong></p>")])

    def test_texts__answers_nothing_for_an_empty_value(self):
        # setup
        block = {"@type": "slate", "value": [], "plaintext": ""}

        # do it
        pairs = self.handler.texts(block)

        # postcondition
        self.assertEqual(pairs, [])

    def test_texts__sends_nothing_for_the_empty_default_paragraph(self):
        # setup — Volto writes this block on almost every page; it serializes
        # to <p></p>, and there is nothing in it to pay a provider for
        block = {
            "@type": "slate",
            "value": [{"type": "p", "children": [{"text": ""}]}],
            "plaintext": "",
        }

        # do it
        pairs = self.handler.texts(block)

        # postcondition
        self.assertEqual(pairs, [])

    def test_rebuild__keeps_the_empty_default_paragraph_as_it_is(self):
        # setup
        block = {
            "@type": "slate",
            "value": [{"type": "p", "children": [{"text": ""}]}],
            "plaintext": "",
        }

        # do it
        rebuilt = self.handler.rebuild(block, [])

        # postcondition — untouched, and still a valid slate tree
        self.assertEqual(rebuilt, block)

    def test_texts__falls_back_to_the_leaf_walk_for_an_empty_value_with_plaintext(self):
        # setup
        block = {"@type": "slate", "plaintext": "Value A"}

        # do it
        pairs = self.handler.texts(block)

        # postcondition
        self.assertEqual(pairs, [(("plaintext",), "Value A")])

    def test_texts__falls_back_to_the_leaf_walk_for_an_unknown_node_type(self):
        # setup
        block = {
            "@type": "slate",
            "value": [{"type": "unknown_type", "children": [{"text": "Value A"}]}],
            "plaintext": "Value A"
        }

        # do it
        pairs = self.handler.texts(block)

        # postcondition — the inherited walk reads the text leaves one by one.
        self.assertEqual(
            pairs,
            [
                (("value", 0, "children", 0, "text"), "Value A"),
                (("plaintext",), "Value A"),
            ],
        )

    def test_texts__falls_back_to_the_leaf_walk_for_a_value_that_is_no_tree(self):
        # setup — imports and direct PATCHes write shapes no slate tree
        # should hold, and plone.restapi accepts them
        block = {"@type": "slate", "value": "Value A", "plaintext": "Value A"}

        # do it
        pairs = self.handler.texts(block)

        # postcondition — the leaf walk reads what it can
        self.assertEqual(
            pairs,
            [
                (("value",), "Value A"),
                (("plaintext",), "Value A"),
            ],
        )

    def test_rebuild__parses_the_answer_back_into_the_value(self):
        # do it
        rebuilt = self.handler.rebuild(self.block, ["<p>etwas <strong>Text</strong></p>"])

        # postcondition
        expected_value = [
            {
                "type": "p",
                "children": [
                    {"text": "etwas "},
                    {"type": "strong", "children": [{"text": "Text"}]}
                ]
            }
        ]
        self.assertEqual(rebuilt["value"], expected_value)
        self.assertEqual(rebuilt["plaintext"], "etwas Text")
        self.assertEqual(rebuilt["@type"], "slate")
        self.assertEqual(self.block["plaintext"], "some text")

    def test_rebuild__keeps_the_block_when_nothing_readable_comes_back(self):
        # do it
        rebuilt = self.handler.rebuild(self.block, [""])

        # postcondition
        self.assertEqual(rebuilt, self.block)

    def test_rebuild__falls_back_to_the_leaf_walk_for_an_unknown_node_type(self):
        # setup
        block = {
            "@type": "slate",
            "value": [{"type": "unknown_type", "children": [{"text": "Value A"}]}],
            "plaintext": "Value A"
        }

        # do it
        rebuilt = self.handler.rebuild(block, ["VALUE A", "VALUE A"])

        # postcondition — written along the same paths the fallback walk read.
        self.assertEqual(rebuilt["value"][0]["children"][0]["text"], "VALUE A")
        self.assertEqual(rebuilt["value"][0]["type"], "unknown_type")
        self.assertEqual(rebuilt["plaintext"], "VALUE A")

    def test_rebuild__falls_back_to_the_leaf_walk_for_a_value_that_is_no_tree(self):
        # setup
        block = {"@type": "slate", "value": "Value A", "plaintext": "Value A"}

        # do it
        rebuilt = self.handler.rebuild(block, ["VALUE A", "VALUE A"])

        # postcondition — written along the same paths the fallback walk read
        self.assertEqual(rebuilt["value"], "VALUE A")
        self.assertEqual(rebuilt["plaintext"], "VALUE A")


class TestBlocksExtractorDispatch(TestCase):
    def test_texts__sends_a_block_to_the_handler_registered_for_its_type(self):
        # setup
        page = {
            "b1": {
                "@type": "test_block",
                "some_block_key": "Test Block Value",
                "other_key": "Other Value"},
            "b2": {
                "@type": "default_block_type",
                "title": "Title Value"
            },
        }

        # do it
        with mock.patch.dict(BLOCK_HANDLERS._handlers, {"test_block": TestBlockHandler()}):
            texts = BlocksExtractor().texts(page)

        # postcondition
        self.assertListEqual(texts, ["Test Block Value", "Title Value"])

    def test_rebuild__hands_every_handler_its_own_slice_of_the_answers(self):
        # setup
        page = {
            "b1": {"@type": "default_block_type", "title": "Title Value b1"},
            "b2": {"@type": "test_block", "some_block_key": "Test Block Value"},
            "b3": {"@type": "default_block_type", "title": "Title Value b3"},
        }
        extractor = BlocksExtractor()

        # do it
        with mock.patch.dict(BLOCK_HANDLERS._handlers, {"test_block": TestBlockHandler()}):
            texts = extractor.texts(page)
            translated_texts = [text.upper() for text in texts]
            rebuilt = extractor.rebuild(page, translated_texts)

        # postcondition
        self.assertEqual(rebuilt["b1"]["title"], "TITLE VALUE B1")
        self.assertEqual(rebuilt["b2"]["some_block_key"], "TEST BLOCK VALUE")
        self.assertEqual(rebuilt["b3"]["title"], "TITLE VALUE B3")

    def test_rebuild__keeps_a_block_whose_handler_gave_no_pairs(self):
        # setup
        page = {
            "b1": {"@type": "default_block_type", "untranslated_key": "somevalue"},
            "b2": {"@type": "default_block_type", "title": "Title Value b1"}
        }
        extractor = BlocksExtractor()

        # do it
        translated_texts = ["TITLE VALUE B1"]
        rebuilt = extractor.rebuild(page, translated_texts)

        # postcondition
        self.assertEqual(rebuilt["b1"], page["b1"])
        self.assertEqual(rebuilt["b2"]["title"], "TITLE VALUE B1")

    def test_texts__still_reads_an_entry_that_is_no_block(self):
        page = {"title": "Title Value", "b": {"@type": "default_block_type", "title": "Title Value b"}}
        extractor = BlocksExtractor()

        # do it
        texts = extractor.texts(page)
        translated_texts = [text.upper() for text in texts]
        rebuilt = extractor.rebuild(page, translated_texts)

        # postcondition
        self.assertEqual(texts, ["Title Value", "Title Value b"])
        self.assertEqual(rebuilt["title"], "TITLE VALUE")
        self.assertEqual(rebuilt["b"]["title"], "TITLE VALUE B")

    def test_texts__one_broken_block_does_not_cost_the_field(self):
        # setup — b1 holds a leaf without text; its error used to propagate
        # and leave the whole blocks field untranslated
        page = {
            "b1": {"@type": "slate", "value": [{"type": "p", "children": [{"text": None}]}]},
            "b2": {"@type": "default_block_type", "title": "Title Value"},
        }

        # do it
        texts = BlocksExtractor().texts(page)

        # postcondition — the healthy block still came through
        self.assertEqual(texts, ["Title Value"])


class TestDefaultBlockHandlerSlateTrees(TestCase):

    def setUp(self):
        super().setUp()

        self.handler = DefaultBlockHandler(["headline", "title", "field_to_translate"])
        self.value = [
            {
                "type": "p",
                "children": [
                    {"text": "Das Institut hat die Anlage gestern in "},
                    {"type": "strong", "children": [{"text": "Betrieb"}]},
                    {"text": " genommen."},
                ],
            }
        ]
        self.plaintext = "Das Institut hat die Anlage gestern in Betrieb genommen."
        self.html = "<p>Das Institut hat die Anlage gestern in <strong>Betrieb</strong> genommen.</p>"
        self.answer = "<p>The institute put the facility into <strong>operation</strong> yesterday.</p>"

    def test_texts__serializes_the_value_of_any_block_into_one_pair(self):
        # setup
        block = {"@type": "textWithBackground", "value": self.value, "plaintext": self.plaintext, "styles": {}}

        # do it
        pairs = self.handler.texts(block)

        # postcondition — one string, and plaintext is not sent a second time
        self.assertEqual(pairs, [(("value",), self.html)])

    def test_texts__reads_the_other_keys_of_the_block_beside_the_tree(self):
        # setup
        block = {
            "@type": "quote",
            "value": self.value,
            "plaintext": self.plaintext,
            "author": "Max Mustermann",
            "field_to_translate": "Direktor",
        }

        # do it
        pairs = self.handler.texts(block)

        # postcondition — the author is no text key and stays
        self.assertEqual(pairs, [(("value",), self.html), (("field_to_translate",), "Direktor")])

    def test_texts__finds_a_tree_under_a_nested_key(self):
        # setup
        block = {
            "@type": "tabBlock",
            "headline": "Tabs",
            "columns": [{"@id": "1", "title": "Erster Tab"}],
            "text-0": {"value": self.value, "plaintext": self.plaintext},
        }

        # do it
        pairs = self.handler.texts(block)

        # postcondition
        self.assertEqual(
            pairs,
            [
                (("headline",), "Tabs"),
                (("columns", 0, "title"), "Erster Tab"),
                (("text-0", "value"), self.html),
            ],
        )

    def test_texts__finds_a_tree_inside_a_container_block(self):
        # setup
        block = {
            "@type": "accordion",
            "data": {
                "blocks": {
                    "panel": {
                        "@type": "accordionPanel",
                        "title": "Der Titel",
                        "blocks": {"inner": {"@type": "slate", "value": self.value, "plaintext": self.plaintext}},
                        "blocks_layout": {"items": ["inner"]},
                    }
                },
                "blocks_layout": {"items": ["panel"]},
            },
        }

        # do it
        pairs = self.handler.texts(block)

        # postcondition
        self.assertEqual(
            pairs,
            [
                (("data", "blocks", "panel", "title"), "Der Titel"),
                (("data", "blocks", "panel", "blocks", "inner", "value"), self.html),
            ],
        )

    def test_texts__sends_plaintext_where_there_is_no_tree_to_read(self):
        # setup
        handler = DefaultBlockHandler(["plaintext"])
        block = {"@type": "textWithBackground", "value": [], "plaintext": "Value A"}

        # do it
        pairs = handler.texts(block)

        # postcondition
        self.assertEqual(pairs, [(("plaintext",), "Value A")])

    def test_texts__leaves_a_list_that_is_no_tree_to_the_leaf_walk(self):
        # setup
        block = {"@type": "someblock", "value": [{"@id": "1", "title": "Eintrag"}], "plaintext": "Eintrag"}

        # do it
        pairs = self.handler.texts(block)

        # postcondition — an object list keeps being read key by key
        self.assertEqual(pairs, [(("value", 0, "title"), "Eintrag")])

    def test_rebuild__keeps_the_other_keys_of_a_list_that_only_looks_like_a_tree(self):
        # setup — items with a `text` but no element on top: no slate tree
        handler = DefaultBlockHandler(["text"])
        block = {"@type": "someblock", "value": [{"@id": "1", "text": "Value A", "url": "/target"}]}

        # do it
        pairs = handler.texts(block)
        rebuilt = handler.rebuild(block, ["Value B"])

        # postcondition — read key by key, the item keeps @id and url
        self.assertEqual(pairs, [(("value", 0, "text"), "Value A")])
        self.assertEqual(rebuilt["value"], [{"@id": "1", "text": "Value B", "url": "/target"}])

    def test_rebuild__writes_the_tree_and_its_plaintext_back(self):
        # setup
        block = {
            "@type": "tabBlock",
            "headline": "Tabs",
            "text-0": {"value": self.value, "plaintext": self.plaintext},
        }

        # do it
        rebuilt = self.handler.rebuild(block, ["Tabs", self.answer])

        # postcondition
        self.assertEqual(
            rebuilt["text-0"]["value"],
            [
                {
                    "type": "p",
                    "children": [
                        {"text": "The institute put the facility into "},
                        {"type": "strong", "children": [{"text": "operation"}]},
                        {"text": " yesterday."},
                    ],
                }
            ],
        )
        self.assertEqual(rebuilt["text-0"]["plaintext"], "The institute put the facility into operation yesterday.")
        self.assertEqual(block["text-0"]["plaintext"], self.plaintext)

    def test_rebuild__keeps_the_tree_when_nothing_readable_comes_back(self):
        # setup
        block = {"@type": "quote", "value": self.value, "plaintext": self.plaintext}

        # do it
        rebuilt = self.handler.rebuild(block, [""])

        # postcondition
        self.assertEqual(rebuilt, block)


class TestDefaultBlockHandlerRichText(TestCase):

    def setUp(self):
        super().setUp()

        self.handler = DefaultBlockHandler(["heading", "description"])
        self.block = {
            "@type": "icon",
            "heading": "Forschung",
            "description": {"data": "<p>Die <b>Anlage</b> läuft.</p>", "content-type": "text/html"},
        }

    def test_texts__sends_the_html_under_a_text_key_as_it_is(self):
        # do it
        pairs = self.handler.texts(self.block)

        # postcondition — not escaped: the widget wrote HTML on purpose
        self.assertEqual(
            pairs,
            [(("heading",), "Forschung"), (("description", "data"), "<p>Die <b>Anlage</b> läuft.</p>")],
        )

    def test_texts__skips_an_empty_rich_text(self):
        # setup
        block = {"@type": "icon", "description": {"data": "", "content-type": "text/html"}}

        # do it
        pairs = self.handler.texts(block)

        # postcondition
        self.assertEqual(pairs, [])

    def test_texts__walks_a_data_dict_under_a_key_that_is_no_text_key(self):
        # setup — an accordion keeps its panels under `data`
        handler = DefaultBlockHandler(["title"])
        block = {"@type": "accordion", "data": {"blocks": {"p1": {"title": "Panel"}}}}

        # do it
        pairs = handler.texts(block)

        # postcondition
        self.assertEqual(pairs, [(("data", "blocks", "p1", "title"), "Panel")])

    def test_rebuild__writes_the_answer_back_and_keeps_the_rest_of_the_dict(self):
        # do it
        rebuilt = self.handler.rebuild(self.block, ["Research", "<p>The <b>facility</b> is running.</p>"])

        # postcondition
        self.assertEqual(rebuilt["heading"], "Research")
        self.assertEqual(
            rebuilt["description"],
            {"data": "<p>The <b>facility</b> is running.</p>", "content-type": "text/html"},
        )
        self.assertEqual(self.block["description"]["data"], "<p>Die <b>Anlage</b> läuft.</p>")

    def test_rebuild__does_not_unescape_html(self):
        # setup
        block = {"@type": "icon", "description": {"data": "<p>A &amp; B</p>"}}

        # do it
        rebuilt = self.handler.rebuild(block, ["<p>A &amp; B</p>"])

        # postcondition — the entity stays an entity, as the widget stores it
        self.assertEqual(rebuilt["description"]["data"], "<p>A &amp; B</p>")
