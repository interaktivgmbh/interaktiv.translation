from unittest import TestCase

from interaktiv.translation.helpers.slate import SlateHTMLParser, SlateHTMLSerializer


class TestSlateHTMLSerializer(TestCase):
    def setUp(self):
        super().setUp()

        self.serializer = SlateHTMLSerializer()

    def test_slate_html_serializer__serialize__text_node(self):
        # setup
        nodes = [{"text": "some text"}]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition
        self.assertEqual(result, "some text")

    def test_slate_html_serializer__serialize__block_with_inline_node(self):
        # setup
        nodes = [{"type": "p", "children": [{"text": "some "}, {"type": "strong", "children": [{"text": "text"}]}]}]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition
        self.assertEqual(result, "<p>some <strong>text</strong></p>")

    def test_slate_html_serializer__serialize__link_node(self):
        # setup
        nodes = [
            {
                "type": "p",
                "children": [
                    {"type": "link", "data": {"url": "https://interaktiv.de"}, "children": [{"text": "link"}]}
                ],
            }
        ]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition
        self.assertEqual(result, '<p><a href="https://interaktiv.de">link</a></p>')

    def test_slate_html_serializer__serialize__escapes_text(self):
        # setup
        nodes = [{"type": "p", "children": [{"text": "1 < 2 & 3 > 2"}]}]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition
        self.assertEqual(result, "<p>1 &lt; 2 &amp; 3 &gt; 2</p>")

    def test_slate_html_serializer__serialize__list_nodes(self):
        # setup
        nodes = [
            {
                "type": "ul",
                "children": [
                    {"type": "li", "children": [{"text": "Item A"}]},
                    {"type": "li", "children": [{"text": "Item B"}]},
                ],
            }
        ]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition
        self.assertEqual(result, "<ul><li>Item A</li><li>Item B</li></ul>")

    def test_slate_html_serializer__serialize__refuses_an_unknown_node_type(self):
        with self.assertRaises(ValueError):
            self.serializer.serialize([{"type": "unknown_type", "children": [{"text": "some text"}]}])

    def test_slate_html_serializer__roundtrip_with_the_parser(self):
        # setup
        nodes = [
            {
                "type": "p",
                "children": [
                    {"text": "some "},
                    {"type": "strong", "children": [{"text": "text"}]},
                    {"text": " and a "},
                    {"type": "link", "data": {"url": "https://interaktiv.de"}, "children": [{"text": "link"}]},
                ],
            },
            {
                "type": "ul",
                "children": [
                    {"type": "li", "children": [{"text": "Item A"}]},
                    {"type": "li", "children": [{"text": "Item B"}]},
                ],
            },
        ]
        parser = SlateHTMLParser()

        # do it
        html = self.serializer.serialize(nodes)
        parser.feed(data=html)
        parsed_nodes, _plaintext = parser.get_result()

        # postcondition
        self.assertEqual(parsed_nodes, nodes)

    def test_slate_html_serializer__serialize__numbers_an_element_with_properties_of_its_own(self):
        # setup
        nodes = [{"type": "p", "styleName": "style-a", "children": [{"text": "some text"}]}]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition — the properties stay here, only the number travels
        self.assertEqual(result, '<p data-slate-node="1">some text</p>')
        self.assertEqual(self.serializer.node_properties, {"1": {"styleName": "style-a"}})

    def test_slate_html_serializer__serialize__numbers_a_text_node_with_properties_of_its_own(self):
        # setup
        nodes = [{"type": "p", "children": [{"text": "some "}, {"text": "text", "style-a": True}]}]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition
        self.assertEqual(result, '<p>some <span data-slate-node="1">text</span></p>')
        self.assertEqual(self.serializer.node_properties, {"1": {"style-a": True}})

    def test_slate_html_serializer__serialize__numbers_a_link_with_more_data_than_its_url(self):
        # setup
        nodes = [
            {
                "type": "link",
                "data": {"url": "https://interaktiv.de", "target": "_blank", "title": "Title A"},
                "children": [{"text": "link"}],
            }
        ]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition — the url is the href and not kept twice
        self.assertEqual(result, '<a href="https://interaktiv.de" data-slate-node="1">link</a>')
        self.assertEqual(self.serializer.node_properties, {"1": {"data": {"target": "_blank", "title": "Title A"}}})

    def test_slate_html_serializer__serialize__numbers_a_parent_before_its_children(self):
        # setup
        nodes = [
            {"type": "p", "styleName": "style-a", "children": [{"text": "text a", "style-b": True}]},
            {"type": "p", "styleName": "style-c", "children": [{"text": "text b"}]},
        ]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition
        self.assertEqual(
            result,
            '<p data-slate-node="1"><span data-slate-node="2">text a</span></p><p data-slate-node="3">text b</p>',
        )

    def test_slate_html_serializer__serialize__starts_to_number_anew_for_each_tree(self):
        # setup
        self.serializer.serialize([{"type": "p", "styleName": "style-a", "children": [{"text": "text a"}]}])

        # do it
        result = self.serializer.serialize([{"type": "p", "styleName": "style-b", "children": [{"text": "text b"}]}])

        # postcondition
        self.assertEqual(result, '<p data-slate-node="1">text b</p>')
        self.assertEqual(self.serializer.node_properties, {"1": {"styleName": "style-b"}})

    def test_slate_html_serializer__serialize__sends_no_tag_for_an_empty_text_node(self):
        # setup
        nodes = [{"type": "p", "children": [{"text": "", "style-a": True}, {"text": "some text"}]}]

        # do it
        result = self.serializer.serialize(nodes)

        # postcondition
        self.assertEqual(result, "<p>some text</p>")
        self.assertEqual(self.serializer.node_properties, {})

    def test_slate_html_serializer__roundtrip_with_the_parser__keeps_the_properties(self):
        # setup
        nodes = [
            {
                "type": "p",
                "styleName": "style-a",
                "children": [
                    {"text": "some "},
                    {"type": "strong", "children": [{"text": "text", "style-b": True}]},
                    {"text": " and a "},
                    {
                        "type": "link",
                        "data": {"url": "https://interaktiv.de", "target": "_blank", "title": "Title A"},
                        "children": [{"text": "styled", "style-b": True}, {"text": " link"}],
                    },
                ],
            },
            {
                "type": "ul",
                "styleName": "style-a",
                "children": [
                    {"type": "li", "children": [{"text": "Item A"}]},
                    {"type": "li", "children": [{"text": "Item "}, {"text": "B", "style-b": True}]},
                ],
            },
        ]

        # do it
        html = self.serializer.serialize(nodes)
        parser = SlateHTMLParser(self.serializer.node_properties)
        parser.feed(data=html)
        parsed_nodes, _plaintext = parser.get_result()

        # postcondition
        self.assertEqual(parsed_nodes, nodes)
