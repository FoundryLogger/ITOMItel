import json
import threading
import unittest
import urllib.request

from test_encoding import Ansi
from totem import logo
from totem.saver import Screensaver, cycle, negative_field
from totem.terminal import encode_screen
from totem.web import make_server


class NegativeFieldTests(unittest.TestCase):
    def test_it_is_the_logo_inverted(self):
        field = negative_field(80, "#")
        self.assertEqual((len(field), {len(r) for r in field}), (14, {46}))
        # one module of margin: logo module (r, c) is field cell (r + 1, c + 1), 2 chars wide
        for r, row in enumerate(logo.GRID):
            for c, module in enumerate(row):
                cell = field[r + 1][2 * (c + 1):2 * (c + 1) + 2]
                self.assertEqual(cell, "  " if module == "#" else "##", (r, c))
        self.assertEqual(set(field[0]), {"#"})          # the margin is solid
        self.assertEqual(set(field[-1]), {"#"})

    def test_ink_character_is_configurable(self):
        self.assertEqual(set("".join(negative_field(80, "@"))), {"@", " "})

    def test_forty_columns_fit(self):
        field = negative_field(40)
        self.assertEqual((len(field), {len(r) for r in field}), (12, {40}))


class CycleTests(unittest.TestCase):
    def test_every_frame_is_a_full_screen(self):
        for width in (80, 40):
            for rows, pause in cycle(width):
                self.assertEqual(len(rows), 24)
                self.assertEqual({len(r) for r in rows}, {width})
                self.assertGreater(pause, 0)

    def test_it_starts_and_ends_blank_and_builds_one_row_at_a_time(self):
        frames = cycle(80)
        blank = [" " * 80] * 24
        self.assertEqual(frames[0][0], blank)
        self.assertEqual(frames[-1][0], blank)
        filled = [sum(1 for r in rows if r.strip()) for rows, _ in frames]
        n = len(negative_field(80))
        self.assertEqual(filled[:n + 1], list(range(n + 1)))            # 0, 1, 2 ... 14
        self.assertEqual(filled[n:], list(range(n, -1, -1)))            # then back down

    def test_the_field_is_centred(self):
        rows = cycle(80)[14][0]                      # fully built
        used = [i for i, r in enumerate(rows) if r.strip()]
        self.assertEqual(used[0], 24 - used[-1] - 1)                    # same space above and below
        widths = {len(r) - len(r.lstrip()) for r in rows if r.strip()}
        self.assertEqual(widths, {17})                                  # (80 - 46) / 2
        self.assertEqual(len(rows[used[0]].rstrip()), 17 + 46)

    def test_bytes_for_the_terminal_reproduce_every_frame_and_stay_small(self):
        frames = cycle(80)
        t, prev, total = Ansi(), None, 0
        for rows, _ in frames:
            data = encode_screen(rows, prev, "ansi")
            t.feed(data)
            self.assertFalse(t.overflow)
            self.assertEqual(t.rows(), [r.rstrip() for r in rows])
            prev, total = rows, total + len(data)
        self.assertLess(total * 10 / 1200, 40)       # the whole cycle in under 40 s at 1200 baud


class ScreensaverClockTests(unittest.TestCase):
    def test_it_waits_for_the_idle_time_then_plays_frames_on_schedule(self):
        s = Screensaver(80, after=100, step=1, hold=10, gap=5)
        self.assertIsNone(s.tick(now=50, last_activity=0))        # not idle long enough
        first = s.tick(now=100, last_activity=0)
        self.assertEqual(first, cycle(80, step=1, hold=10, gap=5)[0][0])
        self.assertIsNone(s.tick(now=100.5, last_activity=0))      # the first frame lasts 1 s
        second = s.tick(now=101, last_activity=0)
        self.assertEqual(sum(1 for r in second if r.strip()), 1)   # one row built

    def test_wake_stops_it_and_reports_whether_it_was_running(self):
        s = Screensaver(80, after=10)
        self.assertFalse(s.wake())
        s.tick(now=10, last_activity=0)
        self.assertTrue(s.active)
        self.assertTrue(s.wake())
        self.assertFalse(s.active)
        self.assertIsNone(s.tick(now=11, last_activity=10.5))      # idle clock restarted

    def test_zero_disables_it(self):
        s = Screensaver(80, after=0)
        self.assertIsNone(s.tick(now=10**6, last_activity=0))
        self.assertFalse(s.active)

    def test_it_loops_forever(self):
        s = Screensaver(80, after=1, step=0.1, hold=0.1, gap=0.1)
        n, now, seen = len(s.frames), 1.0, 0
        while seen < 3 * n:
            if s.tick(now, 0) is not None:
                seen += 1
            now += 0.05
        self.assertTrue(s.active)


class WebSaverTests(unittest.TestCase):
    def test_endpoint_serves_the_cycle(self):
        class Shop:
            def collections(self): return []
            def refresh(self): pass
        server = make_server(Shop(), "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        url = f"http://127.0.0.1:{server.server_address[1]}/api/saver?width=80"
        with urllib.request.urlopen(url) as r:
            frames = json.load(r)["frames"]
        self.assertEqual(len(frames), len(cycle(80)))
        self.assertEqual(frames[14]["rows"], cycle(80)[14][0])
        self.assertTrue(all(len(f["rows"]) == 24 for f in frames))


if __name__ == "__main__":
    unittest.main()
