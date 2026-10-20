# Changelog

## Unreleased

- Machine translations of content without a workflow get the status
  `machine_without_review`: there is nothing to publish, so no review is due
  and no banner is shown.
- An existing working copy of a translation is no longer overwritten, not even
  with `overwrite`: the translation is refused with 409 until the working copy
  is checked in or discarded.

## 1.0.0a1 (2026-10-14)

- Initial public release.
