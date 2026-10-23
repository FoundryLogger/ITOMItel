"""Televideo tests use invented pages that only copy the structure of the real ones
(a 40-column <pre> block plus links); no RAI text is stored in the repository."""
import unittest

from totem import text
from totem.app import App, BODY, HEIGHT
from totem.televideo import SOURCE, TelevideoClient, TvPage, parse


def markup(number, lines, subs=(1,)):
    links = "".join(f'<a href="solotesto.jsp?pagina={number}&amp;sottopagina={s}">x</a>' for s in subs)
    links += f'<a href="solotesto.jsp?pagina={number + 1}&amp;sottopagina=1">Pagina Successiva</a>'
    return f"<html><body><pre>{chr(10).join(lines)}</pre>{links}</body></html>"


class FakeShop:
    def collections(self):
        return []

    def refresh(self):
        pass


class FakeTv:
    """Stands in for TelevideoClient: a few made-up pages, and a log of requests."""
    def __init__(self, pages=None, fail=False):
        self.pages = pages if pages is not None else {
            (100, 1): TvPage(100, 1, [1], ["  PAGINA DI PROVA 100", "", "  Indice inventato"]),
            (101, 1): TvPage(101, 1, [1, 2], ["  NOTIZIE DI PROVA", "  Perché è così"]),
            (101, 2): TvPage(101, 2, [1, 2], ["  SECONDA PARTE"]),
            (102, 1): TvPage(102, 1, [1], ["  CENTODUE"]),
            (200, 1): TvPage(200, 1, [1], [f"  riga {i}" for i in range(1, 24)]),
        }
        self.fail, self.log = fail, []

    def get(self, number, sub=1):
        self.log.append((number, sub))
        if self.fail:
            raise OSError("rete assente")
        return self.pages.get((number, sub))


def open_tv(tv=None, width=80):
    app = App(FakeShop(), width=width, televideo=tv or FakeTv(), loading_delay=5)
    app.key("7")
    return app


class ParseTests(unittest.TestCase):
    def test_extracts_the_pre_block_and_trims_empty_edges(self):
        page = parse(markup(103, ["", "  TITOLO", "  riga due  ", "", ""]), 103)
        self.assertEqual(page.lines, ["  TITOLO", "  riga due"])
        self.assertEqual((page.number, page.sub, page.subs), (103, 1, [1]))

    def test_html_entities_are_decoded(self):
        page = parse(markup(103, ["  PAPA NON ANDR&Agrave; &amp; ALTRO"]), 103)
        self.assertEqual(page.lines, ["  PAPA NON ANDRÀ & ALTRO"])

    def test_subpages_come_from_the_links_to_the_same_page_only(self):
        page = parse(markup(130, ["  testo"], subs=(1, 2, 3)), 130)
        self.assertEqual(page.subs, [1, 2, 3])                      # not 131's link

    def test_a_missing_page_is_none(self):
        self.assertIsNone(parse("<html><body>niente</body></html>", 999))
        self.assertIsNone(parse(markup(999, ["   ", ""]), 999))


class ClientTests(unittest.TestCase):
    def test_pages_are_cached_briefly_and_then_asked_for_again(self):
        calls = []
        client = TelevideoClient(ttl=0.2, pause=0, fetch=lambda n, s: calls.append((n, s)) or markup(n, ["  x"]))
        client.get(100)
        client.get(100)
        self.assertEqual(len(calls), 1)
        import time
        time.sleep(0.25)
        client.get(100)
        self.assertEqual(len(calls), 2)

    def test_it_keeps_a_pause_between_requests(self):
        import time
        stamps = []
        client = TelevideoClient(pause=0.15, fetch=lambda n, s: stamps.append(time.monotonic()) or markup(n, ["  x"]))
        client.get(100)
        client.get(101)
        self.assertGreaterEqual(stamps[1] - stamps[0], 0.14)

    def test_network_errors_propagate_and_are_not_cached(self):
        def boom(n, s):
            raise OSError("down")
        client = TelevideoClient(pause=0, fetch=boom)
        with self.assertRaises(OSError):
            client.get(100)
        client._fetch = lambda n, s: markup(n, ["  ok"])
        self.assertEqual(client.get(100).lines, ["  ok"])


