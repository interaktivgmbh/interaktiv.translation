from unittest import TestCase

from interaktiv.translation.helpers.slate import SlateHTMLParser


class TestSlateHTMLParser(TestCase):
    def setUp(self):
        super().setUp()

        self.parser = SlateHTMLParser()

    def test_slate_html_parser__handle_starttag__inline_tag(self):
        # setup
        tag = "b"
        attrs = {}

        # do it
        self.parser.handle_starttag(tag, attrs)

        # postcondition
        expected_stack = [[{"type": "strong", "children": []}], []]
        self.assertEqual(self.parser.stack, expected_stack)

    def test_slate_html_parser__handle_starttag__a_tag(self):
        # setup
        tag = "a"
        attrs = {"href": "https://interaktiv.de"}

        # do it
        self.parser.handle_starttag(tag, attrs)

        # postcondition
        expected_stack = [[{"type": "link", "data": {"url": "https://interaktiv.de"}, "children": []}], []]
        self.assertEqual(self.parser.stack, expected_stack)

    def test_slate_html_parser__handle_endtag__keeps_stack_entry(self):
        # setup
        self.parser.stack = [1, 2, 3]
        tag = "unkown_tag"

        # do it
        self.parser.handle_endtag(tag)

        # postcondition
        self.assertEqual(self.parser.stack, [1, 2, 3])

    def test_slate_html_parser__handle_endtag__removes_stack_entry(self):
        # setup — the closing tag matches the innermost open one
        self.parser.stack = [1, 2, [{"text": "some text"}]]
        self.parser.open_tags = ["p", "strong"]
        tag = "b"

        # do it
        self.parser.handle_endtag(tag)

        # postcondition
        self.assertEqual(self.parser.stack, [1, 2])
        self.assertEqual(self.parser.open_tags, ["p"])

    def test_slate_html_parser__handle_endtag__ignores_a_tag_that_is_not_open(self):
        # setup
        self.parser.stack = [1, 2, [{"text": "some text"}]]
        self.parser.open_tags = ["p", "strong"]
        tag = "ul"

        # do it
        self.parser.handle_endtag(tag)

        # postcondition — nothing was closed
        self.assertEqual(self.parser.stack, [1, 2, [{"text": "some text"}]])
        self.assertEqual(self.parser.open_tags, ["p", "strong"])

    def test_slate_html_parser__handle_data(self):
        # setup
        data = "some text"

        # do it
        self.parser.handle_data(data)

        # postcondition
        self.assertEqual(self.parser.text_parts, ["some text"])
        self.assertEqual(self.parser.stack, [[{"text": "some text"}]])

    def test_slate_html_parser__get_result__no_data(self):
        # do it
        result = self.parser.get_result()

        # postcondition
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        self.assertEqual(result[0], [])
        self.assertEqual(result[1], "")

    def test_slate_html_parser__get_result(self):
        # setup
        self.parser.text_parts = ["some ", "text"]
        parser_result = [
            {"type": "p", "children": [{"text": "some "}, {"type": "strong", "children": [{"text": "text"}]}]}
        ]
        self.parser.result = parser_result

        # do it
        result = self.parser.get_result()

        # postcondition
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        self.assertEqual(result[0], parser_result)
        self.assertEqual(result[1], "some text")

    def test_slate_html_parser__feed(self):
        # setup
        html = "<p>some <b>text</b></p>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        expected_slate_value = [
            {"type": "p", "children": [{"text": "some "}, {"type": "strong", "children": [{"text": "text"}]}]}
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], "some text")

    def test_slate_html_parser__handle_data__skips_formatting_whitespace_between_blocks(self):
        # setup
        html = "<ul>\n  <li>Item A</li>\n  <li>Item B</li>\n</ul>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                "type": "ul",
                "children": [
                    {"type": "li", "children": [{"text": "Item A"}]},
                    {"type": "li", "children": [{"text": "Item B"}]},
                ],
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], "Item AItem B")

    def test_slate_html_parser__handle_data__keeps_the_space_between_inline_tags(self):
        # setup
        html = "<p><b>Value A</b> <b>Value B</b></p>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                "type": "p",
                "children": [
                    {"type": "strong", "children": [{"text": "Value A"}]},
                    {"text": " "},
                    {"type": "strong", "children": [{"text": "Value B"}]},
                ],
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], "Value A Value B")

    def test_slate_html_parser__handle_starttag__sub_sup_del(self):
        # setup
        html = "<p>H<sub>2</sub>O<sup>+</sup><del>old</del></p>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                "type": "p",
                "children": [
                    {"text": "H"},
                    {"type": "sub", "children": [{"text": "2"}]},
                    {"text": "O"},
                    {"type": "sup", "children": [{"text": "+"}]},
                    {"type": "del", "children": [{"text": "old"}]},
                ],
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], "H2O+old")

    def test_slate_html_parser__link(self):
        # setup
        html = '<p>some <a href="https://interaktiv.de">link</a></p>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        expected_slate_value = [
            {
                "type": "p",
                "children": [
                    {"text": "some "},
                    {"type": "link", "data": {"url": "https://interaktiv.de"}, "children": [{"text": "link"}]},
                ],
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], "some link")

    def test_slate_html_parser__feed__empty_element_gets_an_empty_text_child(self):
        # setup — slate's invariant: every element holds at least one text child
        html = "<p></p>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [{"type": "p", "children": [{"text": ""}]}]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], "")

    def test_slate_html_parser__feed__empty_list_item_gets_an_empty_text_child(self):
        # setup
        html = "<ul><li></li></ul>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [{"type": "ul", "children": [{"type": "li", "children": [{"text": ""}]}]}]
        self.assertEqual(result[0], expected_slate_value)

    def test_slate_html_parser__feed__ignores_a_stray_closing_tag(self):
        # setup — a provider does not guarantee balanced HTML; the stray
        # </strong> must not shift " Welt" out of the paragraph
        html = "<p>Hallo</strong> Welt</p>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [{"type": "p", "children": [{"text": "Hallo"}, {"text": " Welt"}]}]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], "Hallo Welt")

    def test_slate_html_parser__feed__closing_a_parent_closes_the_open_child(self):
        # setup — the unclosed <strong> must not swallow the second paragraph
        html = "<p>Hallo <strong>Welt</p><p>Zwei</p>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition — two paragraphs side by side, no p inside a p
        expected_slate_value = [
            {"type": "p", "children": [{"text": "Hallo "}, {"type": "strong", "children": [{"text": "Welt"}]}]},
            {"type": "p", "children": [{"text": "Zwei"}]},
        ]
        self.assertEqual(result[0], expected_slate_value)

    def test_slate_html_parser__feed__closes_what_a_truncated_answer_left_open(self):
        # setup
        html = "<p>Hallo <strong>Welt"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {"type": "p", "children": [{"text": "Hallo "}, {"type": "strong", "children": [{"text": "Welt"}]}]}
        ]
        self.assertEqual(result[0], expected_slate_value)

    def test_slate_html_parser__feed__an_alias_closing_tag_finds_its_opener(self):
        # setup — <b> opens as strong; </b> has to close it all the same
        html = "<p><b>Hallo</b> Welt</p>"

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {"type": "p", "children": [{"type": "strong", "children": [{"text": "Hallo"}]}, {"text": " Welt"}]}
        ]
        self.assertEqual(result[0], expected_slate_value)


