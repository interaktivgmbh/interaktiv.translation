# Changelog

## Unreleased

- Added `GET @translation-fields` service to be used for type specific metadata selection
- Breaking: which fields are handled by translation is configured in metadata_selection
- Breaking: which fields go into a translation is decided per content type:
  title, description and page content always, the fields the metadata
  mapping has values for, and the fields chosen in `metadata_selection`;
  translated or taken over by the kind of field. Fields are read and written
  by their schema name (`subjects`, not `subject`), also in the metadata
  mapping and the report.
- Breaking: removed `translate_fields` and `copy_fields` from settings
- Added `excluded_fields` -> fields that are skipped
- Added `always_fields` -> fields that are always handled by translation
- Added `copied_fields` -> fields that are copied untranslated when handled
- Breaking: the settings `translate_fields` and `copy_fields` are gone; the
  upgrade step to profile version 1001 removes them. The advanced settings
  name instead the fields never translated (`excluded_fields`), always
  translated (`always_fields`) and taken over unchanged (`copied_fields`),
  for every content type, with the add-on's lists as defaults. The offered
  target languages moved back to the translation service tab.
- Added vocabulary `interaktiv.translation.ContentTypes`
  for choice of not translated content types
- Fix: target language choice vocabulary when unknown value is stored
- Fixed do not show a stored API key in the browser
- Added service @translation-connection to test connection and retrieve account information
- The translation service tab lists the offered target languages before the
  API URL and the key.
- Added encryption for API key based on cryptography.fernet
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

## 1.0.0a1 (2026-10-14)

- Initial public release.
