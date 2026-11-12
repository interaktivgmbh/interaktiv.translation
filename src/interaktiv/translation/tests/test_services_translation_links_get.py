import copy

import plone.api as api
import transaction
from plone.app.multilingual.interfaces import ITranslationManager
from plone.app.testing import SITE_OWNER_NAME, SITE_OWNER_PASSWORD, TEST_USER_ID, setRoles
from z3c.relationfield import RelationValue
from zope.component import getUtility
from zope.intid.interfaces import IIntIds

from interaktiv.translation.helpers.links import check_links
from interaktiv.translation.testing import (
    INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING,
    INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING,
    RelativeSession,
    TestCase,
)


def _slate_link(url, text="Text A"):
    return {"@type": "slate", "value": [{"type": "link", "data": {"url": url}, "children": [{"text": text}]}]}


class TestTranslationLinksGet(TestCase):
    """The links of the content as it is now, each with how it stands to the
    language of the content."""

    layer = INTERAKTIV_TRANSLATION_MULTILINGUAL_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        self.page_a = api.content.create(container=self.portal["de"], type="Document", id="page-a", title="Titel A")
        self.page_b = api.content.create(container=self.portal["de"], type="Document", id="page-b", title="Titel B")
        self.page_c = api.content.create(container=self.portal["en"], type="Document", id="page-c", title="Title C")
        self.image = api.content.create(container=self.portal["de"], type="Image", id="image-a", title="Image A")
        self.shared = api.content.create(container=self.portal, type="File", id="file-a", title="File A")
        # the content checked: an English page
        self.page = api.content.create(container=self.portal["en"], type="Document", id="page-d", title="Title D")
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        transaction.commit()

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def _set_blocks(self, **blocks):
        self.page.blocks = blocks
        transaction.commit()

    def _get(self, path="/en/page-d"):
        return self.api_session.get(f"{path}/@translation-links")

    def _items(self):
        return self._get().json()["items"]

    def test_get__answers_the_language_and_no_links_for_a_page_without_any(self):
        # do it
        response = self._get()

        # postcondition
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["@id"], f"{self.page.absolute_url()}/@translation-links")
        self.assertEqual(body["language"], "en")
        self.assertEqual(body["items"], [])
        self.assertEqual(
            body["summary"],
            {"translated": 0, "translatable": 0, "untranslated": 0, "independent": 0, "broken": 0, "external": 0},
        )

    def test_get__link_into_the_language_of_the_page_is_translated(self):
        # setup
        self._set_blocks(b1=_slate_link("/en/page-c"))

        # postcondition
        self.assertEqual(
            self._items(),
            [{"text": "Text A", "kind": "link", "status": "translated", "url": "/en/page-c", "translation": None}],
        )

    def test_get__link_into_another_language_without_translation_is_untranslated(self):
        # setup
        self._set_blocks(b1=_slate_link("/de/page-a"))

        # postcondition
        self.assertEqual(
            self._items(),
            [{"text": "Text A", "kind": "link", "status": "untranslated", "url": "/de/page-a", "translation": None}],
        )

    def test_get__link_becomes_translatable_once_its_target_is_translated(self):
        # setup — the link was left alone, its target got a translation later
        self._set_blocks(b1=_slate_link("/de/page-a"))
        self.assertEqual(self._items()[0]["status"], "untranslated")
        manager = ITranslationManager(self.page_a)
        manager.add_translation("en")
        translation = manager.get_translation("en")
        transaction.commit()

        # do it
        items = self._items()

        # postcondition — with where it could point instead
        self.assertEqual(items[0]["status"], "translatable")
        self.assertEqual(items[0]["url"], "/de/page-a")
        self.assertEqual(items[0]["translation"], translation.absolute_url())

    def test_get__link_to_content_without_language_is_independent(self):
        # setup
        self._set_blocks(b1=_slate_link("/file-a"))

        # postcondition
        items = self._items()
        self.assertEqual(items[0]["status"], "independent")
        self.assertEqual(items[0]["kind"], "file")

    def test_get__link_to_nothing_is_broken(self):
        # setup
        self._set_blocks(b1=_slate_link("/de/page-missing"))

        # postcondition
        self.assertEqual(self._items()[0]["status"], "broken")

    def test_get__link_out_of_the_site_is_external(self):
        # setup
        self._set_blocks(b1=_slate_link("https://example.org/page-a"))

        # postcondition
        self.assertEqual(
            self._items(),
            [
                {
                    "text": "Text A",
                    "kind": "link",
                    "status": "external",
                    "url": "https://example.org/page-a",
                    "translation": None,
                }
            ],
        )

    def test_get__mail_addresses_and_anchors_are_no_links_to_check(self):
        # setup
        self._set_blocks(b1=_slate_link("mailto:a@example.org"), b2=_slate_link("#anchor-a"))

        # postcondition
        self.assertEqual(self._items(), [])

    def test_get__image_block_is_an_image_named_by_its_alt(self):
        # setup
        self._set_blocks(b1={"@type": "image", "url": "/de/image-a", "alt": "Alt A"})

        # postcondition
        items = self._items()
        self.assertEqual(items[0]["kind"], "image")
        self.assertEqual(items[0]["text"], "Alt A")
        self.assertEqual(items[0]["status"], "untranslated")

    def test_get__references_are_links_too(self):
        # setup
        intids = getUtility(IIntIds)
        self.page.relatedItems = [RelationValue(intids.getId(self.page_b)), RelationValue(intids.getId(self.page_c))]
        transaction.commit()

        # postcondition
        self.assertEqual(
            [(item["text"], item["url"], item["status"]) for item in self._items()],
            [
                ("relatedItems", self.page_b.absolute_url(), "untranslated"),
                ("relatedItems", self.page_c.absolute_url(), "translated"),
            ],
        )

    def test_get__counts_the_links_by_status(self):
        # setup
        self._set_blocks(
            b1=_slate_link("/en/page-c"),
            b2=_slate_link("/de/page-a"),
            b3=_slate_link("/de/page-b"),
            b4=_slate_link("https://example.org/page-a"),
        )

        # postcondition
        self.assertEqual(
            self._get().json()["summary"],
            {"translated": 1, "translatable": 0, "untranslated": 2, "independent": 0, "broken": 0, "external": 1},
        )

    def test_get__changes_nothing(self):
        # setup — a link that could be pointed at a translation
        ITranslationManager(self.page_a).add_translation("en")
        self._set_blocks(b1=_slate_link("/de/page-a"))
        before = copy.deepcopy(self.page.blocks)

        # do it
        self._get()
        check_links(self.page)

        # postcondition
        transaction.begin()
        self.assertEqual(self.portal["en"]["page-d"].blocks, before)

    def test_get__needs_the_permission_to_edit(self):
        # setup
        api.user.create(email="user-a@example.org", username="user-a", password="secret-secret")
        transaction.commit()
        self.api_session.auth = ("user-a", "secret-secret")

        # postcondition
        self.assertEqual(self._get().status_code, 401)


class TestTranslationLinksGetWithoutLanguages(TestCase):
    """A site of one language: there is no other language a link could lead into."""

    layer = INTERAKTIV_TRANSLATION_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        super().setUp()
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        api.content.create(container=self.portal, type="Document", id="page-a", title="Titel A")
        page = api.content.create(container=self.portal, type="Document", id="page-b", title="Titel B")
        page.blocks = {"b1": _slate_link("/page-a"), "b2": _slate_link("/page-missing")}
        self.api_session = RelativeSession(self.portal.absolute_url(), test=self)
        self.api_session.headers.update({"Accept": "application/json"})
        self.api_session.auth = (SITE_OWNER_NAME, SITE_OWNER_PASSWORD)
        transaction.commit()

    def tearDown(self) -> None:
        self.api_session.close()
        super().tearDown()

    def test_get__answers_for_a_site_without_translations(self):
        # do it
        response = self.api_session.get("/page-b/@translation-links")

        # postcondition
        self.assertEqual(response.status_code, 200)
        statuses = [item["status"] for item in response.json()["items"]]
        self.assertEqual(statuses[1], "broken")
        # the content has no language of its own here
        self.assertEqual(statuses[0], "independent")
