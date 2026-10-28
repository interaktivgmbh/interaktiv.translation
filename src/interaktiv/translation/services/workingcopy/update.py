from typing import Any

import plone.api as api
from plone.app.iterate.interfaces import ICheckinCheckoutPolicy
from plone.protect.interfaces import IDisableCSRFProtection
from plone.restapi.services.workingcopy.update import UpdateWorkingCopy as StockUpdateWorkingCopy
from zope.component import getMultiAdapter
from zope.interface import alsoProvides

from interaktiv.translation.storage import get_translation_marker


class UpdateWorkingCopy(StockUpdateWorkingCopy):
    """override to set a custom message"""

    def reply(self) -> Any:
        alsoProvides(self.request, IDisableCSRFProtection)

        policy = ICheckinCheckoutPolicy(self.context)
        working_copy = policy.getWorkingCopy()

        if working_copy is None:
            return self._error(400, "Bad Request", "There is no working copy to check in.")

        if not policy.getBaseline():
            # We are on the baseline; the policy that can check in is the
            # working copy's.
            policy = ICheckinCheckoutPolicy(working_copy)

        control = getMultiAdapter((working_copy, self.request), name="iterate_control")
        if not control.checkin_allowed():
            membership_tool = api.portal.get_tool("portal_membership")
            if bool(membership_tool.isAnonymousUser()):
                return self._error(401, "Not authenticated", "Checkin not allowed")

            return self._error(403, "Not authorized", "Checkin not allowed")

        message = "Checked in" if get_translation_marker(working_copy) else ""
        policy.checkin(message)

        return self.reply_no_content()
