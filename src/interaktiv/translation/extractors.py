import copy
import html
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from plone.app.textfield.value import RichTextValue

from interaktiv.translation.blocks import BLOCK_HANDLERS, BlockHandler, DefaultBlockHandler, Pair


class Share(TypedDict):
    # used to keep track where values were translated -> needed for rebuilding
    block_id: str
    handler: Optional[BlockHandler]
    pairs: List[Pair]


class FieldExtractor:
    # fields that belong to translatable fields but are not translated themselves
    COMPANION_FIELDS: Tuple[str, ...] = ()

    def handles(self, value: Any) -> bool:
        raise NotImplementedError

    def shares(self, value: Any) -> Optional[List[Share]]:
        return None

    def texts(self, value: Any, shares: Optional[List[Share]] = None) -> List[str]:
        raise NotImplementedError

    def rebuild(self, value: Any, translated: List[str], shares: Optional[List[Share]] = None) -> Any:
        raise NotImplementedError


class TextExtractor(FieldExtractor):
    def handles(self, value: Any) -> bool:
        return isinstance(value, str)

    def texts(self, value: str, shares: Optional[List[Share]] = None) -> List[str]:
        return [html.escape(value, quote=False)]

    def rebuild(self, value: str, translated: List[str], shares: Optional[List[Share]] = None) -> str:
        return html.unescape(translated[0])


class RichTextExtractor(FieldExtractor):
    def handles(self, value: Any) -> bool:
        return hasattr(value, "raw") and hasattr(value, "mimeType")

    def texts(self, value: Any, shares: Optional[List[Share]] = None) -> List[str]:
        return [value.raw or ""]

    def rebuild(self, value: Any, translated: List[str], shares: Optional[List[Share]] = None) -> Any:
        return RichTextValue(translated[0], mimeType=value.mimeType, outputMimeType=value.outputMimeType)


class BlocksExtractor(FieldExtractor):
    COMPANION_FIELDS = ("blocks_layout",)

    def __init__(self, text_keys: Optional[List[str]] = None) -> None:
        self.default_handler = DefaultBlockHandler(text_keys)

    def handles(self, value: Any) -> bool:
        return isinstance(value, dict)

    def _get_block_handler(self, block: Dict) -> BlockHandler:
        registered = BLOCK_HANDLERS.get(block.get("@type"))
        if registered is not None:
            return registered

        return self.default_handler

    def shares(self, value: Dict) -> List[Share]:
        shares = []

        for block_id, block in value.items():
            if isinstance(block, dict):
                # is a block
                handler = self._get_block_handler(block)
                pairs = handler.texts(block)
            else:
                handler = None
                wrapped_value = {block_id: block}
                pairs = self.default_handler.texts(wrapped_value)

            share = {
                "block_id": block_id,
                "handler": handler,
                "pairs": pairs,
            }
            shares.append(share)

        return shares

    def texts(self, value: Dict, shares: Optional[List[Share]] = None) -> List[str]:
        if shares is None:
            shares = self.shares(value)

        return [text for _share in shares for _path, text in _share["pairs"]]

    def rebuild(self, value: Dict, translated: List[str], shares: Optional[List[Share]] = None) -> Dict:
        if shares is None:
            shares = self.shares(value)

        blocks = {}
        consumed = 0
        for share in shares:
            block_id = share["block_id"]
            handler = share["handler"]
            pairs_count = len(share["pairs"])

            translated_share = translated[consumed : consumed + pairs_count]
            consumed += pairs_count

            if not translated_share:
                blocks[block_id] = copy.deepcopy(value[block_id])
            elif handler is None:
                wrapped_value = {block_id: value[block_id]}
                wrapped_rebuild = self.default_handler.rebuild(wrapped_value, translated_share)
                blocks[block_id] = wrapped_rebuild[block_id]
            else:
                blocks[block_id] = handler.rebuild(value[block_id], translated_share)

        return blocks


class ExtractorRegistry:
    def __init__(self, extractors: Optional[List[FieldExtractor]] = None) -> None:
        self._extractors = list(extractors or [])

    def register(self, extractor: FieldExtractor) -> None:
        self._extractors.insert(0, extractor)

    def for_value(self, value: Any) -> Optional[FieldExtractor]:
        for extractor in self._extractors:
            if extractor.handles(value):
                return extractor

        return None


def default_extractors(block_text_keys: Optional[List[str]] = None) -> ExtractorRegistry:
    return ExtractorRegistry([BlocksExtractor(block_text_keys), RichTextExtractor(), TextExtractor()])
