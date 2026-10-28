from plone.autoform import directives
from plone.schema import JSONField
from plone.supermodel import model
from zope import schema
from zope.interface import Interface

from interaktiv.translation import _
from interaktiv.translation.helpers.field_selection import (
    ALWAYS_FIELDS,
    COPIED_FIELDS,
    EXCLUDED_FIELDS,
    METADATA_SELECTION_JSON_SCHEMA,
)
from interaktiv.translation.helpers.metadata import METADATA_MAPPING_JSON_SCHEMA, validate_metadata_mapping

DEFAULT_BLOCK_TEXT_KEYS = [
    "title",
    "description",
    "text",
    "plaintext",
    "value",
    "label",
    "alt",
    "caption",
    "quote",
    "buttonText",
    "subtitle",
    "headline",
    "heading",
    "eyebrow",
    "lede",
    "body",
    "summary",
]
DEFAULT_BLOCK_LINK_FIELDS = ["url", "href", "preview_image", "@id"]
DEFAULT_EXCLUDED_TYPES = []


class ITranslationSettings(Interface):
    model.fieldset(
        "provider_options",
        label=_("Translation Service"),
        fields=["target_languages", "provider", "api_url", "api_key"],
    )

    target_languages = schema.List(
        title=_("Offered target languages"),
        description=_(
            "The site languages an editor may translate into. A language left out does not "
            "show in the translation menu. Empty offers every site language."
        ),
        value_type=schema.Choice(vocabulary="interaktiv.translation.SiteLanguages"),
        default=[],
        missing_value=[],
        required=False,
    )

    provider = schema.Choice(
        title=_("Translation service"),
        description=_("Which service translates. Only DeepL ships with this add-on."),
        vocabulary="interaktiv.translation.Providers",
        default="deepl",
        required=False,
    )

    api_url = schema.TextLine(
        title=_("DeepL API URL"),
        description=_("Only for a proxy or a self-hosted endpoint. Empty means the host that matches the key."),
        required=False,
    )

    # the key never goes to the browser, see controlpanels/api_key.py; its widget
    # tests the connection
    directives.widget("api_key", frontendOptions={"widget": "translation_api_key"})
    api_key = schema.Password(
        title=_("DeepL API key"),
        description=_(
            "Found in the DeepL account under “Account → API keys”. Stored encrypted and only used on the server."
        ),
        required=False,
    )

    model.fieldset(
        "translation_metadata_field_selection",
        label=_("Fields per content type"),
        fields=[
            "metadata_selection",
        ],
    )

    metadata_selection = JSONField(
        title=_("Fields per content type"),
        description=_(
            "Sets per content type which fields go along into the translation. Only fields "
            "filled in on the page count. Whether a field is translated or taken over as it "
            "is follows from the kind of field; a field with values in the metadata mapping "
            "goes through the mapping."
        ),
        schema=METADATA_SELECTION_JSON_SCHEMA,
        widget="translation_metadata_selection",
        default={},
        missing_value={},
        required=False,
    )

    model.fieldset(
        "translation_metadata_mapping",
        label=_("Metadata Mapping"),
        fields=[
            "metadata_mapping_table",
        ],
    )

    metadata_mapping_table = JSONField(
        title=_("Metadata mapping"),
        description=_(
            "Fixed translations for the values of metadata fields, per field one row per "
            "value with one entry per language. An empty or missing language keeps the "
            "value of the source language."
        ),
        schema=METADATA_MAPPING_JSON_SCHEMA,
        widget="translation_metadata_mapping",
        default={},
        missing_value={},
        constraint=validate_metadata_mapping,
        required=False,
    )

    model.fieldset(
        "translation_advanced_settings",
        label=_("Advanced Settings"),
        fields=[
            "excluded_fields",
            "always_fields",
            "copied_fields",
            "link_fields",
            "block_link_fields",
            "block_text_keys",
            "excluded_types",
        ],
    )

    excluded_fields = schema.List(
        title=_("Fields never translated"),
        description=_(
            "Fields that never go into a translation and are not listed per content type: "
            "they belong to the object, not to its language. Named as in the schema, one per "
            "line, for every content type."
        ),
        value_type=schema.TextLine(),
        default=list(EXCLUDED_FIELDS),
        missing_value=[],
        required=False,
    )

    always_fields = schema.List(
        title=_("Fields always translated"),
        description=_(
            "Fields that always go into a translation and cannot be left out per content "
            "type; they come first in the list. Named as in the schema, one per line. The "
            "main field of a type, as the image of an image, always goes along too."
        ),
        value_type=schema.TextLine(),
        default=list(ALWAYS_FIELDS),
        missing_value=[],
        required=False,
    )

    copied_fields = schema.List(
        title=_("Fields taken over unchanged"),
        description=_(
            "Fields taken over as they are where their kind would have them translated: "
            "text that is no prose, as an address or a project number. Named as in the "
            "schema, one per line, for every content type. A field still only goes along "
            "when it is chosen for the content type."
        ),
        value_type=schema.TextLine(),
        default=list(COPIED_FIELDS),
        missing_value=[],
        required=False,
    )

    link_fields = schema.List(
        title=_("Link fields of the content type"),
        description=_(
            "Fields of your content types that hold a link, one per line — a project "
            "link, a partner link. Links inside blocks are found on their own; these "
            "are the ones that sit on the object itself."
        ),
        value_type=schema.TextLine(),
        default=[],
        missing_value=[],
        required=False,
    )

    block_link_fields = schema.List(
        title=_("Link keys inside blocks"),
        description=_(
            "Which keys of a block hold a link to other content. The default is what "
            "Plone itself watches for link integrity, plus the key an object browser "
            "writes. A block type of your own may need its own keys named here."
        ),
        value_type=schema.TextLine(),
        default=DEFAULT_BLOCK_LINK_FIELDS,
        missing_value=[],
        required=False,
    )

    block_text_keys = schema.List(
        title=_("Prose keys inside blocks"),
        description=_(
            "Which keys of a block hold text to translate. Only the key tells a sentence "
            "apart from a token the front end reads, so a block type of your own needs its "
            "own keys named here, or its text stays in the source language."
        ),
        value_type=schema.TextLine(),
        default=DEFAULT_BLOCK_TEXT_KEYS,
        missing_value=[],
        required=False,
    )

    excluded_types = schema.List(
        title=_("Content types not translated by machine"),
        description=_("Content of these types is never offered for machine translation."),
        value_type=schema.Choice(vocabulary="interaktiv.translation.ContentTypes"),
        default=DEFAULT_EXCLUDED_TYPES,
        missing_value=[],
        required=False,
    )
