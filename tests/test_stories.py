"""Stories tests use invented articles shaped like WordPress REST answers."""
import json
import tempfile
import unittest
from pathlib import Path

from totem import blog, text
from totem.app import App, HEIGHT
from totem.blog import Post, WordPressClient
from totem.text import html_to_text


def rest_post(pid, title, date, content="", link=None):
    return {"id": pid, "date": date, "title": {"rendered": title},
            "link": link or f"https://example.org/{pid}/",
            "content": {"rendered": content}}


POSTS = [rest_post(3, "Perch&eacute; l&#8217;infinito &#8211; parte tre", "2026-03-06T10:00:00",
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
            WordPressClient("https://example.org", "storie", fetch=down).posts()

    def test_an_unknown_category_gives_an_empty_list(self):
        c = WordPressClient("https://example.org", "boh", fetch=lambda url: [])
        self.assertEqual(c.posts(), [])

    def test_domain_without_scheme_or_www(self):
        self.assertEqual(WordPressClient("https://www.example.org/", "s").domain, "example.org")


class ScreenTests(unittest.TestCase):
    def open_stories(self, width=80, client=None):
        app = App(FakeShop(), width=width, stories=client or WordPressClient("https://example.org", "storie", fetch=fake_fetch()),
                  loading_delay=5)
        app.key("8")
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
        app = self.open_stories(client=WordPressClient("https://example.org", "boh", fetch=lambda url: []))
        self.assertIn("Nessuna storia trovata", "\n".join(app.screen()))

    def test_network_down_shows_the_error_screen(self):
        def down(url):
            raise OSError("rete assente")
        app = self.open_stories(client=WordPressClient("https://example.org", "storie", fetch=down))
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
            self.assertIn("8  Storie EPIC", home)


if __name__ == "__main__":
    unittest.main()
