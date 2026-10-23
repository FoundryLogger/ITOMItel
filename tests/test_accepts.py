"""Which keys are worth interrupting a drawing for? Those that change the screen being drawn.

App.accepts(k) must say exactly what pressing k then does, on every screen: this checks it
against the real thing for a lot of screens and keys. Then the watcher and the drawing are
checked with it."""
import unittest

from test_indexes import Shop
from test_interrupt import LinePort
from test_stories import big_fetch, epic, nerdvana
from test_televideo import FakeTv
from totem.app import App
from totem.saver import Screensaver
from totem.terminal import KeyDecoder, KeyWatcher, SerialTerminal, encode_screen

KEYS = ["0", "1", "2", "5", "9", "a", "j", "k", "x", "SEGUENTE", "PRECEDENTE", "ANNUL", "INDICE",
        "GUIDA", "CORREZIONE", "INVIO", "DESTRA", "SINISTRA"]


class DownShop(Shop):
    def collections(self):
        raise OSError("rete assente")


def app_at(keys, width=80, shop=None):
    app = App(shop or Shop(), width=width, televideo=FakeTv(), stories=epic(big_fetch),
              nerdvana=nerdvana(), loading_delay=5)
    for k in keys:
        app.key(k)
    return app


SCREENS = {
    "menu": [],
    "categorie": ["1"], "categorie p2": ["1", "SEGUENTE"], "categorie ultima": ["1", "SEGUENTE", "SEGUENTE"],
    "prodotti": ["2"], "prodotti ultima": ["2", "SEGUENTE"], "scheda prodotto": ["2", "1"],
    "credits": ["0"], "credits p2": ["0", "SEGUENTE"],
    "guida": ["GUIDA"], "impostazioni": ["9"], "impostazioni da guida": ["GUIDA", "1"],
    "cerca": ["5"], "cerca con testo": ["5", "a", "b"], "cerca piena": ["5"] + ["x"] * 30,
    "televideo": ["8"], "televideo con cifra": ["8", "1"], "televideo 2 cifre": ["8", "1", "0"],
    "televideo sottopagine": ["8", "1", "0", "1"], "televideo lunga": ["8", "2", "0", "0"],
    "storie": ["6"], "storie p2": ["6", "SEGUENTE"], "storia": ["6", "1"], "storia p2 elenco": ["6", "SEGUENTE", "1"],
    "nerdvana citta": ["7"], "nerdvana guide": ["7", "1"], "nerdvana guida": ["7", "1", "1"],
}


class AcceptsMatchesReality(unittest.TestCase):
    def check(self, keys, key, width=80, shop=None):
        app = app_at(keys, width, shop)
        before = app.screen()
        says = app.accepts(key)
        app.key(key)
        changed = app.screen() != before
        self.assertEqual(says, changed, f"{keys} + {key}: accepts={says}, but the screen {'did' if changed else 'did not'} change")

    def test_on_every_screen_for_every_key(self):
        for width in (80, 40):
            for name, keys in SCREENS.items():
                for key in KEYS:
                    with self.subTest(width=width, screen=name, key=key):
                        self.check(keys, key, width)

    def test_on_the_error_screen(self):
        # the shop is down: the categories can't load and an error message is shown
        for key in KEYS:
            with self.subTest(key=key):
                app = App(DownShop(), loading_delay=5)
                app.key("1")
                before = app.screen()
                says = app.accepts(key)
                app.key(key)
                self.assertEqual(says, app.screen() != before, key)

    def test_ripetiz_always_counts_it_redraws_the_screen(self):
        for name, keys in SCREENS.items():
            self.assertTrue(app_at(keys).accepts("RIPETIZ"), name)

    def test_the_arrows_count_like_seguente_and_precedente(self):
        for name, keys in SCREENS.items():
            app = app_at(keys)
            self.assertEqual(app.accepts("DESTRA"), app.accepts("SEGUENTE"), name)
            self.assertEqual(app.accepts("SINISTRA"), app.accepts("PRECEDENTE"), name)

    def test_a_few_cases_in_plain_words(self):
        menu = app_at([])
        self.assertTrue(menu.accepts("3"))                # a menu entry
        self.assertFalse(menu.accepts("x"))               # a letter in the menu
        self.assertFalse(menu.accepts("SEGUENTE"))        # nothing to page
        self.assertFalse(menu.accepts("INDICE"))          # already there
        last = app_at(["0", "SEGUENTE"])                  # the last page of the credits
        self.assertFalse(last.accepts("SEGUENTE"))
        self.assertTrue(last.accepts("PRECEDENTE"))
        lst = app_at(["2", "SEGUENTE"])                   # the second page of products: 6 items
        self.assertTrue(lst.accepts("6"))                 # the sixth item exists (labels start again at 1)
        self.assertFalse(lst.accepts("7"))                # no seventh item
        self.assertFalse(lst.accepts("a"))                # and no letters on this page
        search = app_at(["5"])
        self.assertTrue(search.accepts("a"))
        self.assertFalse(search.accepts("INVIO"))         # nothing written yet
        self.assertFalse(search.accepts("CORREZIONE"))


