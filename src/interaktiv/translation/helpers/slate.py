import copy
import html

from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

BLOCK_TYPES = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote")
INLINE_TYPES = ("strong", "em", "u", "s", "code", "sub", "sup", "del")
PARSER_ALIASES = {"b": "strong", "i": "em"}

# What HTML has no place for — the style of a paragraph, the target of a link,
# the style of a word — stays here: the node is numbered, the number travels
# with the text, and the parser hands the properties back by it.
NODE_ATTRIBUTE = "data-slate-node"
# carries the number of a text node, which has no tag of its own
LEAF_TAG = "span"

# what the tag itself says
ELEMENT_KEYS = ("type", "children")
LINK_DATA_KEY = "data"
LINK_URL_KEY = "url"

# {number: properties}, of one serialized tree
NodeProperties = Dict[str, Dict[str, Any]]


def kept_properties(node: Dict) -> Dict[str, Any]:
    """The properties of a node its HTML does not say."""
    if "text" in node:
        return {key: value for key, value in node.items() if key != "text"}

    properties = {key: value for key, value in node.items() if key not in ELEMENT_KEYS}
    if node.get("type") == "link" and isinstance(properties.get(LINK_DATA_KEY), dict):
        # the url is the href
        data = {key: value for key, value in properties[LINK_DATA_KEY].items() if key != LINK_URL_KEY}
        if data:
            properties[LINK_DATA_KEY] = data
        else:
            del properties[LINK_DATA_KEY]

    return properties


class SlateHTMLSerializer:
    TAGS = frozenset(BLOCK_TYPES + INLINE_TYPES)

    def __init__(self) -> None:
        # of the tree serialized last
        self.node_properties: NodeProperties = {}

    def serialize(self, nodes: List[Dict]) -> str:
        self.node_properties = {}

        return self._serialize_nodes(nodes)

    def _serialize_nodes(self, nodes: List[Dict]) -> str:
        return "".join(self._serialize_node(node) for node in nodes)

    def _node_attribute(self, node: Dict) -> str:
        properties = kept_properties(node)
        if not properties:
            return ""

        number = str(len(self.node_properties) + 1)
        self.node_properties[number] = properties

        return f' {NODE_ATTRIBUTE}="{number}"'

    def _serialize_node(self, node: Dict) -> str:
        if "text" in node:
            text = html.escape(node["text"], quote=False)
            if not text:
                return text
            attribute = self._node_attribute(node)

            return f"<{LEAF_TAG}{attribute}>{text}</{LEAF_TAG}>" if attribute else text

        node_type = node.get("type")
        if node_type != "link" and node_type not in self.TAGS:
            raise ValueError(f"No HTML tag for a {node_type} node.")

        # numbered before its children, as the parser meets them
        attribute = self._node_attribute(node)
        children = self._serialize_nodes(node.get("children", []))

        if node_type == "link":
            url = (node.get(LINK_DATA_KEY) or {}).get(LINK_URL_KEY, "")
            return f'<a href="{html.escape(url)}"{attribute}>{children}</a>'

        return f"<{node_type}{attribute}>{children}</{node_type}>"


class SlateHTMLParser(HTMLParser):
    BLOCK_TAGS = frozenset(BLOCK_TYPES)
    INLINE_TAGS = frozenset(INLINE_TYPES) | frozenset(PARSER_ALIASES)
    TAG_MAP = {tag: tag for tag in BLOCK_TYPES + INLINE_TYPES} | PARSER_ALIASES

    BLOCK_CONTAINER_TAGS = frozenset({"ul", "ol"})

    def __init__(self, node_properties: Optional[NodeProperties] = None):
        super().__init__()
        self.result = []
        self.stack = [self.result]
        self.text_parts = []
        self.open_tags = []
        # what the serializer kept of the tree this answer was made from
        self.node_properties = node_properties or {}
        # the open leaf tags, each with the number of elements that were open
        # around it and the properties of the text inside; None for a tag of
        # that name that is no leaf tag but an element
        self.open_leaves = []

    def _properties(self, attrs_dict: Dict) -> Dict[str, Any]:
        # a number the tree did not have names nothing
        return copy.deepcopy(self.node_properties.get(attrs_dict.get(NODE_ATTRIBUTE) or "", {}))

    def _with_properties(self, node: Dict, attrs_dict: Dict) -> Dict:
        for key, value in self._properties(attrs_dict).items():
            if isinstance(value, dict) and isinstance(node.get(key), dict):
                # the data of a link beside its url
                node[key] = {**value, **node[key]}
            else:
                node.setdefault(key, value)

        return node

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == LEAF_TAG:
            # only with a number, where the tag is an element of its own too
            is_leaf = NODE_ATTRIBUTE in attrs_dict or tag not in self.TAG_MAP
            self.open_leaves.append((len(self.open_tags), self._properties(attrs_dict) if is_leaf else None))
            if is_leaf:
                return

        if tag in self.BLOCK_TAGS or tag in self.INLINE_TAGS:
            slate_type = self.TAG_MAP.get(tag, "p")
            node = self._with_properties({"type": slate_type, "children": []}, attrs_dict)
            self.stack[-1].append(node)
            self.stack.append(node["children"])
            # The resolved type, not the raw tag, so a closing alias (`</b>`
            # for `<strong>`) still finds its opener.
            self.open_tags.append(slate_type)

        elif tag == "a":
            url = attrs_dict.get("href", "")
            node = self._with_properties({"type": "link", "data": {"url": url}, "children": []}, attrs_dict)
            self.stack[-1].append(node)
            self.stack.append(node["children"])
            self.open_tags.append(tag)

    def handle_endtag(self, tag):
        if tag == LEAF_TAG and self.open_leaves:
            _depth, properties = self.open_leaves.pop()
            if properties is not None:
                return

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

        # a leaf tag ends with the element it was opened in, closed or not
        while self.open_leaves and self.open_leaves[-1][0] > len(self.open_tags):
            self.open_leaves.pop()

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
        text_node.update(self._leaf_properties())
        self.stack[-1].append(text_node)

    def _leaf_properties(self) -> Dict[str, Any]:
        properties: Dict[str, Any] = {}
        for _depth, leaf_properties in self.open_leaves:
            properties.update(copy.deepcopy(leaf_properties or {}))
        properties.pop("text", None)

        return properties

    def get_result(self):
        # Elements a truncated answer left open close here, the same way a
        # matching end tag would have closed them.
        while self.open_tags:
            self.open_tags.pop()
            self._close_element()

        plaintext = "".join(self.text_parts)
        return self.result, plaintext
