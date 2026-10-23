import json
import threading
import unittest
import urllib.request

from test_encoding import Ansi
from totem import logo
from totem.saver import Screensaver, cycle, logo_origin, negative_screen
from totem.terminal import encode_screen
from totem.web import make_server


class NegativeScreenTests(unittest.TestCase):
    def test_the_whole_screen_is_filled_and_the_logo_is_carved_out(self):
        rows = negative_screen(80, "#")
        self.assertEqual((len(rows), {len(r) for r in rows}), (24, {80}))
        top, left = logo_origin(80)
        self.assertEqual((top, left), (6, 19))                  # centred: (24-12)/2, (80-42)/2
        for r, row in enumerate(logo.GRID):
            for c, module in enumerate(row):
                cell = rows[top + r][left + 2 * c:left + 2 * c + 2]
                self.assertEqual(cell, "  " if module == "#" else "##", (r, c))
        carved = {(top + r, left + 2 * c + k) for r, row in enumerate(logo.GRID)
                  for c, m in enumerate(row) if m == "#" for k in (0, 1)}
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if (r, c) not in carved:
                    self.assertEqual(ch, "#", (r, c))              # everything else is ink

    def test_ink_character_is_configurable(self):
        self.assertEqual(set("".join(negative_screen(80, "@"))), {"@", " "})

    def test_forty_columns_use_the_compact_logo(self):
        rows = negative_screen(40)
        self.assertEqual((len(rows), {len(r) for r in rows}), (24, {40}))
        self.assertEqual(logo_origin(40), (6, 0))
        self.assertIn(" ", rows[6 + 3])


class CycleTests(unittest.TestCase):
    def test_every_frame_is_a_full_screen(self):
        for width in (80, 40):
            for rows, pause in cycle(width):
                self.assertEqual(len(rows), 24)
                self.assertEqual({len(r) for r in rows}, {width})
                self.assertGreaterEqual(pause, 0)

    def test_it_starts_and_ends_blank_and_builds_one_row_at_a_time(self):
        frames = cycle(80)
        blank = [" " * 80] * 24
        self.assertEqual(frames[0][0], blank)
        self.assertEqual(frames[-1][0], blank)
        filled = [sum(1 for r in rows if r.strip()) for rows, _ in frames]
        self.assertEqual(filled[:25], list(range(25)))                 # 0, 1, 2 ... 24
        self.assertEqual(filled[24:], list(range(24, -1, -1)))         # then back down
        self.assertEqual(frames[24][0], negative_screen(80))           # the full screen

    def test_it_is_built_from_the_top_and_emptied_from_the_bottom(self):
        frames = cycle(80)
        full = negative_screen(80)
        self.assertEqual(frames[3][0][:3], full[:3])
        self.assertEqual(frames[3][0][3], " " * 80)
        self.assertEqual(frames[24 + 1][0][-1], " " * 80)             # last row goes first

    def test_bytes_for_the_terminal_reproduce_every_frame(self):
        frames = cycle(80)
        t, prev, total = Ansi(), None, 0
        for rows, _ in frames:
            data = encode_screen(rows, prev, "ansi")
            t.feed(data)
            self.assertFalse(t.overflow)
            self.assertEqual(t.rows(), [r.rstrip() for r in rows])
            prev, total = rows, total + len(data)
        self.assertLess(total * 10 / 1200, 30)       # the whole cycle in under 30 s at 1200 baud


class NoPauseBetweenRoundsTests(unittest.TestCase):
    def test_the_last_frame_has_no_pause_and_the_default_cycle_has_no_blank_wait(self):
        frames = cycle(80)
        self.assertEqual(frames[-1][1], 0.0)
        waits = [pause for rows, pause in frames if not any(r.strip() for r in rows)]
        self.assertLessEqual(max(waits), 1.0)         # only the 1 s of the very first blank frame

    def test_when_it_loops_the_next_frame_is_the_first_row_straight_away(self):
        s = Screensaver(80, after=1, step=1, hold=5)
        n, now, drawn = len(s.frames), 1.0, []
        while len(drawn) < n + 2:
            f = s.tick(now, 0)
            if f is not None:
                drawn.append((now, sum(1 for r in f if r.strip())))
            now += 0.25
        # frames: ... last (blank) at index n-1, then the second round starts with ONE row
        t_blank, filled_blank = drawn[n - 1]
        t_next, filled_next = drawn[n]
        self.assertEqual((filled_blank, filled_next), (0, 1))
        self.assertLessEqual(t_next - t_blank, 0.25)    # no pause: the very next tick
        # and the second round does not begin with the blank start frame again
        self.assertEqual(drawn[n + 1][1], 2)


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
        self.assertEqual(frames[24]["rows"], cycle(80)[24][0])
        self.assertTrue(all(len(f["rows"]) == 24 for f in frames))


if __name__ == "__main__":
    unittest.main()
