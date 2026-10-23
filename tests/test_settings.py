import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from totem.app import App, GUIDA, HEIGHT
from totem.saver import Screensaver
from totem.settings import DEFAULTS, ORDER, SPECS, Settings
from totem.web import make_server


class FakeShop:
    def collections(self):
        return []

    def refresh(self):
        pass


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        s = Settings()
        self.assertEqual((s.saver_after, s.idle_after, s.ink, s.hold), (300, 120, "#", 30))

    def test_cycle_walks_the_options_and_wraps_around(self):
        s = Settings()
        seen = []
        for _ in range(len(SPECS["saver_after"][2])):
            s.cycle("saver_after")
            seen.append(s.saver_after)
        self.assertEqual(seen, [600, 0, 60, 300])          # 5 min -> 10 min -> never -> 1 min -> 5 min

    def test_values_are_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            s = Settings(path)
            s.cycle("ink")
            s.cycle("hold")
            again = Settings(path)
            self.assertEqual((again.ink, again.hold), ("@", 60))

    def test_garbage_in_the_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            path.write_text(json.dumps({"saver_after": 7, "ink": "@", "nope": 1, "hold": "x"}))
            s = Settings(path)
            self.assertEqual((s.saver_after, s.ink, s.hold), (300, "@", 30))
            path.write_text("not json at all")
            self.assertEqual(Settings(path).values, DEFAULTS)

    def test_command_line_values_win_at_start_even_if_not_in_the_list(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            path.write_text(json.dumps({"saver_after": 600}))
            s = Settings(path, saver_after=30, idle_after=None)
            self.assertEqual((s.saver_after, s.idle_after), (30, 120))
            self.assertEqual(s.text("saver_after"), "30 s")
            s.cycle("saver_after")                           # not in the list: back to the first
            self.assertEqual(s.saver_after, 60)

    def test_a_read_only_location_does_not_stop_anything(self):
        s = Settings("/nonexistent-folder/settings.json")
        s.cycle("ink")                                       # must not raise
        self.assertEqual(s.ink, "@")


class SettingsScreenTests(unittest.TestCase):
    def open_settings(self, width=80):
        app = App(FakeShop(), width=width)
        app.key(GUIDA)
        app.key("1")
        return app

    def test_guida_offers_the_settings_and_annul_goes_back(self):
        app = App(FakeShop())
        app.key(GUIDA)
        self.assertIn("1  Impostazioni", "\n".join(app.screen()))
        app.key("1")
        self.assertTrue(app.screen()[0].startswith("IMPOSTAZIONI"))
        app.key("ANNUL")
        self.assertTrue(app.screen()[0].startswith("GUIDA"))
        app.key("ANNUL")
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_pressing_guida_again_does_not_stack_screens(self):
        app = App(FakeShop())
        app.key(GUIDA)
        app.key(GUIDA)
        app.key("ANNUL")
        self.assertEqual(app.screen()[0], "ITOMItel".center(80))

    def test_layout_on_80_and_40_columns(self):
        for width in (80, 40):
            screen = self.open_settings(width).screen()
            self.assertEqual(len(screen), HEIGHT)
            self.assertEqual({len(r) for r in screen}, {width})
            self.assertEqual(sum(1 for r in screen if "..." in r), len(ORDER))

    def test_a_number_changes_that_value_on_screen(self):
        app = self.open_settings()
        before = "\n".join(app.screen())
        self.assertIn("5 minuti", before)
        app.key("1")
        after = "\n".join(app.screen())
        self.assertIn("10 minuti", after)
        self.assertEqual(app.settings.saver_after, 600)
        app.key("3")
        self.assertEqual(app.settings.ink, "@")

    def test_the_value_sits_at_the_right_edge(self):
        row = [r for r in self.open_settings().screen() if "Screensaver dopo" in r][0]
        self.assertTrue(row.endswith("minuti  "), row)


class ScreensaverConfigureTests(unittest.TestCase):
    def test_new_ink_rebuilds_the_frames(self):
        s = Screensaver(80, after=60)
        s.configure(60, "@", 30)
        self.assertIn("@", "".join(s.frames[24][0]))
        self.assertNotIn("#", "".join(s.frames[24][0]))

    def test_new_hold_changes_the_pause_on_the_full_logo(self):
        s = Screensaver(80, after=60)
        s.configure(60, "#", 120)
        self.assertEqual(s.frames[24][1], 120)

    def test_never_stops_it_and_a_later_value_starts_it_again(self):
        s = Screensaver(80, after=60)
        s.tick(now=100, last_activity=0)
        self.assertTrue(s.active)
        s.configure(0, "#", 30)
        self.assertFalse(s.active)
        self.assertIsNone(s.tick(now=10**6, last_activity=0))
        s.configure(60, "#", 30)
        self.assertIsNotNone(s.tick(now=10**6, last_activity=0))


class WebSettingsTests(unittest.TestCase):
    def test_the_emulator_gets_the_settings_and_the_saver_uses_them(self):
        server = make_server(FakeShop(), "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def key(k):
            req = urllib.request.Request(base + "/api/key", method="POST",
                                         data=json.dumps({"sid": "t", "width": 80, "key": k}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                return json.load(r)

        key("GUIDA")
        key("1")
        r = key("1")                                            # saver_after 300 -> 600
        self.assertEqual(r["settings"]["saver_after"], 600)
        r = key("3")                                            # ink # -> @
        self.assertEqual(r["settings"]["ink"], "@")
        with urllib.request.urlopen(base + "/api/saver?sid=t&width=80") as resp:
            frames = json.load(resp)["frames"]
        self.assertIn("@", "".join(frames[24]["rows"]))
        with urllib.request.urlopen(base + "/api/saver?sid=other&width=80") as resp:
            other = json.load(resp)["frames"]
        self.assertIn("#", "".join(other[24]["rows"]))           # another session keeps its own


if __name__ == "__main__":
    unittest.main()
