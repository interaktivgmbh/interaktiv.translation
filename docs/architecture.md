# Architecture

What each part is for, and why it behaves the way it does. The code keeps its
comments short; the reasons live here.

## The flow

An editor asks for a translation: in Volto through `POST @translate`
(`services/translate/post.py`), in Classic through the form in
`views/translate.py`. Both do the same steps:

1. `TranslationStorage.refusal()` checks whether the result could be stored
   at all. A refusal comes **before** the provider is called, so DeepL is
   never paid for a translation that would be thrown away.
2. `ContentTranslator.translate()` works out **what text** the page holds,
   has a `TranslationProvider` **translate** it, and builds the translated
   field values. It writes nothing.
3. `TranslationStorage.store()` decides **where the result goes** and marks
   it as a machine translation.
4. The service answers with a **report**: where the result went, which links
   were pointed at translated pages and which metadata values were mapped.

Nothing in the middle knows which front end asked, so the two cannot drift
into translating different things.

## `providers/` — who translates

`TranslationProvider` is the contract: `translate`, `languages`,
`configured`. `configured` exists so the site can ask *before* offering the
action; an action that cannot work is not shown. `translate` must answer
**one string per input string, in order** — everything above it relies on
that to put the answers back where they came from.

`translate_texts_by_key()` takes `{key: [texts]}` and answers the same shape.
The base class calls `translate` once per key. A provider that can do better
overrides it; the translator only ever calls this method.

`ProviderRegistry` (`PROVIDERS`) maps a name to a class. The control panel's
list of services is that registry, so registering one is all an add-on does.

### `DeepLProvider`

* **Two hosts.** DeepL runs the free plan on `api-free.deepl.com` and the
  paid one on `api.deepl.com`; a key for one is refused by the other. A free
  key ends in `:fx`, which is enough to pick the host. The `api_url` setting
  overrides it, for a proxy.
* **One run per page.** `translate_texts_by_key` flattens the texts of all
  fields into one list and cuts the answers back per field, so a page costs
  as few requests as its amount of text demands, not one per field.
* **Chunks.** DeepL takes at most 50 `text` parameters and 128 KiB per
  request. `_chunked()` fills requests up to `MAX_TEXTS_PER_REQUEST` (50) and
  `MAX_REQUEST_BYTES` (100 000, measured in UTF-8 bytes, with room for the
  other payload fields). A single text above the budget is refused with 413:
  splitting it would cut through markup or sentences.
* **Rate limits.** A 429 is retried up to `RETRY_ATTEMPTS` times with a
  growing delay plus jitter. A 456 (quota used up) is not retried — knocking
  again does not refill a quota.
* **Empty texts are never sent.** They keep their place in the answer, so the
  caller still gets one answer per input.
* **`tag_handling: html`.** Volto blocks and Classic rich text carry markup
  that has to survive the round trip.
* **Language codes.** Plone says `de`, `pt-br`; DeepL wants `DE`, `PT-BR` and
  refuses a regional code as a *source*, so a source is cut back to its first
  part. A source equal to the target carries no information and is left out;
  DeepL then detects the language itself.
* **Its failures are answers.** A refused key is 403, a used-up quota 429, an
  unreachable DeepL a message rather than a traceback. `languages()` answers
  an empty list when DeepL is down: a control panel that cannot be opened is
  worse than one that offers no languages.
* **Constructing it.** `api_key=None` means "take it from the site", `""`
  means "there is none". That makes the class usable in a test, a script or a
  migration with no Plone around.

### `MockProvider`

Writes the text in capitals and answers immediately, so the whole flow —
menu, report, working copies, the Slate round trip — can be tried on a site
without a DeepL key. Tags and entities pass through untouched: the answer has
to parse back into a block tree, or the mock would not test the round trip.

## `settings.py` — reading the registry

One reader over the records of `ITranslationSettings`, so nothing else needs
to know a dotted key. With no site around every setting falls back to its
default — an unconfigured provider rather than a broken one.
`get_metadata_mapping(source, target)` hands out the metadata mapping for one
direction (see `helpers/metadata.py`).

The control panel is plone.restapi's generic configlet for the same schema;
Volto renders it from the schema, Classic through z3c.form. Fields, tabs and
validation messages are therefore the same in both.

## `translator.py` — one translation run

`ContentTranslator.translate()` runs in phases:

1. **Source language.** The request's `source_language`, else the
   `language` field of the content, else the site default. The content knows
   its language best; the default is a guess that cannot cover a
   multilingual tree. `None` is allowed — the provider then detects the
   language per text.
2. **Collect.** For every field named in the control panel the matching
   extractor (`extractors.py`) reads the texts. A field that cannot be read
   is logged and skipped — one broken field must not lose the rest of the
   page.
3. **Translate.** All texts of all fields go to the provider in one
   `translate_texts_by_key()` call. A `TranslationError` is not swallowed:
   that is the service itself failing, and the editor has to hear about it.
