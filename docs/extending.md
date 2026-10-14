# Extending interaktiv.translation

Three seams have a registry in front of them; register from your add-on's
`__init__`, because registration happens on import.

| Seam | Base class | Registry | What it decides |
| --- | --- | --- | --- |
| The service | `TranslationProvider` | `PROVIDERS` | Who translates, and how it is spoken to |
| The field shapes | `FieldExtractor` | `ExtractorRegistry` | Which parts of a value are text |
| The block types | `BlockHandler` | `BLOCK_HANDLERS` | Which parts of one block are text |

Much needs no code at all. The control panel names the translated fields,
the keys of a block that hold text or links, the link fields of your content
types, and the metadata mapping tables.

## Another translation service

```python
from interaktiv.translation.providers.base import PROVIDERS, TranslationProvider
from interaktiv.translation.settings import settings


class AcmeProvider(TranslationProvider):
    name = "acme"
    title = "Acme Translate"

    def configured(self):
        return bool(settings().api_key)

    def translate(self, texts, target_language, source_language=None):
        ...  # one answer per input, in the same order

    def languages(self):
        return [{"code": "EN", "title": "English"}]


PROVIDERS.register(AcmeProvider)
```

The provider then appears in the control panel's list, because the
vocabulary reads the same registry. `translate` must answer one string per
input string, in order: everything above it counts on that to put the
answers back where they came from. Raise `TranslationError(message, status)`
for a failure the editor should see.

The translator calls `translate_texts_by_key({key: [texts]}, ...)`. The base
class calls `translate` once per key; a service with request limits, like
DeepL, overrides it to bundle all texts of a page and split them into chunks
it accepts.

## Another field shape

A `FieldExtractor` answers three questions about a value: is this mine, what
text is in it, and how do I put translations back. That contract keeps a
page's structure out of the translation.

```python
from interaktiv.translation.extractors import FieldExtractor, default_extractors
from interaktiv.translation.translator import ContentTranslator


class AcmeTableExtractor(FieldExtractor):
    def handles(self, value):
        return isinstance(value, AcmeTable)

    def texts(self, value, shares=None):
        return [cell.text for row in value.rows for cell in row]

    def rebuild(self, value, translated, shares=None):
        ...  # a new value, with the answers in the cells


extractors = default_extractors()
extractors.register(AcmeTableExtractor())      # placed in front, so it wins
ContentTranslator(extractors=extractors)
```

`shares` is optional bookkeeping: an extractor that has to split a value
into parts can compute that split once in `shares(value)` and gets it back in
`texts` and `rebuild`. A simple extractor ignores it. Set `COMPANION_FIELDS`
for fields that belong to the value without holding text, the way
`blocks_layout` belongs to `blocks`; they are copied along unchanged.

## Another block type

Volto's `blocks` field is one value, so `BlocksExtractor` claims it whole;
block types plug in *inside* it, by `@type`. For most custom blocks the stock
walk is right and only the key names are their own. Name them in the control
panel, or register a handler with its own keys:

```python
from interaktiv.translation.blocks import BLOCK_HANDLERS, DefaultBlockHandler

BLOCK_HANDLERS.register("tabBlock", DefaultBlockHandler(["tabTitle"]))
```

A block that keeps its text in a shape of its own implements the two methods
itself:

```python
from interaktiv.translation.blocks import BLOCK_HANDLERS, BlockHandler


class AcmeChartHandler(BlockHandler):
    def texts(self, block):
        return [(("caption",), block["caption"])]

    def rebuild(self, block, translated):
        return dict(block, caption=translated[0])


BLOCK_HANDLERS.register("acmeChart", AcmeChartHandler())
```

`texts` answers `(path, text)` pairs in a stable order, and `rebuild` gets
exactly one answer per pair. The pairs need not mirror the block's shape —
the stock Slate handler sends a whole tree as one HTML string. The last
registration for a type wins, so replacing the stock Slate handler is the
same call. A block type nobody registered gets the `DefaultBlockHandler` with
the control panel's keys.

## Where translations are stored

There is no registry for this. `TranslationStorage` decides between the
object itself, a new language sibling and a working copy, from what the site
has installed (`plone.app.multilingual`, `plone.app.iterate`). A project that
keeps translations somewhere else subclasses it — `store()` dispatches to
`_store_in_place` and `_store_as_translation`, so only what differs needs
overriding — and registers its own `@translate` service for a more specific
browser layer that uses the subclass.

## The user interface

The Volto interface lives in the separate frontend add-on `volto-translation`
and talks to the REST endpoints only (`@translate`, the
`machine_translation` expander, `@workingcopy`). A different interface can
use the same endpoints; nothing in the backend depends on the frontend.
