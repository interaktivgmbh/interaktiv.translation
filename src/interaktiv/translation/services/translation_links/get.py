from typing import Any, Dict

from Acquisition import aq_base
from plone.restapi.services import Service

from interaktiv.translation.helpers.links import LINK_STATUSES, check_links


class TranslationLinksGet(Service):
    """The links of the content as it is now, each with how it stands to the
    language of the content: what an editor goes through after a translation."""

    def reply(self) -> Dict[str, Any]:
        items = check_links(self.context)
        statuses = [item["status"] for item in items]

        return {
            "@id": f"{self.context.absolute_url()}/@translation-links",
            "language": getattr(aq_base(self.context), "language", None) or None,
            "items": items,
            "summary": {status: statuses.count(status) for status in LINK_STATUSES},
        }
