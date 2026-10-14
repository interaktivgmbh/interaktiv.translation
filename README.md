# interaktiv.translation

Machine translation for Plone 6 content with DeepL. Editors translate a page
from the toolbar; the add-on sends only the text to the translation service,
keeps the page structure intact and stores the result where the site keeps
its languages. Machine translations stay marked until an editor has reviewed
them.

The Volto user interface comes with the frontend add-on
[`volto-translation`](https://github.com/interaktivgmbh/volto-translation).

## Features

- Translates the configured fields. Inside Volto blocks only text is sent;
  Slate rich text travels as one HTML string, so sentences stay intact.
- Stores a translation as the language sibling of the page
  (`plone.app.multilingual`) or, on a single-language site, in the page itself.
- Never overwrites a live translation unasked: with `plone.app.iterate` the
  result goes into a working copy for review, otherwise overwriting has to be
  requested explicitly.
- Marks machine translations and tracks their review (unreviewed, edited,
  reviewed). A banner and the Manage Translations view show the state;
  checking in or publishing counts as review and is noted in the history.
- Points internal links at the translated target pages where they exist.
- Carries metadata such as keywords over without translating them,
  optionally through a mapping table.
- Reports after saving which links and metadata values were changed and
  which were not.
- Sends all texts of a page in as few requests as possible and retries when
  DeepL rate-limits.

## Requirements

Plone 6.0 or 6.1, Python 3.10 or later and `plone.restapi`. Both
`plone.app.multilingual` and `plone.app.iterate` ship with Plone and are
used when they are activated on the site: multilingual for language
siblings, iterate for working copies. Without multilingual a translation is
stored in the page itself; without iterate an existing translation is
replaced only on request.

## Installation

The package is not published on PyPI yet. Install it from GitHub:

```
pip install git+https://github.com/interaktivgmbh/interaktiv.translation.git
```

or, in a project managed with [mxdev](https://github.com/mxstack/mxdev), add
it to `mx.ini`:

```ini
[interaktiv.translation]
url = https://github.com/interaktivgmbh/interaktiv.translation.git
branch = main
```

The repository holds no compiled translation files. Set the environment
variable `zope_i18n_compile_mo_files=true` for the Plone instance, so the
user interface translations are compiled on startup.

For Volto, also install the frontend add-on
[`volto-translation`](https://github.com/interaktivgmbh/volto-translation).

Then activate the add-on in **Site Setup → Add-ons** and enter a
DeepL API key in **Site Setup → Translation**. Free keys (ending in `:fx`) use
DeepL's free endpoint automatically. To try the add-on without a key, choose
the provider *Mock*: it writes the text in capitals instead of translating it.

## Configuration

**Site Setup → Translation** has three tabs:

- **Translation Service:** provider, API key, API URL.
- **Translation Options:** source and target languages, translated fields,
  which keys of a block hold text or links, and the content types that are
  never translated by machine (by default none). The source language is
  taken from the content first; the setting is the fallback.
- **Metadata Mapping:** fields carried over unchanged (named as the object
  stores them, e.g. `subject`; by default `image` and `file`, so images,
  files and lead images come along as a copy), and value tables per
  metadata field. A line
  `[field_id]` starts a table, followed by a header with language codes and
  one line per term:

  ```
  [subject]
  de, en, fr
  Forschung, Research, Recherche
  ```

  Values without a matching line are carried over unchanged.

## REST API

```
GET  /++api++/a-page/@translate
     configuration and translation status per language

POST /++api++/a-page/@translate
     {"target_language": "en"}                                   translated fields, nothing stored
     {"target_language": "en", "save": true}                     translate and store
     {"target_language": "en", "save": true, "overwrite": true}  replace an existing translation
     {"target_language": "en", "text": "Hallo"}                  translate a single text
```

`POST` needs the permission *Manage Translations*, `GET` needs *Modify portal
content*. Refusals come before DeepL is called: `400` on a working copy,
`409` for an excluded content type, for a save into the page's own language, over an existing translation
or working copy without `overwrite`, or when the translation cannot be checked
out (someone else is editing it, or the checkout permission is missing).

## Documentation

- [docs/architecture.md](docs/architecture.md): what each part does and why.
- [docs/extending.md](docs/extending.md): another translation service,
  another field shape, another block type.

## License

The project is licensed under the GNU General Public License, version 2 or
later (GPL-2.0-or-later). See [LICENSE.md](LICENSE.md).
