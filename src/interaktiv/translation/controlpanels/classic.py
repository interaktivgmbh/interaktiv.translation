from typing import Any, Dict

from plone.app.registry.browser import controlpanel
from z3c.form.interfaces import NOT_CHANGED

from interaktiv.translation import _
from interaktiv.translation.registry.translation import ITranslationSettings


class TranslationSettingsForm(controlpanel.RegistryEditForm):
    schema = ITranslationSettings
    label = _("Translation")
    description = _("The service that translates content, and what it may translate.")

    def applyChanges(self, data: Dict[str, Any]) -> Any:
        # a password field shows no value: left empty, the stored key stays
        if not data.get("api_key"):
            data["api_key"] = NOT_CHANGED

        return super().applyChanges(data)


class TranslationSettingsControlPanel(controlpanel.ControlPanelFormWrapper):
    form = TranslationSettingsForm
