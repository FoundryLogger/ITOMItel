"""Stories tests use invented articles shaped like WordPress REST answers."""
import json
import tempfile
import unittest
from pathlib import Path

from totem import blog, text
from totem.app import App, HEIGHT
from totem.blog import Post, WordPressClient
from totem.text import html_to_text


def rest_post(pid, title, date, content="", link=None, author=None):
    post = {"id": pid, "date": date, "title": {"rendered": title},
            "link": link or f"https://example.org/{pid}/",
            "content": {"rendered": content}}
    if author:                                       # what _embed=author adds
        post["_embedded"] = {"author": [{"id": 5, "name": author}]}
    return post


POSTS = [rest_post(3, "Perch&eacute; l&#8217;infinito &#8211; parte tre", "2026-03-06T10:00:00", author="Fj&oacute;na Cakalli", content=
                   "<h2>Un titolo<br>su due righe</h2><p>Primo paragrafo, &egrave; lungo " + "parola " * 260 +
                   "</p><ul><li>uno</li><li>due</li></ul><iframe src='x'>video</iframe>"
                   "<audio controls><source src='a.mp3'></audio><p>Fine.</p>"),
         rest_post(2, "Secondo articolo", "2026-02-03T10:00:00", "<p>Breve.</p>"),
         rest_post(1, "Primo", "2025-12-30T10:00:00", "")]


