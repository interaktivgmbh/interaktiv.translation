from typing import Any, Dict

from AccessControl import getSecurityManager
from plone.restapi.interfaces import IExpandableElement
from plone.restapi.services import Service
from zope.annotation.interfaces import IAnnotations
from zope.component import adapter
from zope.interface import Interface, implementer

from interaktiv.translation.interfaces import IInteraktivTranslationBrowserLayer
from interaktiv.translation.storage import MACHINE_TRANSLATION_KEY, translation_status


@implementer(IExpandableElement)
@adapter(Interface, IInteraktivTranslationBrowserLayer)
class MachineTranslationInfo:
    def __init__(self, context: Any, request: Any) -> None:
        self.context = context
        self.request = request

    def __call__(self, expand: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {"machine_translation": {"@id": f"{self.context.absolute_url()}/@machine-translation"}}
        if not expand:
            return result

        # edit permission for Reading status
        has_permission = getSecurityManager().checkPermission("Modify portal content", self.context)
        if not has_permission:
            return result

        annotations = IAnnotations(self.context, None)
        marker = annotations.get(MACHINE_TRANSLATION_KEY) if annotations is not None else None
        info: Dict[str, Any] = {
            "machine_translated": marker is not None,
            "status": translation_status(self.context),
        }
        if marker:
            info.update(marker)
        result["machine_translation"].update(info)

        return result


class MachineTranslationInfoGet(Service):
    def reply(self) -> Dict[str, Any]:
        return MachineTranslationInfo(self.context, self.request)(expand=True)["machine_translation"]
