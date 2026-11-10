from unittest import TestCase

from interaktiv.translation.storage import Refusal


class TestRefusal(TestCase):
    def test_refusal__is_its_message(self):
        # a refusal is shown as it is, e.g. as a Classic status message
        refusal = Refusal("code_a", "Message A", language="xx")

        self.assertEqual(refusal, "Message A")
        self.assertEqual(refusal.code, "code_a")
        self.assertEqual(refusal.values, {"language": "xx"})

    def test_error__carries_code_and_values(self):
        # do it
        error = Refusal("code_a", "Message A", language="xx").error(409)

        # postcondition
        self.assertEqual(str(error), "Message A")
        self.assertEqual(error.status, 409)
        self.assertEqual(error.code, "code_a")
        self.assertEqual(error.values, {"language": "xx"})
