import plone.api as api
from plone.browserlayer.utils import registered_layers
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from interaktiv.translation import ADDON_DEPENDENCIES
from interaktiv.translation.interfaces import IInteraktivTranslationBrowserLayer
from interaktiv.translation.registry.translation import ITranslationSettings
from interaktiv.translation.testing import INTERAKTIV_TRANSLATION_INTEGRATION_TESTING, TestCase


class TestSetup(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING
    addon_name = "interaktiv.translation"

    def test_addon_installed(self):
        installer = self.get_installer()

        self.assertTrue(installer.is_product_installed(self.addon_name))

    def test_dependencies_are_installed(self):
        installer = self.get_installer()

        for addon_name in ADDON_DEPENDENCIES:
            self.assertTrue(
                installer.is_product_installed(addon_name),
                msg="Add-on '{}' missing".format(addon_name),
            )


class TestUninstall(TestCase):
    layer = INTERAKTIV_TRANSLATION_INTEGRATION_TESTING
    addon_name = "interaktiv.translation"

    def setUp(self):
        super().setUp()
        with api.env.adopt_roles(["Manager"]):
            self.get_installer().uninstall_product(self.addon_name)

    def test_addon_uninstalled(self):
        self.assertFalse(self.get_installer().is_product_installed(self.addon_name))

    def test_browserlayer_removed(self):
        self.assertNotIn(IInteraktivTranslationBrowserLayer, registered_layers())

    def test_registry_records_removed(self):
        records = getUtility(IRegistry).records

        for name in ITranslationSettings.names():
            self.assertNotIn(f"{ITranslationSettings.__identifier__}.{name}", records)

    def test_action_removed(self):
        self.assertNotIn("translate", api.portal.get_tool("portal_actions").object_buttons.objectIds())

    def test_controlpanel_removed(self):
        configlets = [configlet.getId() for configlet in api.portal.get_tool("portal_controlpanel").listActions()]

        self.assertNotIn("translation_controlpanel", configlets)
