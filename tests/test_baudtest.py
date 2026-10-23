import unittest

from totem import baudtest
from totem.baudtest import RATES, STEPS, message, pro, run


class FakePort:
    """Records what is written and at which speed, and every change of speed."""
    def __init__(self):
        self._baud, self.log = 1200, []

    @property
    def baudrate(self): return self._baud

    @baudrate.setter
    def baudrate(self, value):
        self._baud = value
        self.log.append(("baud", value))

    def write(self, data): self.log.append(("write", self._baud, data))
    def flush(self): pass


class BaudTestTests(unittest.TestCase):
    def setUp(self):
        orig, baudtest.time.sleep = baudtest.time.sleep, lambda s: None
        self.addCleanup(setattr, baudtest.time, "sleep", orig)

    def writes(self, port):
        return [(e[1], e[2]) for e in port.log if e[0] == "write"]

    def test_the_speed_commands_are_the_teletel_ones(self):
        self.assertEqual(pro(4800), b"\x1b:kv")
        self.assertEqual(pro(9600), b"\x1b:k\x7f")
        self.assertEqual(pro(1200), b"\x1b:kd")
        self.assertEqual(set(RATES), {1200, 4800, 9600})

    def test_the_text_is_plain_printable_ascii_after_the_clear(self):
        for label, baud, _ in STEPS:
            body = message(label, baud)[len(baudtest.CLEAR):]
            self.assertTrue(all(b in (0x0D, 0x0A) or 32 <= b < 127 for b in body))
            self.assertIn(str(baud).encode(), body)

    def test_a_full_run_ends_with_the_port_at_1200_and_a_clear(self):
        port = FakePort()
        run(port)
        self.assertEqual(port.baudrate, 1200)
        self.assertEqual(self.writes(port)[-1], (1200, baudtest.CLEAR))

    def test_raw_steps_send_the_text_at_that_speed_without_any_command(self):
        port = FakePort()
        run(port, only=3)                                       # 4800 raw
        sent = self.writes(port)
        self.assertEqual(sent[0][0], 4800)
        self.assertNotIn(b"\x1b:k", sent[0][1])
        self.assertEqual(len([s for s in sent if b"\x1b:k" in s[1]]), 0)

    def test_command_steps_switch_the_terminal_first_and_bring_it_back_after(self):
        port = FakePort()
        run(port, only=5)                                       # 4800 with the command
        sent = self.writes(port)
        self.assertEqual(sent[0], (1200, pro(4800)))            # told at the old speed
        self.assertEqual(sent[1][0], 4800)                      # then the text at the new one
        self.assertEqual(sent[2], (4800, pro(1200)))            # and sent back at the speed it is now
        self.assertEqual(sent[-1], (1200, baudtest.CLEAR))

    def test_if_it_is_cut_short_the_terminal_is_still_taken_back(self):
        port = FakePort()
        calls = []

        def boom(seconds):
            calls.append(seconds)
            if len(calls) == 2:                                 # after the switch, during the text
                raise KeyboardInterrupt
        baudtest.time.sleep = boom
        with self.assertRaises(KeyboardInterrupt):
            run(port, only=6)                                   # 9600 with the command
        sent = self.writes(port)
        self.assertIn((9600, pro(1200)), sent)                  # the way back was sent
        self.assertEqual(port.baudrate, 1200)


if __name__ == "__main__":
    unittest.main()
