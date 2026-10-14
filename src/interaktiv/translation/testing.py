import importlib
import unittest
from typing import Any, List, Optional

import requests
from plone.app.testing import (
    PLONE_FIXTURE,
    TEST_USER_ID,
    FunctionalTesting,
    IntegrationTesting,
    PloneSandboxLayer,
    applyProfile,
    setRoles,
)
from plone.base.utils import get_installer
from plone.protect import auto as protect_auto
from plone.testing.zope import WSGI_SERVER_FIXTURE
from Products.CMFCore.utils import getToolByName
from zope.component import getMultiAdapter

from interaktiv.translation import ADDON_DEPENDENCIES


class InteraktivTranslationLayer(PloneSandboxLayer):
    defaultBases = (PLONE_FIXTURE,)

    def __init__(self) -> None:
        super().__init__()

        self.products_to_import: List[str] = list(ADDON_DEPENDENCIES)

    def setUpZope(self, app: Any, configuration_context: Any) -> None:
        for name in self.products_to_import:
            self.loadZCML(package=importlib.import_module(name))
        self.loadZCML(package=importlib.import_module("interaktiv.translation"))

    def setUpPloneSite(self, portal: Any) -> None:
        if "plone.app.multilingual" in self.products_to_import:
            getToolByName(portal, "portal_languages").addSupportedLanguage("de")

        applyProfile(portal, "interaktiv.translation:default")

        self._csrf_disabled = protect_auto.CSRF_DISABLED
        protect_auto.CSRF_DISABLED = True

    def tearDownPloneSite(self, portal: Any) -> None:
        protect_auto.CSRF_DISABLED = self._csrf_disabled


INTERAKTIV_TRANSLATION_FIXTURE = InteraktivTranslationLayer()

INTERAKTIV_TRANSLATION_INTEGRATION_TESTING = IntegrationTesting(
    bases=(INTERAKTIV_TRANSLATION_FIXTURE,),
    name="InteraktivTranslationLayer:IntegrationTesting",
)
INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(INTERAKTIV_TRANSLATION_FIXTURE, WSGI_SERVER_FIXTURE),
    name="InteraktivTranslationLayer:FunctionalTesting",
)


class InteraktivTranslationMultilingualLayer(InteraktivTranslationLayer):
    """The same site, with language root folders and a second language."""

    def __init__(self):
        super().__init__()
        self.products_to_import.append("plone.app.multilingual")

    def setUpPloneSite(self, portal):
        super().setUpPloneSite(portal)
        applyProfile(portal, "plone.app.multilingual:default")


INTERAKTIV_TRANSLATION_MULTILINGUAL_FIXTURE = InteraktivTranslationMultilingualLayer()

INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(INTERAKTIV_TRANSLATION_MULTILINGUAL_FIXTURE, WSGI_SERVER_FIXTURE),
    name="InteraktivTranslationMultilingualLayer:FunctionalTesting",
)


class InteraktivTranslationWorkingCopyLayer(InteraktivTranslationMultilingualLayer):
    """A multilingual site with plone.app.iterate installed, so an existing
    translation is checked out instead of overwritten."""

    def __init__(self):
        super().__init__()
        self.products_to_import.append("plone.app.iterate")

    def setUpPloneSite(self, portal):
        super().setUpPloneSite(portal)
        applyProfile(portal, "plone.app.iterate:default")


INTERAKTIV_TRANSLATION_WORKING_COPY_FIXTURE = InteraktivTranslationWorkingCopyLayer()

INTERAKTIV_TRANSLATION_WORKING_COPY_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(INTERAKTIV_TRANSLATION_WORKING_COPY_FIXTURE, WSGI_SERVER_FIXTURE),
    name="InteraktivTranslationWorkingCopyLayer:FunctionalTesting",
)


class TestCase(unittest.TestCase):
    layer: Any = None

    def setUp(self) -> None:
        self.app = self.layer["app"]
        self.portal = self.layer["portal"]
        self.request = self.layer["request"]
        setRoles(self.portal, TEST_USER_ID, ["Manager", "Site Administrator"])

    def get_installer(self) -> Any:
        return get_installer(self.portal, self.request)

    def get_view(self, view_name: str, context: Optional[Any] = None) -> Any:
        return getMultiAdapter((context or self.portal, self.request), name=view_name)


# A requests session rooted at the site — see docs/architecture.md on why it is
# not plone.restapi's.
class RelativeSession(requests.Session):
    def __init__(self, base_url: str, test=None) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.test = test

    def request(self, method, url, *args, **kwargs):
        return super().request(method, f"{self.base_url}{url}", *args, **kwargs)