class ScreenTests(unittest.TestCase):
    def test_menu_entry_opens_page_100_with_the_source_notice(self):
        app = open_tv()
        screen = app.screen()
        self.assertEqual(len(screen), HEIGHT)
        self.assertTrue(screen[0].startswith("TELEVIDEO  100"))
        self.assertIn("PAGINA DI PROVA 100", "\n".join(screen))
        self.assertIn(SOURCE, "\n".join(screen))                    # the source is always shown
        self.assertEqual({len(r) for r in screen}, {80})

    def test_the_40_column_text_is_centred_on_80_columns(self):
        row = [r for r in open_tv().screen() if "PAGINA DI PROVA" in r][0]
        self.assertEqual(len(row) - len(row.lstrip()), 20 + 2)       # 20 to centre + 2 of the page's own indent

    def test_typing_three_digits_loads_that_page_like_on_a_tv(self):
        tv = FakeTv()
        app = open_tv(tv)
        app.key("1")
        self.assertIn("TELEVIDEO  1__", app.screen()[0])
        app.key("0")
        self.assertIn("TELEVIDEO  10_", app.screen()[0])
        app.key("2")
        self.assertIn("CENTODUE", "\n".join(app.screen()))
        self.assertEqual(tv.log[-1], (102, 1))

    def test_correzione_and_annul_edit_the_entry_before_leaving(self):
        app = open_tv()
        app.key("1"); app.key("5")
        app.key("CORREZIONE")
        self.assertIn("1__", app.screen()[0])
        app.key("ANNUL")
        self.assertIn("TELEVIDEO  100", app.screen()[0])
        app.key("ANNUL")                                             # nothing typed: back to the menu
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_pages_outside_100_899_are_refused_without_a_request(self):
        tv = FakeTv()
        app = open_tv(tv)
        before = len(tv.log)
        for k in "050":
            app.key(k)
        self.assertIn("Le pagine vanno da 100 a 899", "\n".join(app.screen()))
        self.assertEqual(len(tv.log), before)

    def test_a_missing_page_keeps_the_current_one_and_says_so(self):
        app = open_tv()
        for k in "555":
            app.key(k)
        screen = "\n".join(app.screen())
        self.assertIn("Pagina 555 non disponibile", screen)
        self.assertIn("PAGINA DI PROVA 100", screen)

    def test_network_down_shows_a_message_instead_of_crashing(self):
        app = App(FakeShop(), televideo=FakeTv(fail=True), loading_delay=5)
        app.key("7")
        self.assertIn("Televideo non raggiungibile", "\n".join(app.screen()))
        app.key("INDICE")
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))


class NavigationTests(unittest.TestCase):
    def test_seguente_goes_to_the_next_subpage_then_the_next_page(self):
        app = open_tv()
        app.key("1"); app.key("0"); app.key("1")
        self.assertIn("1/2", app.screen()[0])
        app.key("SEGUENTE")
        self.assertIn("SECONDA PARTE", "\n".join(app.screen()))
        self.assertIn("2/2", app.screen()[0])
        app.key("SEGUENTE")
        self.assertIn("CENTODUE", "\n".join(app.screen()))           # page 102

    def test_precedente_goes_back_and_leaves_to_the_menu_before_page_100(self):
        app = open_tv()
        app.key("SEGUENTE")                                          # 100 -> 101
        self.assertIn("NOTIZIE DI PROVA", "\n".join(app.screen()))
        app.key("PRECEDENTE")
        self.assertIn("TELEVIDEO  100", app.screen()[0])
        app.key("PRECEDENTE")
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_a_page_longer_than_the_screen_scrolls_before_moving_on(self):
        app = open_tv()
        for k in "200":
            app.key(k)
        first = "\n".join(app.screen())
        self.assertIn("riga 1", first)
        self.assertIn("--- continua (Seguente) ---", first)
        self.assertNotIn("riga 23", first)
        app.key("SEGUENTE")
        second = "\n".join(app.screen())
        self.assertIn("riga 23", second)
        self.assertNotIn("--- continua", second)
        app.key("PRECEDENTE")
        self.assertIn("riga 1 ", "\n".join(app.screen()))         # back at the top of the page

    def test_layout_is_exact_in_ascii_mode_on_80_and_40_columns(self):
        text.set_ascii_only(True)
        self.addCleanup(text.set_ascii_only, False)
        for width in (80, 40):
            app = open_tv(width=width)
            app.key("1"); app.key("0"); app.key("1")
            for r in app.screen():
                self.assertEqual(len(r), width, r)
                self.assertTrue(r.isascii(), r)


if __name__ == "__main__":
    unittest.main()
