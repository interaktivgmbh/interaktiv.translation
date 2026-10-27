import plone.api as api

from interaktiv.translation.helpers.field_access import MISSING, field_value, set_field_value
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_INTEGRATION_TESTING, TestCase


class Content:
    def __init__(self, **fields):
        for name, value in fields.items():
            setattr(self, name, value)


class TestFieldAccess(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.page = api.content.create(container=self.portal, type="Document", id="page", title="Titel")

    def test_field_value__reads_a_field_its_behavior_keeps_elsewhere(self):
        # setup — the keywords of "subjects" live in "subject"
        self.page.setSubject(("Wert A",))

        # do it, postcondition
        self.assertEqual(field_value(self.page, "subjects"), ("Wert A",))

    def test_set_field_value__writes_a_field_its_behavior_keeps_elsewhere(self):
        # do it
        set_field_value(self.page, "subjects", ("Wert A",))

        # postcondition
        self.assertEqual(self.page.Subject(), ("Wert A",))

    def test_field_value__never_acquires_from_the_folder(self):
        # setup
        self.portal.field_a = "Wert A"

        # do it, postcondition
        self.assertIs(field_value(self.page, "field_a", MISSING), MISSING)

    def test_field_value__reads_an_object_without_a_type_as_attribute(self):
        self.assertEqual(field_value(Content(field_a="Wert A"), "field_a"), "Wert A")

    def test_set_field_value__writes_an_object_without_a_type_as_attribute(self):
        # setup
        content = Content()

        # do it
        set_field_value(content, "field_a", "Wert A")

        # postcondition
        self.assertEqual(content.field_a, "Wert A")
