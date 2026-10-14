from unittest import TestCase

from interaktiv.translation.helpers.slate import SlateHTMLParser


class TestSlateHTMLParser(TestCase):
    def setUp(self):
        super().setUp()

        self.parser = SlateHTMLParser()

    def test_slate_html_parser__handle_starttag__inline_tag(self):
        # setup
        tag = 'b'
        attrs = {}

        # do it
        self.parser.handle_starttag(tag, attrs)

        # postcondition
        expected_stack = [
            [
                {'type': 'strong', 'children': []}
            ],
            []
        ]
        self.assertEqual(self.parser.stack, expected_stack)

    def test_slate_html_parser__handle_starttag__a_tag(self):
        # setup
        tag = 'a'
        attrs = {'href': 'https://interaktiv.de'}

        # do it
        self.parser.handle_starttag(tag, attrs)

        # postcondition
        expected_stack = [
            [
                {'type': 'link', 'data': {'url': 'https://interaktiv.de'}, 'children': []}
            ],
            []
        ]
        self.assertEqual(self.parser.stack, expected_stack)

    def test_slate_html_parser__handle_endtag__keeps_stack_entry(self):
        # setup
        self.parser.stack = [1, 2, 3]
        tag = 'unkown_tag'

        # do it
        self.parser.handle_endtag(tag)

        # postcondition
        self.assertEqual(self.parser.stack, [1, 2, 3])

    def test_slate_html_parser__handle_endtag__removes_stack_entry(self):
        # setup — the closing tag matches the innermost open one
        self.parser.stack = [1, 2, [{'text': 'some text'}]]
        self.parser.open_tags = ['p', 'strong']
        tag = 'b'

        # do it
        self.parser.handle_endtag(tag)

        # postcondition
        self.assertEqual(self.parser.stack, [1, 2])
        self.assertEqual(self.parser.open_tags, ['p'])

    def test_slate_html_parser__handle_endtag__ignores_a_tag_that_is_not_open(self):
        # setup
        self.parser.stack = [1, 2, [{'text': 'some text'}]]
        self.parser.open_tags = ['p', 'strong']
        tag = 'ul'

        # do it
        self.parser.handle_endtag(tag)

        # postcondition — nothing was closed
        self.assertEqual(self.parser.stack, [1, 2, [{'text': 'some text'}]])
        self.assertEqual(self.parser.open_tags, ['p', 'strong'])

    def test_slate_html_parser__handle_data(self):
        # setup
        data = 'some text'

        # do it
        self.parser.handle_data(data)

        # postcondition
        self.assertEqual(self.parser.text_parts, ['some text'])
        self.assertEqual(self.parser.stack, [[{'text': 'some text'}]])

    def test_slate_html_parser__get_result__no_data(self):
        # do it
        result = self.parser.get_result()

        # postcondition
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        self.assertEqual(result[0], [])
        self.assertEqual(result[1], '')

    def test_slate_html_parser__get_result(self):
        # setup
        self.parser.text_parts = ['some ', 'text']
        parser_result = [
            {
                'type': 'p',
                'children': [
                    {'text': 'some '},
                    {'type': 'strong', 'children': [{'text': 'text'}]}
                ]
            }
        ]
        self.parser.result = parser_result

        # do it
        result = self.parser.get_result()

        # postcondition
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        self.assertEqual(result[0], parser_result)
        self.assertEqual(result[1], 'some text')

    def test_slate_html_parser__feed(self):
        # setup
        html = '<p>some <b>text</b></p>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        expected_slate_value = [
            {
                'type': 'p',
                'children': [
                    {'text': 'some '},
                    {'type': 'strong', 'children': [{'text': 'text'}]}
                ]
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], 'some text')

    def test_slate_html_parser__handle_data__skips_formatting_whitespace_between_blocks(self):
        # setup
        html = '<ul>\n  <li>Item A</li>\n  <li>Item B</li>\n</ul>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                'type': 'ul',
                'children': [
                    {'type': 'li', 'children': [{'text': 'Item A'}]},
                    {'type': 'li', 'children': [{'text': 'Item B'}]}
                ]
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], 'Item AItem B')

    def test_slate_html_parser__handle_data__keeps_the_space_between_inline_tags(self):
        # setup
        html = '<p><b>Value A</b> <b>Value B</b></p>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                'type': 'p',
                'children': [
                    {'type': 'strong', 'children': [{'text': 'Value A'}]},
                    {'text': ' '},
                    {'type': 'strong', 'children': [{'text': 'Value B'}]}
                ]
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], 'Value A Value B')

    def test_slate_html_parser__handle_starttag__sub_sup_del(self):
        # setup
        html = '<p>H<sub>2</sub>O<sup>+</sup><del>old</del></p>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                'type': 'p',
                'children': [
                    {'text': 'H'},
                    {'type': 'sub', 'children': [{'text': '2'}]},
                    {'text': 'O'},
                    {'type': 'sup', 'children': [{'text': '+'}]},
                    {'type': 'del', 'children': [{'text': 'old'}]}
                ]
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], 'H2O+old')

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
                'type': 'p',
                'children': [
                    {
                        'text': 'some '
                    },
                    {
                        'type': 'link',
                        'data': {'url': 'https://interaktiv.de'},
                        'children': [{'text': 'link'}]
                    }
                ]
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], 'some link')

    def test_slate_html_parser__feed__empty_element_gets_an_empty_text_child(self):
        # setup — slate's invariant: every element holds at least one text child
        html = '<p></p>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {'type': 'p', 'children': [{'text': ''}]}
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], '')

    def test_slate_html_parser__feed__empty_list_item_gets_an_empty_text_child(self):
        # setup
        html = '<ul><li></li></ul>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                'type': 'ul',
                'children': [
                    {'type': 'li', 'children': [{'text': ''}]}
                ]
            }
        ]
        self.assertEqual(result[0], expected_slate_value)

    def test_slate_html_parser__feed__ignores_a_stray_closing_tag(self):
        # setup — a provider does not guarantee balanced HTML; the stray
        # </strong> must not shift " Welt" out of the paragraph
        html = '<p>Hallo</strong> Welt</p>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {'type': 'p', 'children': [{'text': 'Hallo'}, {'text': ' Welt'}]}
        ]
        self.assertEqual(result[0], expected_slate_value)
        self.assertEqual(result[1], 'Hallo Welt')

    def test_slate_html_parser__feed__closing_a_parent_closes_the_open_child(self):
        # setup — the unclosed <strong> must not swallow the second paragraph
        html = '<p>Hallo <strong>Welt</p><p>Zwei</p>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition — two paragraphs side by side, no p inside a p
        expected_slate_value = [
            {
                'type': 'p',
                'children': [
                    {'text': 'Hallo '},
                    {'type': 'strong', 'children': [{'text': 'Welt'}]}
                ]
            },
            {'type': 'p', 'children': [{'text': 'Zwei'}]}
        ]
        self.assertEqual(result[0], expected_slate_value)

    def test_slate_html_parser__feed__closes_what_a_truncated_answer_left_open(self):
        # setup
        html = '<p>Hallo <strong>Welt'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                'type': 'p',
                'children': [
                    {'text': 'Hallo '},
                    {'type': 'strong', 'children': [{'text': 'Welt'}]}
                ]
            }
        ]
        self.assertEqual(result[0], expected_slate_value)

    def test_slate_html_parser__feed__an_alias_closing_tag_finds_its_opener(self):
        # setup — <b> opens as strong; </b> has to close it all the same
        html = '<p><b>Hallo</b> Welt</p>'

        # do it
        self.parser.feed(data=html)
        result = self.parser.get_result()

        # postcondition
        expected_slate_value = [
            {
                'type': 'p',
                'children': [
                    {'type': 'strong', 'children': [{'text': 'Hallo'}]},
                    {'text': ' Welt'}
                ]
            }
        ]
        self.assertEqual(result[0], expected_slate_value)