4. **Rebuild.** Each extractor puts its answers back. Fields that belong to a
   translated value without holding text — `blocks_layout` beside `blocks` —
   travel along unchanged, but only once the value itself came back.
5. **Links.** `helpers/links.py` points internal links at the translated
   pages. A failure here costs the rewritten links, never the paid
   translation.
6. **Metadata.** Fields named in `copy_fields` are carried over as they
   are — plain values (text, numbers, dates, lists of them) and files and
   images; a reference would still belong to the source. A file or image
   becomes a new object with the same data, never the source's own: two
   contents sharing one persistent object would both change when one is
   edited. By default `copy_fields` names `image` and `file`, so an image or
   a file gets its content and a page its lead image. Fields that have a
   table in the metadata mapping are carried over instead of translated:
   each value is looked up for the direction of the run, and an unknown
   value stays as it is. The mapping runs last, so it wins over both a
   translation and a copy of the same field. A field that is empty in the
   source is skipped by both: the translation keeps what it has.

`link_report` and `metadata_report` record what steps 5 and 6 did, in the
same shape: `before`, `after`, and `after: null` for a value that stayed as
it was. `copied_report` only names the fields that were carried over.

## `extractors.py` — what counts as text

A `FieldExtractor` answers three questions about a value: *is this mine*,
*what text is in it*, *how do I put translations back*. One class per shape
of value, so an add-on with its own widget registers one more instead of
growing a chain of `isinstance` checks.

* `TextExtractor` — a plain string.
* `RichTextExtractor` — plone.app.textfield's `RichTextValue`. Only the raw
  text travels; the mime types come back unchanged.
* `BlocksExtractor` — Volto's `blocks` mapping. It reads no block itself: it
  looks each block's `@type` up in `BLOCK_HANDLERS` and hands the block to the
  handler found there. `shares()` records which handler gave which texts;
  `texts()` and `rebuild()` both run over that record, so each handler gets
  exactly its own slice of the answers back, even when it sends fewer texts
  than its tree has leaves.

`shares()` is computed once per run and handed to both `texts()` and
`rebuild()`. `ExtractorRegistry` picks the first extractor that claims a
value; `register()` puts a new one in front, so an add-on can shadow a stock
one. `default_extractors()` puts blocks before text on purpose: a `blocks`
value is a mapping, and the order says which reading is meant.

## `blocks.py` and `helpers/slate.py` — one block at a time

`BlockHandler` is the contract: `texts` answers `(path, text)` pairs relative
to the block, `rebuild` a new block with the answers in it. `BLOCK_HANDLERS`
maps a block's `@type` to a handler the way `PROVIDERS` maps a name to a
service; the last registration for a type wins.

`DefaultBlockHandler` walks the block and picks out **only the keys that hold
text**, as named in the control panel. A block's layout, its `href`, its
image path and its listing query stay exactly as they were — translating one
of those breaks the page. `styles` is never read: its values are English
words that look like text.

