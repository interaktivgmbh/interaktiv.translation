# Changelog

## Unreleased

- Added `GET @translation-fields` service to be used for type specific metadata selection
- Breaking: which fields go into a translation is decided per content type:
  title, description and page content always, the fields the metadata
  mapping has values for, and the fields chosen in `metadata_selection`;
  translated or taken over by the kind of field. Fields are read and written
  by their schema name (`subjects`, not `subject`), also in the metadata
  mapping and the report.
- Breaking: removed `translate_fields` and `copy_fields` from settings; the
  upgrade step to profile version 1001 removes the records.
- Added `excluded_fields` -> fields that are skipped
- Added `always_fields` -> fields that are always handled by translation
- Added `copied_fields` -> fields that are copied untranslated when handled
- Added vocabulary `interaktiv.translation.ContentTypes`
  for choice of not translated content types
- Fix: target language choice vocabulary when unknown value is stored
- Fixed do not show a stored API key in the browser
- Added service @translation-connection to test connection and retrieve account information
- The offered target languages come first in the translation service tab.
- Added encryption for API key based on cryptography.fernet
- Fix: saving the classic control panel no longer removes the API key; its
  password field shows no value, so an empty field keeps the stored key.
- DeepL glossary IDs per direction, from the site's default language to each
  offered target language (`glossary_ids`); the translation sends the
  direction's glossary along, and goes on without it when DeepL refuses it.
- Added service `POST @translation-glossaries`: the glossaries of the account
  (DeepL API v2), with the settings as the form holds them.
- References (`preview_image_link`, `relatedItems`, any relation field) can go
  along when chosen for the content type: each points at the translation of its
  target, else at the target itself, and the report lists them with the links.
- Link fields (`link_fields`, by default `remoteUrl` and `event_url`) are taken
  over, never sent to the service; an internal link points at the translation
  of its target where there is one. Before, the setting only acted on fields
  that were translated. The upgrade step to profile version 1001 adds the
  defaults to a site's own list and takes them out of `copied_fields`.
- Add handling for path criterion in query searches
- Machine translations of content without a workflow get the status
  `machine_without_review`.
- Breaking: an existing working copy is never overwritten, not even with
  `overwrite`; the translation is refused with 409.
- Breaking: `GET @translate` answers `languages` (with `machine` per
  language) instead of `target_languages`; on a multilingual site only site
  languages are offered.
- The machine translation marker and the `machine_translation` expander
  include `source_language`.
- Breaking: the metadata mapping (`metadata_mapping_table`) is a JSON field
  instead of CSV text: `{"field_id": [{"de": "…", "en": "…"}, …]}`, one
  object per value with one entry per language. An empty or missing language
  keeps the source value.
  The upgrade step to profile version 1001 converts an existing CSV mapping.
- Breaking: the source language setting (`default_source_language`) is gone;
  content without a language of its own is taken to be in the site's default
  language, so DeepL no longer detects the language. The upgrade step removes
  the record.
- The offered target languages are a choice of the site languages. The
  upgrade step keeps the codes the site has and drops the others.
- Breaking: `POST @translate` refuses a target language that is not offered
  for machine translation (409), for a preview as for a save, before the
  provider is called; the Classic form refuses it the same way. Before, only
  the front ends left such languages out.
- Fix: content without a language of its own no longer takes the language of
  a folder above as the source language for the provider; like the stored
  marker, it is taken to be in the site's default language.
- Breaking: content with an open working copy is not translated by machine
  (409), with or without `save`, before the provider is called: its live
  content would be translated, not the newer one in the working copy.
  `GET @translate` names that working copy as `working_copy_url`.
- The messages of refused or failed translations are translated (de, en):
  `POST @translate` answers its `message` in the language of the request,
  the Classic form shows it in the site's language. Alongside, a `code`
  (e.g. `source_working_copy`, `not_offered`, `translation_exists`, or the
  provider's own like `quota_exceeded`) and the `values` the message names
  (e.g. `{"language": "en"}`), for a front end to react to.
- Fix: an open working copy is found even after earlier working copies of
  the same content were deleted instead of discarded. plone.app.iterate
  takes the first relation it finds, a broken one left by such a deletion
  among them, and then answers no working copy; the translation looks for
  the intact relation itself.
- Breaking: on a multilingual site, content without a language of its own
  (e.g. outside the language root folders) is not translated (409,
  `code: no_language`), as plone.app.multilingual treats it as language
  independent. Before, its translations were made next to it, linked to
  nothing, and even into the site's default language.
- `GET @translate` answers `manual_translatable` (whether Plone's own form
  may translate the content by hand) and, when `translatable` is false, a
  `refusal` with its `code` and `message` in the language of the request.
- `GET @translation-fields` tells per field whether it may be added to the
  metadata mapping (`mappable`): a field of texts (text line, text, a choice
  of texts, or a collection of them) that goes along by its type; not one
  always translated, taken over by its name, the same in all languages, a
  reference or a link.

## 1.0.0a1 (2026-10-14)

- Initial public release.
