from typing import Any, Dict

from plone.restapi.services import Service
from zope.i18n import translate

from interaktiv.translation.helpers.field_selection import selectable_types, type_fields
from interaktiv.translation.settings import settings


class TranslationFieldsGet(Service):
    """The content types an editor adds, each with its fields and how the translation treats them."""

    def reply(self) -> Dict[str, Any]:
        current = settings()
        mapped = current.mapped_fields

        return {
            "types": [
                {
                    "id": portal_type,
                    "title": translate(title, context=self.request),
                    "fields": type_fields(portal_type, self.context, self.request, mapped),
                }
                for portal_type, title in selectable_types(self.context, current.excluded_types)
            ]
        }
