import time
import unittest

from totem.app import App, HEIGHT, loading_screen
from totem.terminal import encode_screen, estimate_seconds


class SlowShop:
    def __init__(self, delay=0.0, fail=False):
        self.delay, self.fail = delay, fail

    def collections(self):
        return []

    def refresh(self):
        pass

    def newest(self):
        time.sleep(self.delay)
        if self.fail:
            raise OSError("rete assente")
        return []


def open_new(app):
    app.key("2")  # "Novità" on the home screen


class LoadingScreenTests(unittest.TestCase):
    def test_layout(self):
        for w in (80, 40):
            rows = loading_screen(w, "Bestseller")
            self.assertEqual(len(rows), HEIGHT)
            self.assertEqual({len(r) for r in rows}, {w})
            self.assertEqual(rows[0], "ITOMItel".center(w))
            text = "\n".join(rows)
            self.assertIn("Caricamento in corso...", text)
            self.assertIn("Bestseller", text)

    def test_it_is_cheap_to_send(self):
        data = encode_screen(loading_screen(80, "Bestseller"), None, "ff")
        self.assertLess(estimate_seconds(data), 1.5)   # at 1200 baud


class SlowFetchTests(unittest.TestCase):
    def test_slow_fetch_shows_loading_screen_once_then_the_result(self):
        shown = []
        app = App(SlowShop(delay=0.3), on_loading=shown.append, loading_delay=0.05)
        open_new(app)
        self.assertEqual(len(shown), 1)
        self.assertIn("Caricamento in corso...", "\n".join(shown[0]))
        self.assertIn("Novità", "\n".join(shown[0]))
        self.assertIn("Nessun prodotto", "\n".join(app.screen()))  # result is in place

    def test_fast_fetch_never_shows_it(self):
        shown = []
        app = App(SlowShop(delay=0.0), on_loading=shown.append, loading_delay=0.5)
        open_new(app)
        self.assertEqual(shown, [])

    def test_errors_still_reach_the_error_screen(self):
        shown = []
        app = App(SlowShop(delay=0.1, fail=True), on_loading=shown.append,
                  loading_delay=0.02)
        open_new(app)
        self.assertEqual(len(shown), 1)
        self.assertIn("Servizio non raggiungibile", "\n".join(app.screen()))

    def test_without_a_callback_it_just_waits(self):
        app = App(SlowShop(delay=0.1), loading_delay=0.01)
        open_new(app)
        self.assertIn("Nessun prodotto", "\n".join(app.screen()))


if __name__ == "__main__":
    unittest.main()
