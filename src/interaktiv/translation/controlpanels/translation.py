from plone.restapi.controlpanels import RegistryConfigletPanel
from zope.component import adapter
from zope.interface import Interface

from interaktiv.translation.interfaces import IInteraktivTranslationBrowserLayer
from interaktiv.translation.registry.translation import ITranslationSettings


@adapter(Interface, IInteraktivTranslationBrowserLayer)
class TranslationControlpanel(RegistryConfigletPanel):
    schema = ITranslationSettings
    configlet_id = "translation_controlpanel"
    configlet_category_id = "Products"
    schema_prefix = None
