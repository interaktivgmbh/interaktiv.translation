from unittest import TestCase

from plone.app.textfield import RichText
from plone.namedfile.field import NamedBlobFile, NamedBlobImage
from plone.schema import JSONField
from z3c.relationfield.schema import RelationChoice, RelationList
from zope import schema

from interaktiv.translation.helpers.field_selection import (
    ALWAYS_FIELDS,
    COPIED_FIELDS,
    MODE_COPY,
    MODE_MAPPING,
    MODE_TRANSLATE,
    REASON_ALWAYS,
    REASON_FIELD_NAME,
    REASON_FIELD_TYPE,
    REASON_LANGUAGE_INDEPENDENT,
    REASON_MAPPING,
    REASON_PRIMARY,
    ROLE_ALWAYS,
    ROLE_DEFAULT,
    ROLE_IMPOSSIBLE,
    always_first,
    classify_field,
    mode_by_field_type,
)


def _named(field, name="field_a"):
    field.__name__ = name
    return field


class TestModeByFieldType(TestCase):
    def test_mode__translates_text(self):
        for field in (schema.TextLine(), schema.Text(), RichText()):
            with self.subTest(field=type(field).__name__):
                self.assertEqual(mode_by_field_type(field), MODE_TRANSLATE)

    def test_mode__copies_values_that_mean_the_same_in_every_language(self):
        fields = (
            schema.Bool(),
            schema.Int(),
            schema.Float(),
            schema.Date(),
            schema.Datetime(),
            schema.Choice(values=["value_a", "value_b"]),
            NamedBlobImage(),
            NamedBlobFile(),
        )
        for field in fields:
            with self.subTest(field=type(field).__name__):
                self.assertEqual(mode_by_field_type(field), MODE_COPY)

    def test_mode__copies_a_text_line_that_is_no_prose(self):
        # an URI and an ASCII line are text lines too, but addresses and tokens
        for field in (schema.URI(), schema.ASCIILine()):
            with self.subTest(field=type(field).__name__):
                self.assertEqual(mode_by_field_type(field), MODE_COPY)

    def test_mode__copies_a_list_of_plain_values(self):
        for field in (schema.Tuple(value_type=schema.TextLine()), schema.List(value_type=schema.Choice(values=["a"]))):
            with self.subTest(field=type(field).__name__):
                self.assertEqual(mode_by_field_type(field), MODE_COPY)

    def test_mode__cannot_take_a_reference_or_a_structure_along(self):
        fields = (
            RelationChoice(vocabulary="plone.app.vocabularies.Catalog"),
            RelationList(value_type=RelationChoice(vocabulary="plone.app.vocabularies.Catalog")),
            JSONField(),
            schema.Dict(),
            schema.Object(schema=schema.interfaces.IField),
            schema.List(value_type=schema.Dict()),
            schema.List(),
        )
        for field in fields:
            with self.subTest(field=type(field).__name__):
                self.assertIsNone(mode_by_field_type(field))


class TestClassifyField(TestCase):
    def test_classify__a_plain_field_goes_along_by_its_type(self):
        self.assertEqual(
            classify_field(_named(schema.TextLine())),
            (ROLE_DEFAULT, MODE_TRANSLATE, REASON_FIELD_TYPE),
        )
        self.assertEqual(
            classify_field(_named(schema.Bool())),
            (ROLE_DEFAULT, MODE_COPY, REASON_FIELD_TYPE),
        )

    def test_classify__title_and_page_content_always_go_along(self):
        for name in ALWAYS_FIELDS:
            with self.subTest(name=name):
                role, mode, reason = classify_field(_named(schema.TextLine(), name))
                self.assertEqual((role, mode, reason), (ROLE_ALWAYS, MODE_TRANSLATE, REASON_ALWAYS))

    def test_classify__the_blocks_always_go_along_translated(self):
        # a JSON field could not go along by its type; the page content does
        self.assertEqual(
            classify_field(_named(JSONField(), "blocks")),
            (ROLE_ALWAYS, MODE_TRANSLATE, REASON_ALWAYS),
        )

    def test_classify__the_primary_field_always_goes_along(self):
        self.assertEqual(
            classify_field(_named(NamedBlobImage()), primary=True),
            (ROLE_ALWAYS, MODE_COPY, REASON_PRIMARY),
        )

    def test_classify__a_primary_reference_still_cannot_go_along(self):
        role, mode, _reason = classify_field(
            _named(RelationChoice(vocabulary="plone.app.vocabularies.Catalog")), primary=True
        )

        self.assertEqual((role, mode), (ROLE_IMPOSSIBLE, None))

    def test_classify__a_mapped_field_goes_through_the_mapping(self):
        self.assertEqual(
            classify_field(_named(schema.Tuple(value_type=schema.TextLine())), mapped_fields=["field_a"]),
            (ROLE_DEFAULT, MODE_MAPPING, REASON_MAPPING),
        )

    def test_classify__a_reference_is_not_mapped(self):
        field = _named(RelationList(value_type=RelationChoice(vocabulary="plone.app.vocabularies.Catalog")))

        self.assertEqual(classify_field(field, mapped_fields=["field_a"])[:2], (ROLE_IMPOSSIBLE, None))

    def test_classify__a_known_field_name_is_copied_though_its_type_is_text(self):
        self.assertEqual(
            classify_field(_named(schema.TextLine(), COPIED_FIELDS[0])),
            (ROLE_DEFAULT, MODE_COPY, REASON_FIELD_NAME),
        )

    def test_classify__a_known_field_name_is_copied_though_its_type_could_not_go_along(self):
        # the search of a collection is a list of structures
        field = _named(schema.List(value_type=schema.Dict()), "query")

        self.assertEqual(classify_field(field), (ROLE_DEFAULT, MODE_COPY, REASON_FIELD_NAME))

    def test_classify__a_language_independent_field_is_copied(self):
        self.assertEqual(
            classify_field(_named(schema.TextLine()), language_independent=True),
            (ROLE_DEFAULT, MODE_COPY, REASON_LANGUAGE_INDEPENDENT),
        )

    def test_classify__the_mapping_comes_before_the_other_rules(self):
        field = _named(schema.TextLine(), COPIED_FIELDS[0])

        self.assertEqual(
            classify_field(field, language_independent=True, mapped_fields=[COPIED_FIELDS[0]]),
            (ROLE_DEFAULT, MODE_MAPPING, REASON_MAPPING),
        )


class TestAlwaysFirst(TestCase):
    def test_always_first__puts_title_description_and_page_content_on_top(self):
        # setup
        fields = [{"id": name} for name in ("field_a", "blocks", "field_b", "description", "title")]

        # do it
        ordered = always_first(fields)

        # postcondition — the rest keep their order
        self.assertEqual(
            [field["id"] for field in ordered],
            ["title", "description", "blocks", "field_a", "field_b"],
        )
