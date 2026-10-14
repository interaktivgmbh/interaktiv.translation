from Products.CMFPlone.Portal import PloneSite


def post_install(context: PloneSite) -> None:
    """Run after the default profile is installed."""


def uninstall(context: PloneSite) -> None:
    """Run after the uninstall profile is applied."""