def fake_fetch(calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if "/categories?" in url:
            return [{"id": 8}]
        if "/posts/" in url:
            pid = int(url.split("/posts/")[1].split("?")[0])
            return next(p for p in POSTS if p["id"] == pid)
        return [{k: p[k] for k in ("id", "date", "title", "link")} for p in POSTS]
    return fetch


def epic(fetch, category="storie"):
    """A client set up like Storie EPIC (one category, newest first, with dates)."""
    return WordPressClient("https://example.org", category, fetch=fetch,
                           list_title="STORIE EPIC", detail_title="STORIA", index_name="Storie",
                           show_author=True)


class FakeShop:
    def collections(self):
        return []

    def refresh(self):
        pass


class TextTests(unittest.TestCase):
    def test_headings_become_capitals_set_apart_and_embeds_are_dropped(self):
        out = html_to_text("<p>a</p><h2>Un titolo</h2><p>b</p><iframe>NO</iframe><audio>NO</audio>", headings=True)
        self.assertEqual(out, "a\n\nUN TITOLO\n\nb")

    def test_headings_are_left_alone_by_default(self):
        self.assertEqual(html_to_text("<h2>Un titolo</h2><p>b</p>"), "Un titolo\n\nb")

    def test_lists_and_entities(self):
        self.assertEqual(html_to_text("<p>l&#8217;uno &amp; l&egrave;</p><ul><li>x</li><li>y</li></ul>"),
                         "l’uno & lè\n\n- x\n- y")


class PostTests(unittest.TestCase):
    def test_dates(self):
        p = Post(1, "2026-03-06T10:00:00", "t", "l")
        self.assertEqual((p.short_date, p.long_date), ("06/03/26", "6 marzo 2026"))


class ClientTests(unittest.TestCase):
    def client(self, **kw):
        return WordPressClient("https://example.org/", "storie", fetch=fake_fetch(kw.pop("calls", None)), **kw)

    def test_posts_are_listed_newest_first_with_clean_titles_and_no_text(self):
        posts = self.client().posts()
        self.assertEqual([p.id for p in posts], [3, 2, 1])
        self.assertEqual(posts[0].title, "Perché l’infinito – parte tre")
        self.assertEqual(posts[0].text, "")

    def test_an_article_comes_with_its_text(self):
        art = self.client().article(3)
        self.assertIn("UN TITOLO\nSU DUE RIGHE", art.text)
        self.assertIn("- uno\n- due", art.text)
        self.assertNotIn("video", art.text)

    def test_answers_are_cached_in_memory(self):
        calls = []
        c = self.client(calls=calls)
        c.posts(); c.posts()
        self.assertEqual(len(calls), 2)                       # category + posts, once each

    def test_it_pages_through_long_categories(self):
        old, blog.PAGE_LIMIT = blog.PAGE_LIMIT, 2
        self.addCleanup(setattr, blog, "PAGE_LIMIT", old)
        five = [rest_post(i, f"Articolo {i}", f"2026-01-0{i}T10:00:00") for i in range(5, 0, -1)]
        asked = []

        def fetch(url):
            if "/categories?" in url:
                return [{"id": 8}]
            page = int(url.split("&page=")[1].split("&")[0])
            asked.append(page)
            return five[(page - 1) * 2:page * 2]

        posts = WordPressClient("https://example.org", "storie", fetch=fetch).posts()
        self.assertEqual([p.id for p in posts], [5, 4, 3, 2, 1])
        self.assertEqual(asked, [1, 2, 3])

    def test_a_dead_network_falls_back_to_the_last_copy_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            WordPressClient("https://example.org", "storie", cache_dir=d, fetch=fake_fetch()).posts()
            def down(url):
                raise OSError("rete assente")
            offline = WordPressClient("https://example.org", "storie", cache_dir=d, fetch=down)
            self.assertEqual([p.id for p in offline.posts()], [3, 2, 1])

    def test_without_a_copy_the_error_is_raised(self):
        def down(url):
            raise OSError("rete assente")
        with self.assertRaises(OSError):
            epic(down).posts()

    def test_an_unknown_category_gives_an_empty_list(self):
        c = epic(lambda url: [], "boh")
        self.assertEqual(c.posts(), [])

    def test_domain_without_scheme_or_www(self):
        self.assertEqual(WordPressClient("https://www.example.org/", "s").domain, "example.org")


class ScreenTests(unittest.TestCase):
    def open_stories(self, width=80, client=None):
        app = App(FakeShop(), width=width, stories=client or epic(fake_fetch()),
                  loading_delay=5)
        app.key("6")
        return app

    def test_the_list_shows_titles_and_dates_and_the_source(self):
        screen = self.open_stories().screen()
        joined = "\n".join(screen)
        self.assertTrue(screen[0].startswith("STORIE EPIC"))
        self.assertTrue(any(r.rstrip().endswith("06/03/26") for r in screen))
        self.assertIn("fonte: example.org", joined)
        self.assertEqual({len(r) for r in screen}, {80})

    def test_opening_an_article_shows_title_date_text_and_link(self):
        app = self.open_stories()
        app.key("1")
        screen = app.screen()
        joined = "\n".join(screen)
        self.assertTrue(screen[0].startswith("STORIA"))
        self.assertIn("PERCHÉ L'INFINITO - PARTE TRE", joined)      # typographic marks become plain ones
        self.assertIn("6 marzo 2026", joined)
        self.assertIn("UN TITOLO", joined)
        self.assertIn("Fonte: example.org", joined)
        app.key("SEGUENTE")                                     # the link closes the article
        self.assertIn("example.org/3/", "\n".join(app.screen()))

    def test_a_long_article_is_paged_and_annul_goes_back_to_the_list(self):
        app = self.open_stories()
        app.key("1")
        self.assertGreater(app.view.pages(), 1)
        app.key("SEGUENTE")
        self.assertIn("2/", app.screen()[0])
        app.key("PRECEDENTE")
        app.key("PRECEDENTE")                                   # before the first page: back to the list
        self.assertTrue(app.screen()[0].startswith("STORIE EPIC"))
        app.key("ANNUL")
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_an_article_without_text_says_so(self):
        app = self.open_stories()
        app.key("3")                                            # "Primo" has empty content
        self.assertIn("Articolo non disponibile", "\n".join(app.screen()))

    def test_an_empty_category(self):
        app = self.open_stories(client=epic(lambda url: [], "boh"))
        self.assertIn("Nessun articolo trovato", "\n".join(app.screen()))

    def test_network_down_shows_the_error_screen(self):
        def down(url):
            raise OSError("rete assente")
        app = self.open_stories(client=epic(down))
        self.assertIn("Servizio non raggiungibile", "\n".join(app.screen()))
        app.key("INDICE")
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_layout_is_exact_in_ascii_mode_on_80_and_40_columns(self):
        text.set_ascii_only(True)
        self.addCleanup(text.set_ascii_only, False)
        for width in (80, 40):
            app = self.open_stories(width)
            shots = [app.screen()]
            app.key("1")
            shots += [app.screen()]
            app.key("SEGUENTE")
            shots += [app.screen()]
            for screen in shots:
                self.assertEqual(len(screen), HEIGHT)
                for row in screen:
                    self.assertEqual(len(row), width, row)
                    self.assertTrue(row.isascii(), row)

    def test_the_home_menu_has_the_entry_on_both_widths(self):
        for width in (80, 40):
            home = "\n".join(App(FakeShop(), width=width).screen())
            self.assertIn("6  Storie di EPIC" if width == 80 else "6  Storie EPIC", home)


# ---- a site where the reader first picks a category (Nerdvana: one per city) ----

CITIES = [{"id": 54, "name": "Londra", "slug": "londra", "count": 2},
          {"id": 5, "name": "New York", "slug": "newyork", "count": 1},
          {"id": 9, "name": "Vuota", "slug": "vuota", "count": 0},
          {"id": 7, "name": "L&#8217;Aquila", "slug": "laquila", "count": 1}]
GUIDES = {54: [rest_post(11, "Zeta Shop", "2026-07-14T10:00:00", "<p>Negozio di Londra.</p>"),
               rest_post(12, "&Egrave;ra Comics", "2026-07-14T10:00:00", "<p>Fumetti &egrave; altro.</p>")],
          5: [rest_post(21, "Alfa Store", "2026-07-14T10:00:00", "<p>Negozio di New York.</p>")],
          7: [rest_post(31, "Beta", "2026-07-14T10:00:00", "<p>x</p>")]}


def nerdvana_fetch(url):
    if "/categories?" in url and "slug=" in url:
        slug = url.split("slug=")[1].split("&")[0]
        return [{"id": c["id"]} for c in CITIES if c["slug"] == slug]
    if "/categories?" in url:
        return CITIES
    if "/posts/" in url:
        pid = int(url.split("/posts/")[1].split("?")[0])
        return next(p for posts in GUIDES.values() for p in posts if p["id"] == pid)
    cid = int(url.split("categories=")[1].split("&")[0])
    return [{k: p[k] for k in ("id", "date", "title", "link")} for p in GUIDES.get(cid, [])]


def nerdvana():
    return WordPressClient("https://example.net", None, fetch=nerdvana_fetch, sort="title",
                           show_dates=False, list_title="NERDVANA", detail_title="GUIDA",
                           index_name="Nerdvana")


class NerdvanaTests(unittest.TestCase):
    def open_menu(self, width=80):
        app = App(FakeShop(), width=width, nerdvana=nerdvana(), loading_delay=5)
        app.key("7")
        return app

    def test_categories_skip_empty_ones_and_are_sorted_a_z_with_clean_names(self):
        cats = nerdvana().categories()
        self.assertEqual([c.name for c in cats], ["Londra", "L’Aquila", "New York"])
        self.assertEqual([c.count for c in cats], [2, 1, 1])

    def test_posts_are_sorted_by_title_ignoring_accents_and_case(self):
        self.assertEqual([p.title for p in nerdvana().posts("londra")], ["Èra Comics", "Zeta Shop"])

    def test_menu_entry_shows_the_cities_with_their_counts(self):
        screen = self.open_menu().screen()
        self.assertTrue(screen[0].startswith("NERDVANA"))
        joined = "\n".join(screen)
        self.assertIn("Londra", joined)
        self.assertTrue(any(r.rstrip().endswith("(2)") for r in screen))
        self.assertNotIn("Vuota", joined)
        self.assertEqual({len(r) for r in screen}, {80})

    def test_a_city_lists_its_guides_without_dates(self):
        app = self.open_menu()
        app.key("1")                                            # Londra
        screen = app.screen()
        self.assertTrue(screen[0].startswith("NERDVANA - LONDRA"))
        rows = [r for r in screen if "Zeta Shop" in r or "Comics" in r]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.rstrip().endswith(("Zeta Shop", "Comics")) for r in rows))   # nothing on the right
        self.assertIn("fonte: example.net", "\n".join(screen))

    def test_a_guide_has_no_date_line_and_cites_the_source(self):
        app = self.open_menu()
        app.key("1")
        app.key("1")
        screen = app.screen()
        joined = "\n".join(screen)
        self.assertTrue(screen[0].startswith("GUIDA"))
        self.assertIn("ÈRA COMICS", joined)
        self.assertIn("Fumetti è altro.", joined)
        self.assertNotIn("luglio", joined)                       # the publication date means nothing here
        self.assertIn("Fonte: example.net", joined)

    def test_annul_walks_back_guide_city_list_menu(self):
        app = self.open_menu()
        app.key("1"); app.key("1")
        app.key("ANNUL")
        self.assertTrue(app.screen()[0].startswith("NERDVANA - LONDRA"))
        app.key("ANNUL")
        self.assertTrue(app.screen()[0].startswith("NERDVANA"))
        self.assertNotIn("LONDRA", app.screen()[0])
        app.key("ANNUL")
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_the_other_story_source_is_not_affected(self):
        app = App(FakeShop(), nerdvana=nerdvana(),
                  stories=epic(fake_fetch()), loading_delay=5)
        app.key("6")
        self.assertTrue(app.screen()[0].startswith("STORIE EPIC"))     # straight to the articles, with dates
        self.assertTrue(any(r.rstrip().endswith("06/03/26") for r in app.screen()))

    def test_layout_is_exact_in_ascii_mode_on_80_and_40_columns(self):
        text.set_ascii_only(True)
        self.addCleanup(text.set_ascii_only, False)
        for width in (80, 40):
            app = self.open_menu(width)
            shots = [app.screen()]
            app.key("1"); shots.append(app.screen())             # Londra
            app.key("1"); shots.append(app.screen())             # its first guide
            for screen in shots:
                self.assertEqual(len(screen), HEIGHT)
                for row in screen:
                    self.assertEqual(len(row), width, row)
                    self.assertTrue(row.isascii(), row)

    def test_home_menu_on_both_widths(self):
        self.assertIn("7  Guide Nerdvana", "\n".join(App(FakeShop()).screen()))
        self.assertIn("7  Nerdvana", "\n".join(App(FakeShop(), width=40).screen()))


