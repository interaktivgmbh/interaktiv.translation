"""The API key never goes to the browser."""

from typing import Any

from plone.dexterity.interfaces import IDexterityContent
from plone.restapi.deserializer.dxfields import TextLineFieldDeserializer
from plone.restapi.interfaces import IFieldDeserializer, IFieldSerializer
from plone.restapi.serializer.dxfields import DefaultFieldSerializer
from zope.component import adapter
from zope.interface import implementer
from zope.schema.interfaces import IPassword

from interaktiv.translation.interfaces import IInteraktivTranslationBrowserLayer
from interaktiv.translation.registry.translation import ITranslationSettings
from interaktiv.translation.settings import settings

# what the form shows for a stored key
API_KEY_PLACEHOLDER = "••••••••"


def is_api_key(field: Any) -> bool:
    return field.interface is ITranslationSettings and field.getName() == "api_key"


@implementer(IFieldSerializer)
@adapter(IPassword, ITranslationSettings, IInteraktivTranslationBrowserLayer)
class ApiKeySerializer(DefaultFieldSerializer):
    def __call__(self) -> Any:
        if not is_api_key(self.field):
            return super().__call__()

        return API_KEY_PLACEHOLDER if self.get_value() else None


# a control panel deserializes on a stand-in content, not on the settings
@implementer(IFieldDeserializer)
@adapter(IPassword, IDexterityContent, IInteraktivTranslationBrowserLayer)
class ApiKeyDeserializer(TextLineFieldDeserializer):
    def __call__(self, value: Any) -> Any:
        if is_api_key(self.field) and value == API_KEY_PLACEHOLDER:
            # unchanged in the form: the stored key stays
            return settings().api_key or None

        return super().__call__(value)
