"""The line speed: a setting (1200 / 4800), changed by telling the terminal."""
import unittest

from totem import terminal
from totem.app import App, GUIDA, HEIGHT
from totem.settings import ORDER, SPECS, Settings
from totem.terminal import KeyDecoder, SerialTerminal, SPEED_CODES, speed_command


class SpeedPort:
    """A port with a baudrate, remembering what was written at which speed."""
    def __init__(self, answer=b""):
        self.baudrate, self.log, self.answer, self.reads = 1200, [], answer, 0

    def write(self, data): self.log.append((self.baudrate, data))
    def flush(self): pass

    def read(self, n=1):
        self.reads += 1
        out, self.answer = self.answer[:n], self.answer[n:]
        return out


class FakeShop:
    def collections(self): return []
    def refresh(self): pass


class SettingTests(unittest.TestCase):
    def test_the_speed_is_a_setting_with_only_checked_values(self):
        self.assertEqual(Settings().baud, 1200)
        self.assertEqual([v for v, _ in SPECS["baud"][2]], [1200, 4800])
        self.assertEqual(set(SPECS["baud"][2][i][0] for i in range(2)), set(SPECS_SPEEDS))

    def test_cycling_goes_to_4800_and_back(self):
        s = Settings()
        s.cycle("baud"); self.assertEqual(s.baud, 4800)
        s.cycle("baud"); self.assertEqual(s.baud, 1200)

    def test_it_is_saved_and_a_value_nobody_checked_is_ignored(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            path.write_text(json.dumps({"baud": 4800}))
            self.assertEqual(Settings(path).baud, 4800)
            path.write_text(json.dumps({"baud": 9600}))
            self.assertEqual(Settings(path).baud, 1200)            # 9600 was never checked


SPECS_SPEEDS = set(SPEED_CODES)


class SettingsScreenTests(unittest.TestCase):
    def test_the_speed_is_the_fifth_entry_with_a_note_about_restarting_the_minitel(self):
        app = App(FakeShop())
        app.key("9")
        screen = app.screen()
        joined = "\n".join(screen)
        self.assertEqual(ORDER[-1], "baud")
        self.assertIn("5  Velocità della linea", joined)
        self.assertTrue(any(r.rstrip().endswith("1200 baud") for r in screen))
        self.assertIn("Se lo spegni e lo riaccendi", joined)
        app.key("5")
        self.assertTrue(any(r.rstrip().endswith("4800 baud") for r in app.screen()))
        self.assertEqual(app.settings.baud, 4800)

    def test_the_screen_still_fits_on_80_and_40_columns(self):
        for width in (80, 40):
            app = App(FakeShop(), width=width)
            app.key("9")
            screen = app.screen()
            self.assertEqual(len(screen), HEIGHT)
            self.assertEqual({len(r) for r in screen}, {width})


class SwitchTests(unittest.TestCase):
    def test_the_commands_are_the_minitel_ones(self):
        self.assertEqual(speed_command(4800), b"\x1b:kv")
        self.assertEqual(speed_command(1200), b"\x1b:kd")

    def test_it_asks_at_the_old_speed_waits_reading_the_answer_then_follows(self):
        port = SpeedPort(answer=b"\x1b:sv")                       # the terminal answers at the old speed
        term = SerialTerminal(port, "ansi", baud=1200)
        term.prev = ["x"]
        term.switch_speed(4800, settle=0.05)
        self.assertEqual(port.log, [(1200, b"\x1b:kv")])          # sent at 1200
        self.assertEqual(port.baudrate, 4800)
        self.assertEqual(term.baud, 4800)
        self.assertGreater(port.reads, 0)                          # the answer was read and dropped
        self.assertEqual(port.answer, b"")
        self.assertIsNone(term.prev)                               # the screen is unknown: next draw is full

    def test_it_waits_the_full_settling_time(self):
        import time
        port = SpeedPort()
        start = time.monotonic()
        SerialTerminal(port, "ansi").switch_speed(4800, settle=0.3)
        self.assertGreaterEqual(time.monotonic() - start, 0.29)

    def test_the_default_wait_is_long_enough_that_the_first_attempts_did_not_fail(self):
        import inspect
        self.assertGreaterEqual(inspect.signature(SerialTerminal.switch_speed).parameters["settle"].default, 1.0)

    def test_going_back_is_sent_at_the_current_speed(self):
        port = SpeedPort()
        term = SerialTerminal(port, "ansi", baud=1200)
        term.switch_speed(4800, settle=0)
        term.switch_speed(1200, settle=0)
        self.assertEqual(port.log, [(1200, b"\x1b:kv"), (4800, b"\x1b:kd")])
        self.assertEqual(port.baudrate, 1200)

    def test_nothing_is_sent_when_the_speed_is_already_right(self):
        port = SpeedPort()
        SerialTerminal(port, "ansi", baud=1200).switch_speed(1200, settle=0)
        self.assertEqual(port.log, [])

    def test_resync_starts_again_from_1200_whatever_we_thought(self):
        port = SpeedPort()
        port.baudrate = 4800
        term = SerialTerminal(port, "ansi", baud=4800)             # we believe 4800; the terminal is at 1200
        term.resync(4800, settle=0)
        self.assertEqual(port.log, [(1200, b"\x1b:kv")])           # the command went out at 1200
        self.assertEqual((port.baudrate, term.baud), (4800, 4800))

    def test_a_port_without_baudrate_does_not_break_it(self):
        class Plain:
            def __init__(self): self.out = []
            def write(self, d): self.out.append(d)
        port = Plain()
        SerialTerminal(port, "ansi").switch_speed(4800, settle=0)
        self.assertEqual(port.out, [b"\x1b:kv"])


class GarbageTests(unittest.TestCase):
    def test_a_burst_of_control_bytes_is_counted(self):
        d = KeyDecoder()
        self.assertEqual(d.feed(b"\x00x\x00\x00x\x00\x80"), ["x", "x"])
        self.assertEqual(d.take_dropped(), 5)                      # the zeros and the 0x80
        self.assertEqual(d.take_dropped(), 0)

    def test_normal_typing_and_known_sequences_count_for_nothing(self):
        d = KeyDecoder()
        d.feed(b"ab\r\x1b[C\x1b[A3")                               # letters, Invio, an arrow, an unknown arrow
        self.assertEqual(d.take_dropped(), 0)

    def test_the_resync_threshold_is_four_dropped_bytes(self):
        src = open(terminal.__file__.replace("terminal.py", "serial_cli.py")).read()
        self.assertIn("take_dropped() >= 4", src)


if __name__ == "__main__":
    unittest.main()
