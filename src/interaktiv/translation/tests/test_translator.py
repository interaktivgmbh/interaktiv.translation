from unittest import TestCase, mock

from plone.namedfile.file import NamedFile, NamedImage

from interaktiv.translation.extractors import ExtractorRegistry, FieldExtractor, TextExtractor
from interaktiv.translation.providers.base import TranslationProvider
from interaktiv.translation.translator import ContentTranslator

# The smallest valid GIF: one transparent pixel.
GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


class Upper(TranslationProvider):
    name = "upper"
    title = "Upper"

    def __init__(self):
        self.calls = []

    def translate(self, texts, target_language, source_language=None):
        self.calls.append((list(texts), target_language, source_language))

        return [text.upper() for text in texts]

    def languages(self):
        return []

    def configured(self):
        return True


class Content:
    def __init__(self, **fields):
        for name, value in fields.items():
            setattr(self, name, value)


class TestContentTranslator(TestCase):
    def setUp(self):
        self.provider = Upper()
        self.settings = mock.Mock(
            block_text_keys=None,
            default_source_language="de",
        )
        self.settings.get_metadata_mapping.return_value = {}
        patcher = mock.patch(
            "interaktiv.translation.translator.settings",
            return_value=self.settings,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # which fields go along, and how: what the content type and the
        # control panel decide, here decided by the test
        self.modes = {"title": "translate", "description": "translate", "blocks": "translate"}
        patcher = mock.patch(
            "interaktiv.translation.translator.get_handled_fields",
            side_effect=lambda *args: dict(self.modes),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _translator(self):
        return ContentTranslator(translation_provider=self.provider)

    def test_fields_of__names_only_the_fields_the_content_has(self):
        content = Content(title="Titel", blocks={})

        self.assertEqual(self._translator().fields_of(content), ["title", "blocks"])

    def test_translate__answers_the_translated_fields_without_writing_them(self):
        # setup
        content = Content(title="Titel", description="Beschreibung")

        # do it
        result = self._translator().translate(content, "EN")

        # postcondition
        self.assertEqual(result, {"title": "TITEL", "description": "BESCHREIBUNG"})
        self.assertEqual(content.title, "Titel")

    def test_translate__passes_the_configured_source_language(self):
        # setup
        content = Content(title="Titel")

        # do it
        self._translator().translate(content, "EN")

        # postcondition
        self.assertEqual(self.provider.calls[0][2], "de")

    def test_translate__lets_the_caller_override_the_source_language(self):
        self._translator().translate(Content(title="Title"), "DE", source_language="en")

        self.assertEqual(self.provider.calls[0][2], "en")

    def test_translate__skips_a_field_that_is_empty(self):
        # setup
        content = Content(title="Titel", description="", blocks={})

        # do it
        result = self._translator().translate(content, "EN")

        # postcondition — nothing was sent for the empty ones
        self.assertEqual(list(result), ["title"])

    def test_translate__keeps_going_when_one_field_cannot_be_read(self):
        # setup
        class Exploding(FieldExtractor):
            def handles(self, value):
                return value == "boom"

            def texts(self, value):
                raise RuntimeError("this field is broken")

            def rebuild(self, value, translated):
                return value

        registry = ExtractorRegistry([TextExtractor()])
        registry.register(Exploding())
        translator = ContentTranslator(translation_provider=self.provider, extractors=registry)

        # do it
        result = translator.translate(Content(title="boom", description="Text"), "EN")

        # postcondition — the readable field still came back
        self.assertEqual(result, {"description": "TEXT"})

    def test_translate__carries_the_block_order_along_with_the_blocks(self):
        # setup — the order is not prose, and a page written without it holds
        # blocks that nothing lays out.
        content = Content(
            title="Titel",
            blocks={"b1": {"title": "Hallo"}},
            blocks_layout={"items": ["b1"]},
        )

        # do it
        result = self._translator().translate(content, "EN")

        # postcondition
        self.assertEqual(result["blocks_layout"], {"items": ["b1"]})
        self.assertEqual(result["blocks"], {"b1": {"title": "HALLO"}})

    def test_translate__does_not_send_the_block_order_to_the_service(self):
        content = Content(blocks={"b1": {"title": "Hallo"}}, blocks_layout={"items": ["b1"]})

        self._translator().translate(content, "EN")

        self.assertEqual([text for call in self.provider.calls for text in call[0]], ["Hallo"])

    def test_translate__leaves_the_order_out_when_the_blocks_never_came_back(self):
        # setup
        class Exploding(FieldExtractor):
            COMPANION_FIELDS = ("blocks_layout",)

            def handles(self, value):
                return isinstance(value, dict)

            def texts(self, value):
                raise RuntimeError("this field is broken")

            def rebuild(self, value, translated):
                return value

        registry = ExtractorRegistry([TextExtractor()])
        registry.register(Exploding())
        translator = ContentTranslator(translation_provider=self.provider, extractors=registry)
        content = Content(title="Titel", blocks={"b1": {}}, blocks_layout={"items": ["b1"]})

        # do it
        result = translator.translate(content, "EN")

        # postcondition
        self.assertEqual(result, {"title": "TITEL"})

    def test_translate__keeps_the_translation_when_postprocessing_fails(self):
        # setup — the translation is already made and paid for; a failing
        # link rewrite may cost the rewritten links, never the content.
        content = Content(
            title="Titel",
            blocks={"b1": {"title": "Hallo"}},
            blocks_layout={"items": ["b1"]},
        )

        # do it
        with mock.patch(
            "interaktiv.translation.translator.postprocess_links",
            side_effect=RuntimeError("broken link data"),
        ):
            result = self._translator().translate(content, "EN")

        # postcondition — every field carries the plain translation, and the
        # block order came along with the blocks
        self.assertEqual(result["title"], "TITEL")
        self.assertEqual(result["blocks"], {"b1": {"title": "HALLO"}})
        self.assertEqual(result["blocks_layout"], {"items": ["b1"]})

    def test_translate__maps_metadata_values_instead_of_translating_them(self):
        # setup
        self.modes.update({"field_a": "mapping"})
        self.settings.get_metadata_mapping.return_value = {
            "field_a": {"Wert A": "value a", "Wert B": "value b"},
        }
        content = Content(title="Titel", field_a=("Wert A", "Wert X"))

        # do it
        result = self._translator().translate(content, "EN")

        # postcondition — mapped where the table knows the value, carried
        # over unchanged where it does not, and still a tuple
        self.assertEqual(result["field_a"], ("value a", "Wert X"))
        # the mapped field never went to the provider
        sent = [text for call in self.provider.calls for text in call[0]]
        self.assertNotIn("Wert A", sent)

    def test_translate__maps_a_plain_string_metadata_field(self):
        # setup
        self.modes.update({"field_a": "mapping"})
        self.settings.get_metadata_mapping.return_value = {"field_a": {"Wert A": "value a"}}
        content = Content(title="Titel", field_a="Wert A")

        # do it
        result = self._translator().translate(content, "EN")

        # postcondition
        self.assertEqual(result["field_a"], "value a")

    def test_translate__reports_what_the_mapping_did_and_what_it_missed(self):
        # setup
        self.modes.update({"field_a": "mapping"})
        self.settings.get_metadata_mapping.return_value = {"field_a": {"Wert A": "value a"}}
        translator = self._translator()

        # do it
        translator.translate(Content(title="Titel", field_a=("Wert A", "Wert X")), "EN")

        # postcondition — same contract as the link report: `after` stays
        # None for a value the table does not know
        self.assertEqual(
            translator.metadata_report,
            [
                {"field": "field_a", "before": "Wert A", "after": "value a"},
                {"field": "field_a", "before": "Wert X", "after": None},
            ],
        )

        # a second run starts a fresh report
        translator.translate(Content(title="Titel", field_a=("Wert A",)), "EN")
        self.assertEqual(len(translator.metadata_report), 1)

    def test_translate__skips_a_mapped_field_the_content_does_not_have(self):
        # setup
        self.modes.update({"field_a": "mapping"})
        self.settings.get_metadata_mapping.return_value = {"field_a": {"Wert A": "value a"}}

        # do it
        result = self._translator().translate(Content(title="Titel"), "EN")

        # postcondition
        self.assertNotIn("field_a", result)

    def test_translate__skips_a_mapped_field_that_is_empty_in_the_source(self):
        # setup — nothing to map: the translation keeps the values it has
        self.modes.update({"field_a": "mapping", "field_b": "mapping"})
        self.settings.get_metadata_mapping.return_value = {"field_a": {"Wert A": "value a"}, "field_b": {}}
        content = Content(title="Titel", field_a=(), field_b="")

        # do it
        result = self._translator().translate(content, "EN")

        # postcondition
        self.assertNotIn("field_a", result)
        self.assertNotIn("field_b", result)

    def test_translate__carries_copy_fields_over_unchanged(self):
        # setup
        self.modes.update({"field_a": "copy", "field_b": "copy", "field_c": "copy"})
        content = Content(title="Titel", field_a=("Wert A", "Wert B"), field_b="Wert C", field_c=42)
        translator = self._translator()

        # do it
        result = translator.translate(content, "EN")

        # postcondition — taken over as they are, never sent to the provider
        self.assertEqual(result["field_a"], ("Wert A", "Wert B"))
        self.assertEqual(result["field_b"], "Wert C")
        self.assertEqual(result["field_c"], 42)
        sent = [text for call in self.provider.calls for text in call[0]]
        self.assertEqual(sent, ["Titel"])
        self.assertEqual(translator.copied_report, ["field_a", "field_b", "field_c"])

    def test_translate__copies_a_list_instead_of_sharing_it(self):
        # setup
        self.modes.update({"field_a": "copy"})
        content = Content(title="Titel", field_a=["Wert A"])

        # do it
        result = self._translator().translate(content, "EN")
        result["field_a"].append("Wert B")

        # postcondition — the source's list is untouched
        self.assertEqual(content.field_a, ["Wert A"])

    def test_translate__copies_a_file_instead_of_sharing_it(self):
        # setup
        self.modes.update({"field_a": "copy", "field_b": "copy"})
        content = Content(
            title="Titel",
            field_a=NamedFile(data=b"Inhalt A", contentType="text/plain", filename="datei-a.txt"),
            field_b=NamedImage(data=GIF, contentType="image/gif", filename="bild-b.gif"),
        )
        translator = self._translator()

        # do it
        result = translator.translate(content, "EN")

        # postcondition — same data, but an object of its own
        for field_id in ("field_a", "field_b"):
            source, copied = getattr(content, field_id), result[field_id]
            self.assertIsNot(copied, source)
            self.assertIs(type(copied), type(source))
            self.assertEqual(copied.data, source.data)
            self.assertEqual(copied.filename, source.filename)
            self.assertEqual(copied.contentType, source.contentType)
        self.assertEqual(translator.copied_report, ["field_a", "field_b"])

    def test_translate__skips_copy_fields_that_are_missing_or_empty(self):
        # setup — nothing to take over: the translation keeps what it has
        self.modes.update({"field_a": "copy", "field_b": "copy", "field_c": "copy"})
        content = Content(title="Titel", field_a=(), field_b=None)
        translator = self._translator()

        # do it
        result = translator.translate(content, "EN")

        # postcondition
        self.assertNotIn("field_a", result)
        self.assertNotIn("field_b", result)
        self.assertNotIn("field_c", result)
        self.assertEqual(translator.copied_report, [])

    def test_translate__skips_copy_fields_that_hold_no_plain_value(self):
        # setup — a reference must not travel as it is
        self.modes.update({"field_a": "copy", "field_b": "copy"})
        content = Content(title="Titel", field_a=object(), field_b=[object()])

        # do it
        result = self._translator().translate(content, "EN")

        # postcondition
        self.assertNotIn("field_a", result)
        self.assertNotIn("field_b", result)

    def test_translate__a_field_to_copy_is_not_mapped(self):
        # setup — the mapping knows the value, but the field is taken over
        self.modes.update({"field_a": "copy"})
        self.settings.get_metadata_mapping.return_value = {"field_a": {"Wert A": "value a"}}
        content = Content(title="Titel", field_a=("Wert A",))

        # do it
        result = self._translator().translate(content, "EN")

        # postcondition — the content type decides how a field goes along
        self.assertEqual(result["field_a"], ("Wert A",))

    def test_translate__asks_for_the_mapping_of_the_resolved_direction(self):
        # do it — no source given: the configured default counts
        self._translator().translate(Content(title="Titel"), "EN")

        # postcondition
        self.settings.get_metadata_mapping.assert_called_once_with("de", "EN")

    def test_translate__the_contents_own_language_beats_the_site_default(self):
        # do it — the page knows what language it holds; the default is a
        # guess that cannot cover a multilingual tree
        self._translator().translate(Content(title="Title", language="fr"), "DE")

        # postcondition
        self.assertEqual(self.provider.calls[0][2], "fr")

    def test_translate__survives_without_any_source_language(self):
        # setup — nothing configured, nothing on the content
        self.settings.default_source_language = None

        # do it
        result = self._translator().translate(Content(title="Titel"), "EN")

        # postcondition — translated with provider detection, mapping asked
        # with no direction
        self.assertEqual(result["title"], "TITEL")
        self.settings.get_metadata_mapping.assert_called_once_with(None, "EN")
