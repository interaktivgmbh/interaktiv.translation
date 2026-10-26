# Changelog

## Unreleased

- Added `GET @translation-fields` service to be used for type specific metadata selection
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