# ---- the 0 key: back to the index of the site being read ----

BIG = [rest_post(i, f"Storia {i:02d}", f"2026-01-{i % 28 + 1:02d}T10:00:00", f"<p>Testo {i}.</p>")
       for i in range(30, 0, -1)]


def big_fetch(url):
    if "/categories?" in url:
        return [{"id": 8}]
    if "/posts/" in url:
        pid = int(url.split("/posts/")[1].split("?")[0])
        return next(p for p in BIG if p["id"] == pid)
    page = int(url.split("&page=")[1].split("&")[0])
    return [{k: p[k] for k in ("id", "date", "title", "link")} for p in BIG] if page == 1 else []


class IndexKeyTests(unittest.TestCase):
    def epic(self, width=80):
        app = App(FakeShop(), width=width, stories=epic(big_fetch), loading_delay=5)
        app.key("6")
        return app

    def nerdvana(self, width=80):
        app = App(FakeShop(), width=width, nerdvana=nerdvana(), loading_delay=5)
        app.key("7")
        return app

    def test_from_an_epic_article_zero_goes_back_to_the_list_at_its_first_page(self):
        app = self.epic()
        app.key("SEGUENTE")                                       # list page 2
        app.key("1")                                              # open an article from page 2
        self.assertTrue(app.screen()[0].startswith("STORIA"))
        app.key("0")
        screen = app.screen()
        self.assertTrue(screen[0].startswith("STORIE EPIC"))
        self.assertIn("1/2", screen[0])                           # the first of two pages
        self.assertIn("Storia 30", "\n".join(screen))
        app.key("ANNUL")                                          # one step back: the main menu
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_zero_on_the_epic_index_itself_goes_to_its_first_page_and_stays(self):
        app = self.epic()
        app.key("SEGUENTE")
        self.assertIn("2/2", app.screen()[0])
        app.key("0")
        self.assertIn("1/2", app.screen()[0])
        app.key("0")
        self.assertTrue(app.screen()[0].startswith("STORIE EPIC"))

    def test_the_key_line_names_the_zero_key_only_where_it_leads_somewhere(self):
        app = self.epic()
        self.assertNotIn("0=indice", app.screen()[-1])            # already on the index
        app.key("1")
        self.assertIn("0=indice Storie", app.screen()[-1])        # inside an article
        nv = self.nerdvana()
        self.assertNotIn("0=indice", nv.screen()[-1])             # the list of cities
        nv.key("1")
        self.assertIn("0=indice Nerdvana", nv.screen()[-1])       # a city's guides
        nv.key("1")
        self.assertIn("0=indice Nerdvana", nv.screen()[-1])       # a guide

    def test_from_a_nerdvana_guide_zero_goes_to_the_cities(self):
        app = self.nerdvana()
        app.key("1"); app.key("1")                                # Londra -> first guide
        self.assertTrue(app.screen()[0].startswith("GUIDA"))
        app.key("0")
        screen = app.screen()
        self.assertTrue(screen[0].startswith("NERDVANA"))
        self.assertNotIn("LONDRA", screen[0])
        self.assertIn("Londra", "\n".join(screen))               # the list of cities
        app.key("ANNUL")
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_from_a_cities_guide_list_zero_goes_to_the_cities(self):
        app = self.nerdvana()
        app.key("1")
        self.assertTrue(app.screen()[0].startswith("NERDVANA - LONDRA"))
        app.key("0")
        self.assertNotIn("LONDRA", app.screen()[0])

    def test_zero_does_not_disturb_the_other_sections(self):
        app = App(FakeShop(), loading_delay=5)
        app.key("1")                                              # the shop's categories: 0 is not a choice there
        before = app.screen()[0]
        app.key("0")
        self.assertEqual(app.screen()[0], before)

    def test_key_lines_fit_on_80_and_40_columns(self):
        for width in (80, 40):
            for app in (self.epic(width), self.nerdvana(width)):
                for key in ("1", "1", "0"):
                    app.key(key)
                    self.assertTrue(all(len(r) == width for r in app.screen()), width)
                    self.assertLessEqual(len(app.screen()[-1].rstrip()), width)

    def test_guida_mentions_the_key(self):
        app = App(FakeShop())
        app.key("GUIDA")
        self.assertIn("torna all'indice", "\n".join(app.screen()))


