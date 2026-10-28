import html

from html.parser import HTMLParser
from typing import Dict, List

BLOCK_TYPES = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote")
INLINE_TYPES = ("strong", "em", "u", "s", "code", "sub", "sup", "del")
PARSER_ALIASES = {"b": "strong", "i": "em"}


class SlateHTMLSerializer:
    TAGS = frozenset(BLOCK_TYPES + INLINE_TYPES)

    def serialize(self, nodes: List[Dict]) -> str:
        return "".join(self._serialize_node(node) for node in nodes)

    def _serialize_node(self, node: Dict) -> str:
        if "text" in node:
            return html.escape(node["text"], quote=False)

        node_type = node.get("type")
        children = self.serialize(node.get("children", []))

        if node_type == "link":
            url = (node.get("data") or {}).get("url", "")
            return f'<a href="{html.escape(url)}">{children}</a>'

        if node_type not in self.TAGS:
            raise ValueError(f"No HTML tag for a {node_type} node.")

        return f"<{node_type}>{children}</{node_type}>"


class SlateHTMLParser(HTMLParser):
    BLOCK_TAGS = frozenset(BLOCK_TYPES)
    INLINE_TAGS = frozenset(INLINE_TYPES) | frozenset(PARSER_ALIASES)
    TAG_MAP = {tag: tag for tag in BLOCK_TYPES + INLINE_TYPES} | PARSER_ALIASES

    BLOCK_CONTAINER_TAGS = frozenset({"ul", "ol"})

    def __init__(self):
        super().__init__()
        self.result = []
        self.stack = [self.result]
        self.text_parts = []
        self.open_tags = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag in self.BLOCK_TAGS or tag in self.INLINE_TAGS:
            slate_type = self.TAG_MAP.get(tag, "p")
            node = {"type": slate_type, "children": []}
            self.stack[-1].append(node)
            self.stack.append(node["children"])
            # The resolved type, not the raw tag, so a closing alias (`</b>`
            # for `<strong>`) still finds its opener.
            self.open_tags.append(slate_type)

        elif tag == "a":
            url = attrs_dict.get("href", "")
            node = {"type": "link", "data": {"url": url}, "children": []}
            self.stack[-1].append(node)
            self.stack.append(node["children"])
            self.open_tags.append(tag)

    def handle_endtag(self, tag):
        if not (tag in self.BLOCK_TAGS or tag in self.INLINE_TAGS or tag == "a"):
            return

        tag = self.TAG_MAP.get(tag, tag)
        if tag not in self.open_tags:
            return

        # Close the matching element, and with it whatever stayed open
        # inside it.
        while self.open_tags:
            open_tag = self.open_tags.pop()
            self._close_element()
            if open_tag == tag:
                break

    def _close_element(self):
        if len(self.stack) > 1:
            if not self.stack[-1]:
                # Slate's invariant: every element holds at least one text
                # child — an empty one, where nothing came back.
                self.stack[-1].append({"text": ""})
            self.stack.pop()

    def _in_block_container(self):
        return not self.open_tags or self.open_tags[-1] in self.BLOCK_CONTAINER_TAGS

    def handle_data(self, data):
        text = data
        if not text:
            return

        if not text.strip() and self._in_block_container():
            return

        self.text_parts.append(text)

        text_node = {"text": text}
        self.stack[-1].append(text_node)

    def get_result(self):
        # Elements a truncated answer left open close here, the same way a
        # matching end tag would have closed them.
        while self.open_tags:
            self.open_tags.pop()
            self._close_element()

        plaintext = "".join(self.text_parts)
        return self.result, plaintext
