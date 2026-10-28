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
  requested explicitly. An existing working copy is never overwritten.
- Marks machine translations and tracks their review (unreviewed, edited,
  reviewed). A banner and the Manage Translations view show the state;
  checking in or publishing counts as review and is noted in the history.
  Content without a workflow, such as files and images in a default Plone,
  cannot be published and needs no review.
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

**Site Setup → Translation** has four tabs:

- **Translation Service:** the provider, the offered target languages, the
  API URL (only for a proxy) and the API key, with a button that tests the
  connection and tells the account's usage. Content without a language of
  its own is taken to be in the site's default language.
- **Metadata Field Selection:** per content type the fields that go into a
  translation. Title, description and page content always go along, and so
  does the type's main field (the image of an image); the others are chosen.
  Whether a field is translated or taken over follows from its kind.
- **Metadata Mapping:** fixed translations for the values of metadata
  fields (as `subjects`), per field one row per value with one entry per
  language; with import and export as Excel file.
- **Advanced Settings:** the fields never translated, always translated and
  taken over unchanged, for every content type; which keys of a block hold
  text or links; link fields; the content types never translated by machine.

### The API key

The control panel never hands the API key to the browser, and the key is
stored encrypted. The secret to encrypt with comes from the environment
variable `INTERAKTIV_TRANSLATION_SECRET`; without it the add-on keeps a secret
of its own in the site's keyring. Then the key cannot be read in the
registry, but a backup of the database holds what decrypts it — set the
variable in production:

```shell
# once: any long random string will do
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```yaml
# instance.yaml (cookiecutter-zope-instance)
default_context:
  environment:
    INTERAKTIV_TRANSLATION_SECRET: "<the string>"
```

or `INTERAKTIV_TRANSLATION_SECRET=<the string>` in the container's
environment. A key stored under another secret, or before the variable was
set and then removed, cannot be read any more: the control panel says so, and
the key is entered again.

## REST API

```
GET  /++api++/a-page/@translate
     configuration and translation status per language

POST /++api++/a-page/@translate
     {"target_language": "en"}                                   translated fields, nothing stored
     {"target_language": "en", "save": true}                     translate and store
     {"target_language": "en", "save": true, "overwrite": true}  replace an existing translation
     {"target_language": "en", "text": "Hallo"}                  translate a single text

GET  /++api++/@translation-fields
     per content type its fields and how the translation treats them

GET  /++api++/@translation-connection
     how the stored API key is kept: stored, encryption, readable — never the key

POST /++api++/@translation-connection
     {"provider": "deepl", "api_key": "…"}                       test the service, tell the account
```

The three site endpoints need *Manage portal*.

`POST` needs the permission *Manage Translations*, `GET` needs *Modify portal
content*. Refusals come before DeepL is called: `400` on a working copy,
`409` for an excluded content type, for a save into the page's own language, over an existing translation
without `overwrite`, over an existing working copy (even with `overwrite`), or
when the translation cannot be checked out (someone else is editing it, or the
checkout permission is missing).

## Documentation

- [docs/architecture.md](docs/architecture.md): what each part does and why.
- [docs/extending.md](docs/extending.md): another translation service,
  another field shape, another block type.

## License

The project is licensed under the GNU General Public License, version 2 or
later (GPL-2.0-or-later). See [LICENSE.md](LICENSE.md).
