from plone.app.registry.browser import controlpanel

from interaktiv.translation import _
from interaktiv.translation.registry.translation import ITranslationSettings


class TranslationSettingsForm(controlpanel.RegistryEditForm):
    schema = ITranslationSettings
    label = _("Translation")
    description = _("The service that translates content, and what it may translate.")


class TranslationSettingsControlPanel(controlpanel.ControlPanelFormWrapper):
    form = TranslationSettingsForm
