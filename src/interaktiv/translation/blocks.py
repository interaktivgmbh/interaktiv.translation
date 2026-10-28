import copy
import html
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Tuple, Union

from interaktiv.translation import logger
from interaktiv.translation.helpers.slate import SlateHTMLParser, SlateHTMLSerializer
from interaktiv.translation.settings import settings

# path to the text in json branch: dict keys and list indices.
Path = Tuple[Union[str, int], ...]

# path to the text in json branch, and the text itself.
Pair = Tuple[Path, str]


class BlockHandler:
    def texts(self, block: Dict) -> List[Pair]:
        raise NotImplementedError

    def rebuild(self, block: Dict, translated: List[str]) -> Dict:
        raise NotImplementedError


TextKind = Literal["plain", "slate", "html"]
PLAIN: TextKind = "plain"
SLATE: TextKind = "slate"
HTML: TextKind = "html"


class Finding(NamedTuple):
    path: Path
    text: str
    kind: TextKind


RICHTEXT_DATA_KEY = "data"
SLATE_VALUE_KEY = "value"
SLATE_PLAINTEXT_KEY = "plaintext"


def is_slate_tree(nodes: Any) -> bool:
    if not isinstance(nodes, list) or not nodes:
        return False

    return all(isinstance(node, dict) and "type" in node and isinstance(node.get("children"), list) for node in nodes)


def has_prose(nodes: Any) -> bool:
    if isinstance(nodes, dict):
        text = nodes.get("text")
        if isinstance(text, str) and text.strip():
            return True

        return has_prose(nodes.get("children"))
    if isinstance(nodes, list):
        return any(has_prose(node) for node in nodes)

    return False


def slate_html(nodes: Any) -> Optional[str]:
    if not is_slate_tree(nodes) or not has_prose(nodes):
        return None

    try:
        return SlateHTMLSerializer().serialize(nodes)
    except Exception:  # noqa: BLE001
        return None


class DefaultBlockHandler(BlockHandler):
    SKIPPED_KEYS = ("styles",)

    def __init__(self, text_keys: Optional[List[str]] = None) -> None:
        self._own_text_keys = tuple(text_keys) if text_keys else None

    @property
    def text_keys(self) -> Tuple[str, ...]:
        if self._own_text_keys:
            return self._own_text_keys

        return tuple(settings().block_text_keys)

    def _walk(self, node: Any, path: Path = ()) -> List[Finding]:
        # collect all text findings
        found: List[Finding] = []

        if isinstance(node, dict):
            value_html = slate_html(node.get(SLATE_VALUE_KEY))
            for key, value in node.items():
                if key in self.SKIPPED_KEYS:
                    continue
                here = path + (key,)
                if key == SLATE_VALUE_KEY and value_html is not None:
                    found.append(Finding(here, value_html, SLATE))
                elif key == SLATE_PLAINTEXT_KEY and value_html is not None:
                    continue
                elif isinstance(value, str):
                    if key in self.text_keys and value.strip():
                        found.append(Finding(here, value, PLAIN))
                elif self._is_richtext(key, value):
                    if value[RICHTEXT_DATA_KEY].strip():
                        found.append(Finding(here + (RICHTEXT_DATA_KEY,), value[RICHTEXT_DATA_KEY], HTML))
                else:
                    found.extend(self._walk(value, here))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                found.extend(self._walk(item, path + (index,)))

        return found

    def _is_richtext(self, key: str, value: Any) -> bool:
        return key in self.text_keys and isinstance(value, dict) and isinstance(value.get(RICHTEXT_DATA_KEY), str)

    def texts(self, block: Dict) -> List[Pair]:
        # HTML is escaped already, by the serializer or by the widget.
        return [
            (path, html.escape(text, quote=False) if kind == PLAIN else text) for path, text, kind in self._walk(block)
        ]

    def rebuild(self, block: Dict, translated: List[str]) -> Dict:
        result = copy.deepcopy(block)
        for (path, _text, kind), answer in zip(self._walk(block), translated):
            node = result
            for step in path[:-1]:
                node = node[step]
            if kind == SLATE:
                self._write_tree(node, answer)
            elif kind == HTML:
                node[path[-1]] = answer
            else:
                node[path[-1]] = html.unescape(answer)

        return result

    @staticmethod
    def _write_tree(node: Dict, answer: str) -> None:
        parser = SlateHTMLParser()
        parser.feed(answer)
        value, plaintext = parser.get_result()
        if not value:
            return

        node[SLATE_VALUE_KEY] = value
        if SLATE_PLAINTEXT_KEY in node:
            node[SLATE_PLAINTEXT_KEY] = plaintext


class BlockHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, BlockHandler] = {}

    def register(self, type_name: str, handler: BlockHandler) -> None:
        if not type_name:
            raise ValueError("A block handler needs the block type it is for.")
        if type_name in self._handlers:
            logger.info("Replacing the block handler for %s blocks.", type_name)
        self._handlers[type_name] = handler

    def get(self, type_name: Optional[str]) -> Optional[BlockHandler]:
        if not type_name:
            return None

        return self._handlers.get(type_name)

    def names(self) -> List[str]:
        return sorted(self._handlers)


BLOCK_HANDLERS = BlockHandlerRegistry()
