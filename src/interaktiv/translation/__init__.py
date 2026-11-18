import logging

from zope.i18nmessageid import MessageFactory

_ = MessageFactory("interaktiv.translation")
logger = logging.getLogger("interaktiv.translation")

# keep in sync with the dependencies in profiles/default/metadata.xml
ADDON_DEPENDENCIES = {
    "plone.restapi": "profile-plone.restapi:default",
}