class TestSlateHTMLParserNodeProperties(TestCase):
    # What the serializer kept of the tree comes back by the number of the node.

    def setUp(self):
        super().setUp()

        self.node_properties = {
            "1": {"styleName": "style-a"},
            "2": {"style-b": True},
            "3": {"data": {"target": "_blank", "title": "Title A"}},
        }
        self.parser = SlateHTMLParser(self.node_properties)

    def _parsed(self, html):
        self.parser.feed(data=html)

        return self.parser.get_result()

    def test_slate_html_parser__feed__gives_an_element_its_properties_back(self):
        # do it
        value, _plaintext = self._parsed('<p data-slate-node="1">text a</p>')

        # postcondition
        self.assertEqual(value, [{"type": "p", "styleName": "style-a", "children": [{"text": "text a"}]}])

    def test_slate_html_parser__feed__gives_a_text_node_its_properties_back(self):
        # do it
        value, plaintext = self._parsed('<p>some <span data-slate-node="2">text</span> here</p>')

        # postcondition — the tag itself leaves no element behind
        self.assertEqual(
            value,
            [{"type": "p", "children": [{"text": "some "}, {"text": "text", "style-b": True}, {"text": " here"}]}],
        )
        self.assertEqual(plaintext, "some text here")

    def test_slate_html_parser__feed__gives_a_link_its_data_back_beside_the_url(self):
        # do it
        value, _plaintext = self._parsed('<a href="https://interaktiv.de" data-slate-node="3">link</a>')

        # postcondition
        self.assertEqual(
            value,
            [
                {
                    "type": "link",
                    "data": {"url": "https://interaktiv.de", "target": "_blank", "title": "Title A"},
                    "children": [{"text": "link"}],
                }
            ],
        )

    def test_slate_html_parser__feed__follows_a_text_node_the_translation_moved(self):
        # do it — "text styled" came back as "styled text"
        value, _plaintext = self._parsed('<p><span data-slate-node="2">styled</span> text</p>')

        # postcondition
        self.assertEqual(value, [{"type": "p", "children": [{"text": "styled", "style-b": True}, {"text": " text"}]}])

    def test_slate_html_parser__feed__gives_every_part_of_a_split_text_node_the_properties(self):
        # do it
        value, _plaintext = self._parsed(
            '<p><span data-slate-node="2">text a</span> and <span data-slate-node="2">text b</span></p>'
        )

        # postcondition
        self.assertEqual(
            value,
            [
                {
                    "type": "p",
                    "children": [
                        {"text": "text a", "style-b": True},
                        {"text": " and "},
                        {"text": "text b", "style-b": True},
                    ],
                }
            ],
        )

    def test_slate_html_parser__feed__gives_the_text_of_an_element_inside_a_leaf_tag_the_properties(self):
        # do it — the tags came back the other way round
        value, _plaintext = self._parsed('<p><span data-slate-node="2"><strong>text a</strong></span></p>')

        # postcondition
        self.assertEqual(
            value,
            [{"type": "p", "children": [{"type": "strong", "children": [{"text": "text a", "style-b": True}]}]}],
        )

    def test_slate_html_parser__feed__ends_a_leaf_tag_left_open_with_its_element(self):
        # do it
        value, _plaintext = self._parsed('<p><span data-slate-node="2">text a</p><p>text b</p>')

        # postcondition
        self.assertEqual(
            value,
            [
                {"type": "p", "children": [{"text": "text a", "style-b": True}]},
                {"type": "p", "children": [{"text": "text b"}]},
            ],
        )

    def test_slate_html_parser__feed__reads_a_number_the_tree_did_not_have_as_no_properties(self):
        # do it
        value, _plaintext = self._parsed('<p data-slate-node="9"><span data-slate-node="8">text a</span></p>')

        # postcondition
        self.assertEqual(value, [{"type": "p", "children": [{"text": "text a"}]}])

    def test_slate_html_parser__feed__reads_a_tag_that_lost_its_number_as_before(self):
        # do it
        value, _plaintext = self._parsed('<p><span>text a</span> <a href="https://interaktiv.de">link</a></p>')

        # postcondition
        self.assertEqual(
            value,
            [
                {
                    "type": "p",
                    "children": [
                        {"text": "text a"},
                        {"text": " "},
                        {"type": "link", "data": {"url": "https://interaktiv.de"}, "children": [{"text": "link"}]},
                    ],
                }
            ],
        )

    def test_slate_html_parser__feed__hands_out_properties_of_its_own_to_every_node(self):
        # do it
        value, _plaintext = self._parsed('<a href="/a" data-slate-node="3">a</a><a href="/b" data-slate-node="3">b</a>')
        value[0]["data"]["title"] = "Title B"

        # postcondition
        self.assertEqual(value[1]["data"]["title"], "Title A")
        self.assertEqual(self.node_properties["3"]["data"]["title"], "Title A")


