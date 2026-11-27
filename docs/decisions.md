# Decisions

Why the code looks the way it does, where a line of code cannot say it.
What each part does is in [architecture.md](architecture.md).

## Storing a translation (`storage.py`)

**Whether an add-on is installed is read from its profile version.**
`getProfileImportDate` answers out of the import log files `portal_setup`
keeps, whose names carry the `profile-` prefix the caller does not write: it
says "never imported" for a profile that is installed. The profile version
is what Plone's own installer asks. `multilingual` and `working_copies` are
both read this way; an admin switches working copies on by installing
`plone.app.iterate`.

**With `plone.app.iterate` an existing translation is checked out, never
overwritten.** The machine translation lands in a working copy an editor
reviews and checks in. iterate checks out only what can be locked: a type
without the `plone.locking` behavior (a stock Folder) is never checked out,
so its translation is overwritten as on a site without iterate.

**A working copy that is already there is never replaced, not even on
request.** It holds somebody's work.

**A checkout is refused by iterate's own rules before it is tried.**
Somebody editing the translation right now would lose their lock, and with
it their unsaved work.

**`refusal()` is the one place that decides whether a save would be
refused.** The service asks it before the translation service is paid, and
`store` raises the same way. `None` means "go ahead".

**The open working copy is found without iterate's `getWorkingCopy()`.**
That one takes the first relation, even a broken one left by a working copy
that was deleted instead of discarded. `working_copy_of` answers `None`
where iterate is not installed, so its callers need not guard separately.

**A stored translation fires `ObjectModifiedEvent`, not only a reindex.**
Versioning, link integrity and cache purging all hang off the modified
event; a translation that skips it leaves an object nobody can roll back.

**A translation stored in place sets the language of the page itself.** No
second object was made, and the language is the field the catalog and the
front end both read. On the other path `plone.app.multilingual` sets it on
the object it creates.

**The baseline is versioned before a checkout, with a comment of our own.**
`archiver.save` is called before iterate's `handleBeforeCheckout` does it, so
the history names what the working copy was cut from.

**`stored_as`, `created` and `source_language` are kept on the storage.**
They tell the report an editor is shown where the translation went and
whether that object is new.

## The id of a translation (`translation_id.py`, `configure.zcml`)

**A machine translation is named after its translated title.** That is how
Plone names content created by hand; anything else `plone.app.multilingual`
creates keeps the id of the original. The title is normalized by the rules
of the target language: the name chooser alone would take those of the
request, which is on the source.

**The id chooser is registered for the more specific interface.** It is
chosen over `plone.app.multilingual`'s own (for `ITranslatable`) without an
override, and falls back to that one.

## One translation run (`translator.py`)

**A failed link rewrite never costs the content.** The translation is
already made and paid for; the field keeps its translated value and the
failure is logged.

**The companions of a field are written only once the field itself came
back.** A companion on its own would describe a value that was never
written.

**Only values that mean the same in every language are taken over
unchanged** (`COPYABLE_TYPES`). A reference travels too, pointed at the
translation of its target.

**The HTML of an HTML block is told by the type of the block, not by a
text key** (`blocks.py`). A text key holds plain text and is escaped for
the provider; `html` named there would arrive as escaped markup. The block
is found inside other blocks as well.

## Which fields go along (`helpers/field_selection.py`)

**The lists of field names are the defaults of the settings of the same
names.** `excluded_fields`, `always_fields`, `copied_fields` and
`link_fields` are changed per site in the advanced settings.

**`copied_fields` names text that is no prose.** An address, a rule, or the
search of a collection would be translated by its kind of field. A field
named there is taken over in every content type and cannot be chosen to be
translated for one.

**A choice field with a vocabulary of its own tells its values; a named
vocabulary is taken for texts.** A named one is looked up only with a
context, which the listing does not have.

## Links (`helpers/links.py`)

**Only a broken link is a mistake.** An editor may well link content of
another language, so every other status is information.

**A reference to content without a translation is kept.** A broken
reference, read as `None`, is left out.

**`check=True` changes nothing and reports more.** The link status goes
through the same code as the translation, but writes nothing and names the
links that lead out of the site as well.

**The link check reads more fields than the schemas name.** A type may have
fields always translated or holding links without a schema saying so; the
check reads them as the translator does.

**A path a listing searches below is written the way it came.** A UID stays
a UID, a path keeps or leaves out its root, the depth after `::` is kept. A
navigation path is read from the navigation root of the content and written
from that of the translated folder.

**A relative path is told from where the translation lies, or will lie.**
Where the content has no translation yet, that is the folder Plone would
create it in. The path is the shortest one there, so `../../a/b` may come
back as `../b`. A path with a name that leads nowhere is left alone: Plone
skips such a name, and guessing along would point the listing elsewhere.

**A path to a folder without a translation is kept and reported, even
where it leads nowhere in the target language.** A navigation path or a
relative path is read from the translation then and names a folder that is
not there; Plone treats it like any unknown path. Once the folder is
translated under the same id, the path holds again.

