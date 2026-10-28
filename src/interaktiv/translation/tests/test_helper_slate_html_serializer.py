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
