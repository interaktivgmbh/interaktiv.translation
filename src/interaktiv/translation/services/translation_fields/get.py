from typing import Any, Dict

from plone.restapi.services import Service
from zope.i18n import translate

from interaktiv.translation.helpers.field_selection import selectable_types, get_listed_fields
from interaktiv.translation.settings import settings


class TranslationFieldsGet(Service):
    """The content types an editor adds, each with its fields and how the translation treats them."""

    def reply(self) -> Dict[str, Any]:
        current = settings()
        mapped = current.mapped_fields
        rules = current.field_rules

        return {
            "types": [
                {
                    "id": portal_type,
                    "title": translate(title, context=self.request),
                    "fields": get_listed_fields(portal_type, self.context, self.request, mapped, rules),
                }
                for portal_type, title in selectable_types(self.context, current.excluded_types)
            ]
        }