**A link in raw HTML is written back the way it came.** Plone stores the
HTML of an HTML block as it is and resolves no `resolveuid` in it, so a path
stays a path and a full address a full address. Only the value of the
attribute is replaced; the HTML is not parsed and written anew.

**In raw HTML only what is surely internal is touched.** A path from the
root and an address that starts with the site's own. A relative path is
left alone: the browser reads it from the address of the page, Plone from
the page as a folder, and the two differ. An attribute without quotes is
left alone as well.

**The address of a computed scale does not travel to another image.**
`@@images/image-800-<hash>.png` is stored with the image it was made of;
the translation of the image answers it with "not found". Such an address
is pointed at the image as it was uploaded, `@@images/image`: the right
image, at the cost of its full size.

**The rich text of a block is known by the text keys.** The same keys
decide what is translated, so a rich text that is translated has its links
pointed at translations, and one that is not is left alone altogether.

**What an object browser stored of its target comes from the target, in
every language.** It is a copy of the catalog entry, taken when the target
was chosen, and `plone.restapi` renews only `@id` and `image_scales` of it.
Pointed at a translation, every key the entry holds is read anew from the
catalog entry of that page, the way a search with `metadata_fields=_all`
tells it. A key without a value there is kept as `null`, as a fresh choice
stores it. No key is added: which ones a block asked for only the front end
knows.

**What an object browser stored of its target is never translated**
(`blocks.py`). The texts are those of another page: with a translation they
come from it, without one they stay. Such an entry is told by its `@id`
being a link; an `@id` that only numbers an item, a tab or a column, leaves
the item's text to be translated. A block that keeps text of its own next
to a link in `@id` loses the translation of that text.

**An entry with a key the catalog does not know is no such copy.** It is a
block of its own that names a target next to its own values; only its
`@id` is pointed at the translation.

**In raw HTML only `<a href>` and `<img src>` are links.** A script, a
style sheet or a frame hardly ever names content of the site and would
only fill the report with broken links.

## Slate (`helpers/slate.py`)

**What HTML has no place for never leaves the backend.** The style of a
paragraph, the target of a link and the style of a word stay in a table: the
node is numbered (`data-slate-node`), only the number travels with the text,
and the parser hands the properties back by it.

**Open tags are kept by their resolved type.** A closing alias (`</b>` for
`<strong>`) still finds its opener.

**A truncated answer is closed the way a matching end tag would have closed
it.** Every element then holds at least one text child, an empty one where
nothing came back: Slate's invariant.

## DeepL (`providers/deepl.py`)

**A rate-limited request (429) is retried**, with a growing delay plus
jitter.

**A glossary DeepL refuses does not fail the translation.** A glossary it
does not know, or one of another language pair, is logged and the
translation goes on without it.

**The texts are sent in chunks within the payload limits.** A single text
larger than the size limit raises and ends the run.

## Services and the control panel

**`POST @translate` switches CSRF protection off for its request.**
`plone.protect` guards writes made during a request it cannot tie to a form
token, and a REST client has none: without this the store runs, answers
`saved`, and is then rolled back unwritten.

**The connection test is a POST, although it only asks.** The form may hold
a new API key, which must not go into a URL (access logs, proxies, browser
history). What the form leaves out, or the placeholder of the key, is taken
as stored. A failure is an answer (`ok: false`), not an error of the
request.

**`PATCH @workingcopy` overrides `plone.restapi`'s.** Called on the
baseline, the policy that can check in is the working copy's.

**The API key never goes to the browser.** Its serializer answers a
placeholder (`controlpanels/api_key.py`), and `GET @translation-connection`
tells only how the key is kept: `stored`, `encryption` (`environment`,
`site` or `none`) and `readable`.

**The API key is encrypted on its way into the registry, whichever way it
comes**: the control panels, the registry's own view, a profile. Saving the
settings also moves a key to the environment's secret once that is set.

**A stored value of the control panel always finds its term.**
`plone.restapi` cannot show the control panel otherwise. A content type or
a language that went away stays in its vocabulary to be chosen off, under
its id or code.

**The condition of the Translate action calls the view, it reads no
attribute.** The condition is TALES in restricted Python, and reading an
attribute off a view there raises "the container has no security
assertions". That only shows when the action is really evaluated, never
when the expression is merely read, so a test evaluates it.

## Working copies and permissions (`subscribers/events.py`)

**A working copy cannot be translated.** On checkout the permission to
manage translations is set to a tuple of no roles, which stops acquiring;
on checkin it is set to a list, which acquires again.

## Upgrade steps

**1000 → 1001 keeps only the target languages the site has.** The registry
import empties the whole list for a single code that is no site language,
and an empty list offers every site language.

**1001 → 1002 renews the registry field before it writes.** The record's
old field takes a list of fields per content type and refuses the new form.

## Providers (`providers/base.py`)

**`check()` answers what it knows of the account**: `plan`,
`character_count`, `character_limit`. `glossaries()` answers `id`, `name`,
`source`, `target` and `entries` per glossary.
