from typing import Any, Dict, Optional

from plone import api
from plone.registry.interfaces import IRegistry
from Products.GenericSetup.tool import SetupTool
from zope.component import getUtility

from interaktiv.translation import logger
from interaktiv.translation.helpers.field_selection import get_suggested_modes
from interaktiv.translation.registry.translation import ITranslationSettings
from interaktiv.translation.settings import settings

SELECTION_RECORD = f"{ITranslationSettings.__identifier__}.metadata_selection"


# noinspection PyUnusedLocal
def upgrade(site_setup: Optional[SetupTool] = None) -> None:
    """The fields per content type name how each field goes along: a list of fields
    becomes ``{field_id: mode}``, with the mode the field had by its kind."""
    registry = getUtility(IRegistry)
    if SELECTION_RECORD not in registry.records:
        return

    selection = registry.records[SELECTION_RECORD].value
    if not isinstance(selection, dict):
        return

    # the registry step gives the record the field of today: the one it has
    # refuses a field naming how it goes along
    setup_tool = site_setup or api.portal.get_tool("portal_setup")
    setup_tool.runImportStepFromProfile(
        "profile-interaktiv.translation:default", "plone.app.registry", run_dependencies=False
    )

    rules = settings().field_rules
    upgraded: Dict[str, Any] = {}
    for portal_type, chosen in selection.items():
        if not isinstance(chosen, (list, tuple)):
            # chosen with modes already
            upgraded[portal_type] = chosen
            continue

        modes = get_suggested_modes(portal_type, chosen, rules)
        # what always goes along was listed too and needs no choice
        dropped = [name for name in chosen if name not in modes]
        if dropped:
            logger.info("Fields per content type: %s of %s need no choice or are gone.", dropped, portal_type)
        upgraded[portal_type] = modes

    registry[SELECTION_RECORD] = upgraded