# ---- the author's name, after the title and the date (Storie di EPIC only) ----

class AuthorTests(unittest.TestCase):
    def open_article(self, client, key="1"):
        app = App(FakeShop(), stories=client, nerdvana=nerdvana(), loading_delay=5)
        app.key("6")
        app.key(key)
        return app

    def test_the_article_carries_the_name_wordpress_gives_the_author(self):
        art = epic(fake_fetch()).article(3)
        self.assertEqual(art.author, "Fjóna Cakalli")
        self.assertEqual(epic(fake_fetch()).article(2).author, "")          # no author in the answer

    def test_epic_shows_di_name_after_the_title_and_the_date_and_before_the_text(self):
        app = self.open_article(epic(fake_fetch()))
        lines = [r.strip() for r in app.screen()[2:21]]
        self.assertEqual(lines[0], "PERCHÉ L'INFINITO - PARTE TRE")
        self.assertEqual(lines[1], "6 marzo 2026")
        self.assertEqual(lines[2], "di Fjona Cakalli")                 # ó is not on the terminal: plain o
        self.assertEqual(lines[3], "")
        self.assertEqual(lines[4], "UN TITOLO")

    def test_an_article_without_an_author_has_no_di_line(self):
        app = self.open_article(epic(fake_fetch()), key="2")                # "Secondo articolo"
        lines = [r.strip() for r in app.screen()[2:8]]
        self.assertEqual(lines[:3], ["SECONDO ARTICOLO", "3 febbraio 2026", ""])
        self.assertNotIn("di ", " ".join(lines[:3]))

    def test_nerdvana_does_not_show_authors_even_if_the_api_sends_one(self):
        GUIDES[54][0]["_embedded"] = {"author": [{"name": "Qualcuno"}]}
        self.addCleanup(GUIDES[54][0].pop, "_embedded")
        app = App(FakeShop(), nerdvana=nerdvana(), loading_delay=5)
        app.key("7"); app.key("1"); app.key("1")
        self.assertNotIn("Qualcuno", "\n".join(app.screen()))

    def test_the_line_keeps_the_layout_exact_in_ascii_mode(self):
        text.set_ascii_only(True)
        self.addCleanup(text.set_ascii_only, False)
        for width in (80, 40):
            app = App(FakeShop(), width=width, stories=epic(fake_fetch()), loading_delay=5)
            app.key("6"); app.key("1")
            screen = app.screen()
            self.assertIn("di Fjona Cakalli", "\n".join(screen))           # accent spelled out
            self.assertTrue(all(len(r) == width and r.isascii() for r in screen))


if __name__ == "__main__":
    unittest.main()
