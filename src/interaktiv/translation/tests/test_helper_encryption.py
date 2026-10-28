import os
from unittest import mock

from plone.keyring.interfaces import IKeyManager
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from interaktiv.translation.helpers.encryption import (
    ENCRYPTION_ENVIRONMENT,
    ENCRYPTION_NONE,
    ENCRYPTION_SITE,
    KEYRING_NAME,
    SECRET_VARIABLE,
    UnreadableSecret,
    decrypt,
    encrypt,
    encryption_status,
    is_encrypted,
)
from interaktiv.translation.registry.translation import ITranslationSettings
from interaktiv.translation.settings import Settings
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_INTEGRATION_TESTING, TestCase

API_KEY_RECORD = f"{ITranslationSettings.__identifier__}.api_key"


class TestEncryption(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.patcher = mock.patch.dict(os.environ, {})
        self.patcher.start()
        os.environ.pop(SECRET_VARIABLE, None)
        self.addCleanup(self.patcher.stop)

    def test_encrypt__without_a_secret_of_the_environment_takes_the_sites(self):
        # do it
        stored = encrypt("key-value-a")

        # postcondition — a keyring of the add-on's own was made for it
        self.assertTrue(stored.startswith("fernet:site:"))
        self.assertNotIn("key-value-a", stored)
        self.assertIn(KEYRING_NAME, getUtility(IKeyManager))
        self.assertEqual(decrypt(stored), "key-value-a")

    def test_encrypt__takes_the_secret_of_the_environment(self):
        # setup
        os.environ[SECRET_VARIABLE] = "secret-a"

        # do it
        stored = encrypt("key-value-a")

        # postcondition
        self.assertTrue(stored.startswith("fernet:env:"))
        self.assertEqual(decrypt(stored), "key-value-a")

    def test_decrypt__fails_for_another_secret_of_the_environment(self):
        # setup
        os.environ[SECRET_VARIABLE] = "secret-a"
        stored = encrypt("key-value-a")
        os.environ[SECRET_VARIABLE] = "secret-b"

        # do it, postcondition
        with self.assertRaises(UnreadableSecret):
            decrypt(stored)

    def test_decrypt__fails_without_the_secret_of_the_environment(self):
        # setup
        os.environ[SECRET_VARIABLE] = "secret-a"
        stored = encrypt("key-value-a")
        del os.environ[SECRET_VARIABLE]

        # do it, postcondition
        with self.assertRaises(UnreadableSecret):
            decrypt(stored)

    def test_decrypt__survives_a_rotation_of_the_sites_keyring(self):
        # setup
        stored = encrypt("key-value-a")
        getUtility(IKeyManager).rotate(KEYRING_NAME)

        # do it, postcondition
        self.assertEqual(decrypt(stored), "key-value-a")

    def test_decrypt__reads_a_key_stored_before_encryption(self):
        self.assertEqual(decrypt("key-value-a"), "key-value-a")

    def test_status__tells_how_a_value_is_kept(self):
        # setup
        site = encrypt("key-value-a")
        os.environ[SECRET_VARIABLE] = "secret-a"
        environment = encrypt("key-value-a")

        # do it, postcondition
        self.assertEqual(encryption_status(""), {"stored": False, "encryption": None, "readable": False})
        self.assertEqual(
            encryption_status("key-value-a"), {"stored": True, "encryption": ENCRYPTION_NONE, "readable": True}
        )
        self.assertEqual(encryption_status(site), {"stored": True, "encryption": ENCRYPTION_SITE, "readable": True})
        self.assertEqual(
            encryption_status(environment), {"stored": True, "encryption": ENCRYPTION_ENVIRONMENT, "readable": True}
        )
        os.environ[SECRET_VARIABLE] = "secret-b"
        self.assertFalse(encryption_status(environment)["readable"])

    def test_registry__stores_a_key_set_in_plain_text_encrypted(self):
        # do it — as the registry's own view or a profile would
        getUtility(IRegistry)[API_KEY_RECORD] = "key-value-a"

        # postcondition
        self.assertTrue(is_encrypted(getUtility(IRegistry)[API_KEY_RECORD]))
        self.assertEqual(Settings().api_key, "key-value-a")

    def test_settings__answer_no_key_for_one_that_cannot_be_read(self):
        # setup
        os.environ[SECRET_VARIABLE] = "secret-a"
        getUtility(IRegistry)[API_KEY_RECORD] = "key-value-a"
        os.environ[SECRET_VARIABLE] = "secret-b"

        # do it, postcondition — not configured, rather than a wrong key sent
        self.assertEqual(Settings().api_key, "")
        self.assertFalse(Settings().api_key_status["readable"])

    def test_registry__moves_a_key_to_the_secret_of_the_environment_once_it_is_set(self):
        # setup — stored while the environment had no secret
        getUtility(IRegistry)[API_KEY_RECORD] = "key-value-a"
        os.environ[SECRET_VARIABLE] = "secret-a"

        # do it — the settings saved again, the key unchanged
        getUtility(IRegistry)[API_KEY_RECORD] = getUtility(IRegistry)[API_KEY_RECORD]

        # postcondition
        self.assertTrue(getUtility(IRegistry)[API_KEY_RECORD].startswith("fernet:env:"))
        self.assertEqual(Settings().api_key, "key-value-a")

    def test_registry__keeps_a_key_it_cannot_read(self):
        # setup
        os.environ[SECRET_VARIABLE] = "secret-a"
        getUtility(IRegistry)[API_KEY_RECORD] = "key-value-a"
        stored = getUtility(IRegistry)[API_KEY_RECORD]
        os.environ[SECRET_VARIABLE] = "secret-b"

        # do it
        getUtility(IRegistry)[API_KEY_RECORD] = stored

        # postcondition — to be entered again, not lost to a wrong secret
        self.assertEqual(getUtility(IRegistry)[API_KEY_RECORD], stored)