class SpanElementParser(SlateHTMLParser):
    # a parser that knows the leaf tag as an element of its own
    INLINE_TAGS = SlateHTMLParser.INLINE_TAGS | frozenset({"span"})
    TAG_MAP = SlateHTMLParser.TAG_MAP | {"span": "span"}


class TestSlateHTMLParserLeafTagAsElement(TestCase):
    def test_slate_html_parser__feed__reads_the_leaf_tag_without_a_number_as_the_element_it_is(self):
        # setup
        parser = SpanElementParser({"1": {"style-b": True}})

        # do it
        parser.feed(data='<p><span>text a</span> <span data-slate-node="1">text b</span></p>')
        value, _plaintext = parser.get_result()

        # postcondition — only the numbered one is the tag of a text node
        self.assertEqual(
            value,
            [
                {
                    "type": "p",
                    "children": [
                        {"type": "span", "children": [{"text": "text a"}]},
                        {"text": " "},
                        {"text": "text b", "style-b": True},
                    ],
                }
            ],
        )

    def test_slate_html_parser__feed__closes_each_tag_of_that_name_as_what_it_was_opened(self):
        # setup
        parser = SpanElementParser({"1": {"style-b": True}})

        # do it
        parser.feed(data='<p><span data-slate-node="1">text a <span>text b</span> text c</span> text d</p>')
        value, _plaintext = parser.get_result()

        # postcondition
        self.assertEqual(
            value,
            [
                {
                    "type": "p",
                    "children": [
                        {"text": "text a ", "style-b": True},
                        {"type": "span", "children": [{"text": "text b", "style-b": True}]},
                        {"text": " text c", "style-b": True},
                        {"text": " text d"},
                    ],
                }
            ],
        )