Slate splits a formatted sentence into separate text leaves. Read leaf by
leaf, the provider sees fragments — "die Anlage" without its verb, a bold word
on its own — and answers accordingly. So wherever the walk meets a slate tree
under `value` (`is_slate_tree`), it serialises the whole tree to one HTML
string (`helpers/slate.py`) that travels as one text in which the provider may
move tags; the answer is parsed back into a tree, and the `plaintext` beside
it is rebuilt from the same answer instead of being sent a second time. This
happens at any depth: the `value` of a text block, of a project's text
variant or a quote, the `text-0` of a tab, a block inside a grid column or an
accordion panel. The walk falls back to the leaves when the tree holds no
text (Volto's empty paragraph is never sent), when it cannot be serialised,
or when its data is broken; `texts` and `rebuild` decide the same way, so an
answer cannot land in the wrong place. The parser ignores stray closing tags,
closes what an answer left open, and gives every element at least one text
child, so a sloppy answer cannot shift the tree.

A text key may also hold what Volto's rich text widget writes, a dict whose
`data` is HTML (the description of a project's icon block). That HTML travels
as it is, like a `RichTextValue` does, and the answer is written back into
`data` alone; `content-type` and whatever else the dict carries stay. The
check is anchored on the text key, so a `data` dict under another key — an
accordion keeps its panels there — is walked like any other.

Known limit: `styleName`, `style-*` marks and link attributes such as
`target` do not survive the round trip; only the link URL does.

## `helpers/links.py` — internal links

After the rebuild, links inside blocks (keys named in the control panel,
by default the ones Plone's link integrity watches) and link fields on the
object itself are checked. A link to a page of this site that has a
translation in the target language is pointed at that translation, as a
`resolveuid` link; anything else stays as it was and is reported with
`after: null`. External links, `mailto:` and anchors are left alone.

## `helpers/metadata.py` — the mapping table

The control panel stores the mapping exactly as it is delivered: a line
`[field_id]` starts a table, its header names language codes, each further
line is one term across those languages. `parse_metadata_mapping()` reads one
direction out of it on demand; there is no second storage format.
`validate_metadata_mapping_table()` is the schema constraint: it collects
every problem with its line number (no section, unknown language code, a
language twice, wrong number of cells) so a broken paste can be fixed in one
go.

## `storage.py` — where a translation goes

`refusal()` is the one place that decides whether a save is refused: for a
content type excluded in the control panel (none by default), on a
working copy, into the content's own language, over an existing translation
or working copy without `overwrite`, or when a fresh checkout is not allowed.
The last case names its reason — someone else's lock or a missing checkout
permission — so the editor knows what to do. The service calls it before the provider;
`store()` calls it again, so the Classic form and any other caller get the
same protection.

`store()` has three paths:

* **Single-language site:** the object itself. The write also sets
  `language`, because no second object is made and that field is what the
  catalogue and the front end read.
* **Multilingual site, no translation yet:** `plone.app.multilingual` creates
  the language sibling.
* **Multilingual site, translation exists:** with `plone.app.iterate`
  installed the translation is checked out and the result written into the
  working copy, so the live translation stays untouched until an editor
  checks in. Before the checkout the baseline is versioned with a note naming
  the machine translation. Without iterate the translation is overwritten,
  and only with `overwrite`.

Whether the site is multilingual or uses working copies is read from the
installed profile versions, not from a setting — a setting that disagrees
with the site is a way to lose content.

Every write sets the machine translation marker (an annotation with provider,
target language and time), puts a change note on the request and ends in
`notify(ObjectModifiedEvent(...))`. The event cuts a version, so the way back
is the version history; link integrity and cache purging hang off it too. A
request flag (`STORING_KEY`) tells the edit subscriber that this write is the
machine's own and not an editor's edit.

## The marker and its review

`translation_status()` derives one status from the marker, and every display
asks this function:

| status | meaning |
| --- | --- |
| `manual` | no marker: written by hand, or the source |
| `machine_unreviewed` | machine translated, not looked at yet |
| `machine_edited` | an editor has changed it since |
| `machine_reviewed` | reviewed: checked in or published |
| `machine_without_review` | machine translated, content without a workflow: nothing to publish, so no review is due |

Whether content has a workflow is asked when the status is read, not stored:
a type that gets a workflow later asks for review again. A checkin still
records a review on content without a workflow.

The subscribers in `subscribers/events.py` move it along:

* an edit by a person sets `edited_by`;
* a **checkin** of a working copy counts as review: it sets `reviewed_by`
  and labels the version with a note;
* **publishing** counts as review as well; the note is appended to the
  workflow comment, so it appears in the history beside the transition;
* a **checkout** removes the permission *Manage Translations* on the working
  copy, and the checkin restores it, so a working copy cannot itself be
  translated. Plone's own translation menus and views guard with the same
  permission, so the lock holds in Classic as well.

The notes live in versions and workflow comments. A content type without
versioning shows only the publishing note in its history, one without a
workflow none; the status itself does not depend on versioning.

## `views/` and `services/` — the front doors

* **`POST @translate`** needs *Manage Translations*. It serves a whole page
  or a single text (`text`); without `save` it writes nothing, which is what
  a preview wants. On a working copy it answers 400, for a refusal 409. It
  stands `plone.protect` down for the request that saves, and only for that
  one: a REST client carries no form token, and without the stand-down the
  store runs, the service answers `saved`, and the transaction is rolled
  back — after the provider was paid. plone.restapi does the same in its own
  writing services.
* **`GET @translate`** needs *Modify portal content*. It reports whether the
  site is configured, whether this content may be translated by machine
  (`translatable`), the offered target languages (without the content's own)
  and, per language, the translation, its status and an open working copy.
* **The `machine_translation` expander** (`@machine-translation`) adds the
  marker and the status to a content response for editors. Volto's banner
  reads it.
* **`PATCH @workingcopy`** replaces plone.restapi's checkin. The stock one
  checks in with an empty message and fails with a 500 when there is nothing
  to check in; this one labels the version and answers 400.
* **The Classic form** (`@@translate-content`) asks for the language and the
  overwrite flag only; everything else is configuration.
  `TranslationAvailableView` is a *view* rather than an attribute because the
  edit-bar action's condition is restricted Python, which may call a view but
  not read an attribute off one.

## The user interface

Classic gets a GenericSetup `object_button` in the edit bar. Volto gets its
interface from the frontend add-on `volto-translation`: a toolbar menu, the
translation dialog with the report, the banner and the status columns in
Manage Translations. It only reads the endpoints above and decides nothing
of its own.

## `testing.py`

The layers build on `plone.app.testing` alone: `PloneSandboxLayer` with the
add-on's ZCML and profile, a multilingual layer that adds German *before*
`plone.app.multilingual` builds the language folders, and a layer with
`plone.app.iterate`. `TestCase` holds the few helpers the tests use.

`RelativeSession` is a `requests.Session` with a base URL. plone.restapi
ships one, but importing it pulls in a Robot Framework stack this add-on has
no use for. A few lines are cheaper than that dependency.
