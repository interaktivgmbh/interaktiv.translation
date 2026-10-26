from plone.schema import JSONField
from plone.supermodel import model
from zope import schema
from zope.interface import Interface

from interaktiv.translation import _
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
DEFAULT_COPY_FIELDS = ["image", "file"]


class ITranslationSettings(Interface):

    model.fieldset(
        'provider_options',
        label=_("Translation Service"),
        fields=['provider', 'api_key', 'api_url']
    )

    provider = schema.Choice(
        title=_("Translation service"),
        description=_("Which service translates. Only DeepL ships with this add-on."),
        vocabulary="interaktiv.translation.Providers",
        default="deepl",
        required=False,
    )

    api_key = schema.Password(
        title=_("DeepL API key"),
        description=_(
            "The key from your DeepL account. A free key ends in ':fx' and is sent to "
            "the free endpoint; anything else goes to the pro one."
        ),
        required=False,
    )

    api_url = schema.TextLine(
        title=_("DeepL API URL"),
        description=_("Only for a proxy or a self-hosted endpoint. Empty means the host that matches the key."),
        required=False,
    )

    model.fieldset(
        'translation_metadata_field_selection',
        label=_("Metadata Field Selection"),
        fields=[
            'metadata_selection',
        ]
    )

    metadata_selection = JSONField(
        title=_("Fields per content type"),
        description=_(
            "Sets per content type which fields go along into the translation. Only fields "
            "filled in on the page count. Whether a field is translated or taken over as it "
            "is follows from the kind of field; a field with values in the metadata mapping "
            "goes through the mapping."
        ),
#        schema=METADATA_MAPPING_JSON_SCHEMA,
        widget="translation_metadata_selection",
        default={},
        missing_value={},
        required=False,
    )

    model.fieldset(
        'translation_metadata_mapping',
        label=_("Metadata Mapping"),
        fields=[
            'metadata_mapping_table',
        ]
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
        'translation_advanced_settings',
        label=_("Advanced Settings"),
        fields=[
            'target_languages',
            'translate_fields',
            'copy_fields',
            'link_fields',
            'block_link_fields',
            'block_text_keys',
            'excluded_types',
        ]
    )

    target_languages = schema.List(
        title=_("Offered target languages"),
        description=_(
            "The site languages an editor may translate into. A language left out does not "
            "show in the translation menu. Empty offers every site language."
        ),
        value_type=schema.Choice(vocabulary="plone.app.vocabularies.SupportedContentLanguages"),
        default=[],
        missing_value=[],
        required=False,
    )

    translate_fields = schema.List(
        title=_("Translated fields"),
        description=_("The content fields the action translates, in this order."),
        value_type=schema.TextLine(),
        default=["title", "description", "text", "blocks"],
        missing_value=[],
        required=False,
    )

    copy_fields = schema.List(
        title=_("Fields carried over unchanged"),
        description=_(
            "Fields of the content whose values the translation takes over as they are, "
            "neither translated nor mapped — keywords that are codes, a project number. "
            "Named as the object stores them, one per line (e.g. subject, rights, image). "
            "Only text, numbers, dates, lists of them, and files and images, which the "
            "translation gets a copy of; editors may change the values afterwards."
        ),
        value_type=schema.TextLine(),
        default=DEFAULT_COPY_FIELDS,
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
        description=_(
            "Content of these types is never offered for machine translation."
        ),
        value_type=schema.TextLine(),
        default=DEFAULT_EXCLUDED_TYPES,
        missing_value=[],
        required=False,
    )

