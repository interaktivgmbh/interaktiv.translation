"""The API key is stored encrypted (Fernet, from ``cryptography``)."""

import base64
import hashlib
import os
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from plone.keyring.interfaces import IKeyManager
from plone.keyring.keyring import Keyring
from zope.component import queryUtility

SECRET_VARIABLE = "INTERAKTIV_TRANSLATION_SECRET"
KEYRING_NAME = "interaktiv.translation"

PREFIX = "fernet:"
TAG_ENVIRONMENT = "env"
TAG_SITE = "site"

# where the secret of a stored key comes from, for the control panel to tell
ENCRYPTION_ENVIRONMENT = "environment"
ENCRYPTION_SITE = "site"
ENCRYPTION_NONE = "none"
ENCRYPTIONS = {TAG_ENVIRONMENT: ENCRYPTION_ENVIRONMENT, TAG_SITE: ENCRYPTION_SITE}


class UnreadableSecret(Exception):
    """A stored value whose secret is gone or changed."""


def _fernet(secret: str) -> Fernet:
    # any string will do: Fernet wants 32 bytes, url-safe base64
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest()))


def _environment_secret() -> Optional[str]:
    return os.environ.get(SECRET_VARIABLE) or None


def _site_keyring(create: bool = False) -> Optional[Keyring]:
    manager = queryUtility(IKeyManager)
    if manager is None:
        return None

    if KEYRING_NAME not in manager:
        if not create:
            return None
        manager[KEYRING_NAME] = Keyring()
        manager[KEYRING_NAME].fill()

    return manager[KEYRING_NAME]


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value: str) -> str:
    secret = _environment_secret()
    if secret:
        tag = TAG_ENVIRONMENT
    else:
        tag = TAG_SITE
        secret = _site_keyring(create=True).current

    token = _fernet(secret).encrypt(value.encode("utf-8")).decode("ascii")

    return f"{PREFIX}{tag}:{token}"


def _secrets_for(tag: str) -> List[str]:
    if tag == TAG_ENVIRONMENT:
        secret = _environment_secret()
        return [secret] if secret else []
    if tag == TAG_SITE:
        keyring = _site_keyring()
        # every secret of the ring: a rotation must not lose the key
        return [secret for secret in keyring or [] if secret]

    return []


def decrypt(value: str) -> str:
    if not is_encrypted(value):
        return value

    tag, _, token = value[len(PREFIX) :].partition(":")
    secrets = _secrets_for(tag)
    if not secrets:
        raise UnreadableSecret(f"No secret to decrypt a value encrypted with '{tag}'.")

    try:
        return MultiFernet([_fernet(secret) for secret in secrets]).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise UnreadableSecret(f"The secret '{tag}' does not decrypt the stored value.") from error


def stored_value(value: Any) -> Optional[str]:
    """returns encrypted value if not yet encrypted"""
    if not value:
        return None
    if not is_encrypted(value):
        return encrypt(value)

    tag = value[len(PREFIX) :].partition(":")[0]
    if tag == TAG_SITE and _environment_secret():
        try:
            return encrypt(decrypt(value))
        except UnreadableSecret:
            return None

    return None


def encryption_status(value: Any) -> Dict[str, Any]:
    if not value:
        return {"stored": False, "encryption": None, "readable": False}

    if not is_encrypted(value):
        return {"stored": True, "encryption": ENCRYPTION_NONE, "readable": True}

    tag = value[len(PREFIX) :].partition(":")[0]
    try:
        decrypt(value)
        readable = True
    except UnreadableSecret:
        readable = False

    return {"stored": True, "encryption": ENCRYPTIONS.get(tag, ENCRYPTION_NONE), "readable": readable}
