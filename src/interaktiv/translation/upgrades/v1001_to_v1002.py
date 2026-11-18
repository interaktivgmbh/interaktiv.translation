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
    """Turns the list of fields per content type into ``{field_id: mode}``."""
    registry = getUtility(IRegistry)
    if SELECTION_RECORD not in registry.records:
        return

    selection = registry.records[SELECTION_RECORD].value
    if not isinstance(selection, dict):
        return

    # the record's old field refuses the new form: the registry step renews it
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