def screens():
    app = App(Shop())
    return app.screen()


class WatcherWithAppTests(unittest.TestCase):
    def watcher(self, app, port, saver=None):
        return KeyWatcher(port, KeyDecoder(),
                          is_command=lambda k: (saver is not None and saver.active) or app.accepts(k))

    def test_a_key_that_does_nothing_here_does_not_stop_the_drawing_but_is_not_lost(self):
        app = App(Shop())
        home = app.screen()
        port = LinePort(keys_after={5: b"x"})                    # a letter in the menu
        w = self.watcher(app, port)
        term = SerialTerminal(port, "ansi")
        term.draw(home, full=True, abort=w.interrupted)
        self.assertEqual(b"".join(port.writes), encode_screen(home, None, "ansi", 0, True))   # all of it was sent
        self.assertEqual(term.prev, home)
        self.assertEqual(w.take(), ["x"])                        # still delivered, in order, to the main loop

    def test_a_key_that_changes_the_screen_stops_it(self):
        app = App(Shop())
        home = app.screen()
        port = LinePort(keys_after={5: b"3"})                    # the Bestseller entry
        w = self.watcher(app, port)
        term = SerialTerminal(port, "ansi")
        term.draw(home, full=True, abort=w.interrupted)
        self.assertEqual(len(port.writes), 5)
        self.assertIsNone(term.prev)
        self.assertEqual(w.take(), ["3"])

    def test_useless_keys_ahead_of_a_good_one_are_kept_in_order(self):
        app = App(Shop())
        port = LinePort(keys_after={4: b"x", 6: b"2"})
        w = self.watcher(app, port)
        SerialTerminal(port, "ansi").draw(app.screen(), full=True, abort=w.interrupted)
        self.assertEqual(len(port.writes), 6)                    # it ran on past the "x", stopped at the "2"
        self.assertEqual(w.take(), ["x", "2"])

    def test_any_key_wakes_the_screensaver_even_one_that_means_nothing(self):
        app = App(Shop())
        saver = Screensaver(80, after=1)
        port = LinePort(keys_after={3: b"x"})
        w = self.watcher(app, port, saver)
        saver.tick(now=10, last_activity=0)                      # the saver is running
        self.assertTrue(saver.active)
        SerialTerminal(port, "ansi").draw(app.screen(), full=True, abort=w.interrupted)
        self.assertEqual(len(port.writes), 3)
        self.assertEqual(w.take(), ["x"])

    def test_the_urgent_flag_is_cleared_once_the_keys_are_taken(self):
        app = App(Shop())
        port = LinePort()
        w = self.watcher(app, port)
        port.inbox = b"3"
        self.assertTrue(w.interrupted())
        w.take()
        self.assertFalse(w.interrupted())


if __name__ == "__main__":
    unittest.main()
