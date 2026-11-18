from unittest import TestCase

from plone.app.textfield import RichText
from plone.namedfile.field import NamedBlobFile, NamedBlobImage
from plone.schema import JSONField
from z3c.relationfield.schema import RelationChoice, RelationList
from zope import schema

from interaktiv.translation.helpers.field_selection import (
    ALWAYS_FIELDS,
    COPIED_FIELDS,
    LINK_FIELDS,
    FieldRules,
    MODE_COPY,
    MODE_MAPPING,
    MODE_TRANSLATE,
    REASON_ALWAYS,
    REASON_FIELD_NAME,
    REASON_FIELD_TYPE,
    REASON_LINK,
    REASON_LANGUAGE_INDEPENDENT,
    REASON_MAPPING,
    REASON_REFERENCE,
    REASON_PRIMARY,
    ROLE_ALWAYS,
    ROLE_DEFAULT,
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
                # do it
                mode = mode_by_field_type(field)

                # postcondition
                self.assertEqual(mode, MODE_TRANSLATE)

    def test_mode__copies_values_that_mean_the_same_in_every_language(self):
        for field in (
            schema.Bool(),
            schema.Int(),
            schema.Float(),
            schema.Date(),
            schema.Datetime(),
            schema.Choice(values=["value_a", "value_b"]),
            NamedBlobImage(),
            NamedBlobFile(),
        ):
            with self.subTest(field=type(field).__name__):
                # do it
                mode = mode_by_field_type(field)

                # postcondition
                self.assertEqual(mode, MODE_COPY)

    def test_mode__copies_a_text_line_that_is_no_prose(self):
        for field in (schema.URI(), schema.ASCIILine()):
            with self.subTest(field=type(field).__name__):
                # do it
                mode = mode_by_field_type(field)

                # postcondition
                self.assertEqual(mode, MODE_COPY)

    def test_mode__copies_a_list_of_plain_values(self):
        for field in (schema.Tuple(value_type=schema.TextLine()), schema.List(value_type=schema.Choice(values=["a"]))):
            with self.subTest(field=type(field).__name__):
                # do it
                mode = mode_by_field_type(field)

                # postcondition
                self.assertEqual(mode, MODE_COPY)

    def test_mode__takes_a_reference_over(self):
        for field in (
            RelationChoice(vocabulary="plone.app.vocabularies.Catalog"),
            RelationList(value_type=RelationChoice(vocabulary="plone.app.vocabularies.Catalog")),
        ):
            with self.subTest(field=type(field).__name__):
                # do it
                mode = mode_by_field_type(field)

                # postcondition
                self.assertEqual(mode, MODE_COPY)

    def test_mode__cannot_take_a_structure_along(self):
        for field in (
            JSONField(),
            schema.Dict(),
            schema.Object(schema=schema.interfaces.IField),
            schema.List(value_type=schema.Dict()),
            schema.List(),
        ):
            with self.subTest(field=type(field).__name__):
                # do it
                mode = mode_by_field_type(field)

                # postcondition
                self.assertIsNone(mode)


class TestClassifyField(TestCase):
    def test_classify__a_plain_field_goes_along_by_its_type(self):
        # do it
        text_line = classify_field(_named(schema.TextLine()))
        boolean = classify_field(_named(schema.Bool()))

        # postcondition
        self.assertEqual(text_line, (ROLE_DEFAULT, MODE_TRANSLATE, REASON_FIELD_TYPE))
        self.assertEqual(boolean, (ROLE_DEFAULT, MODE_COPY, REASON_FIELD_TYPE))

    def test_classify__title_and_page_content_always_go_along(self):
        for name in ALWAYS_FIELDS:
            with self.subTest(name=name):
                # do it
                role, mode, reason = classify_field(_named(schema.TextLine(), name))

                # postcondition
                self.assertEqual((role, mode, reason), (ROLE_ALWAYS, MODE_TRANSLATE, REASON_ALWAYS))

    def test_classify__the_blocks_always_go_along_translated(self):
        # do it
        classified = classify_field(_named(JSONField(), "blocks"))

        # postcondition
        self.assertEqual(classified, (ROLE_ALWAYS, MODE_TRANSLATE, REASON_ALWAYS))

    def test_classify__the_primary_field_always_goes_along(self):
        # do it
        classified = classify_field(_named(NamedBlobImage()), primary=True)

        # postcondition
        self.assertEqual(classified, (ROLE_ALWAYS, MODE_COPY, REASON_PRIMARY))

    def test_classify__a_reference_is_taken_over(self):
        # do it
        classified = classify_field(_named(RelationChoice(vocabulary="plone.app.vocabularies.Catalog")))

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_COPY, REASON_REFERENCE))

    def test_classify__a_reference_is_taken_over_whatever_else_names_it(self):
        # setup
        field = _named(RelationChoice(vocabulary="plone.app.vocabularies.Catalog"), COPIED_FIELDS[0])

        # do it
        classified = classify_field(field, language_independent=True)

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_COPY, REASON_REFERENCE))

    def test_classify__a_mapped_field_goes_through_the_mapping(self):
        # do it
        classified = classify_field(_named(schema.Tuple(value_type=schema.TextLine())), mapped_fields=["field_a"])

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_MAPPING, REASON_MAPPING))

    def test_classify__a_reference_is_not_mapped(self):
        # setup
        field = _named(RelationList(value_type=RelationChoice(vocabulary="plone.app.vocabularies.Catalog")))

        # do it
        classified = classify_field(field, mapped_fields=["field_a"])

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_COPY, REASON_REFERENCE))

    def test_classify__a_link_field_is_taken_over_as_a_link(self):
        for name in LINK_FIELDS:
            with self.subTest(name=name):
                # do it
                classified = classify_field(_named(schema.TextLine(), name), mapped_fields=[name])

                # postcondition
                self.assertEqual(classified, (ROLE_DEFAULT, MODE_COPY, REASON_LINK))

    def test_classify__goes_by_the_link_fields_of_the_site(self):
        # setup
        rules = FieldRules(links=("field_a",))

        # do it
        classified = classify_field(_named(schema.TextLine()), rules=rules)

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_COPY, REASON_LINK))

    def test_classify__a_known_field_name_is_copied_though_its_type_is_text(self):
        # do it
        classified = classify_field(_named(schema.TextLine(), COPIED_FIELDS[0]))

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_COPY, REASON_FIELD_NAME))

    def test_classify__a_link_field_goes_along_though_its_type_could_not(self):
        # setup
        field = _named(schema.List(value_type=schema.Dict()), "query")

        # do it
        classified = classify_field(field)

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_COPY, REASON_LINK))

    def test_classify__a_language_independent_field_is_copied(self):
        # do it
        classified = classify_field(_named(schema.TextLine()), language_independent=True)

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_COPY, REASON_LANGUAGE_INDEPENDENT))

    def test_classify__the_mapping_comes_before_the_other_rules(self):
        # setup
        field = _named(schema.TextLine(), COPIED_FIELDS[0])

        # do it
        classified = classify_field(field, language_independent=True, mapped_fields=[COPIED_FIELDS[0]])

        # postcondition
        self.assertEqual(classified, (ROLE_DEFAULT, MODE_MAPPING, REASON_MAPPING))


class TestAlwaysFirst(TestCase):
    def test_always_first__puts_title_description_and_page_content_on_top(self):
        # setup
        fields = [{"id": name} for name in ("field_a", "blocks", "field_b", "description", "title")]

        # do it
        ordered = always_first(fields)

        # postcondition
        self.assertEqual(
            [field["id"] for field in ordered],
            ["title", "description", "blocks", "field_a", "field_b"],
        )
