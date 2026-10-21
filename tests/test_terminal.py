"""Offline tests for the serial backend: python3 -m unittest discover tests"""
import unittest

from totem.app import (ANNUL, CORREZIONE, INDICE, INVIO, SEGUENTE, App, render)
from totem.terminal import (KeyDecoder, SerialTerminal, encode_screen,
                            estimate_seconds, to_ascii)


class FakeShop:
    """Just enough of Shop for the Home screen."""
    def collections(self):
        return []

    def refresh(self):
        pass


class FakePort:
    def __init__(self):
        self.out = b""

    def write(self, b):
        self.out += b


def screen(*lines, w=40):
    return render(w, "TITOLO", list(lines), hint="hint", keys="keys")


class EncodeTests(unittest.TestCase):
    def test_to_ascii_spells_out_accents_and_euro(self):
        self.assertEqual(to_ascii("Novità 4,99€ è"), "Novita' 4,99EUR e'")

    def test_plain_trims_trailing_spaces_and_has_24_rows(self):
        data = encode_screen(screen("a"), None, "plain", margin=0)
        self.assertEqual(data.count(b"\r\n"), 24)  # leading CRLF + 23 separators
        self.assertNotIn(b"  \r\n", data)

    def test_ansi_diff_sends_only_changed_rows(self):
        a, b = screen("uno", "due"), screen("uno", "tre")
        full = encode_screen(b, None, "ansi", margin=0)
        diff = encode_screen(b, a, "ansi", margin=0)
        self.assertLess(len(diff), len(full))
        self.assertIn(b"tre", diff)
        self.assertNotIn(b"uno", diff)

    def test_identical_screens_send_only_cursor_park(self):
        a = screen("uno")
        self.assertEqual(encode_screen(a, a, "ansi", 0), b"\x1b[24;40H")

    def test_cursor_parks_in_the_last_column_of_an_80_column_screen(self):
        a, b = screen("uno", w=80), screen("due", w=80)
        self.assertTrue(encode_screen(b, a, "ansi", 0).endswith(b"\x1b[24;80H"))

    def test_margin_centres_text(self):
        data = encode_screen(screen("x"), None, "ff", margin=20)
        self.assertIn(b" " * 20 + b"TITOLO", data)

    def test_full_redraw_estimate_is_seconds_not_milliseconds(self):
        data = encode_screen(screen("x" * 40, "y" * 40), None, "ff", margin=20)
        self.assertGreater(estimate_seconds(data, 1200), 2)

    def test_terminal_remembers_previous_screen(self):
        port = FakePort()
        t = SerialTerminal(port, "ansi", margin=0)
        t.draw(screen("uno", "due"))
        first = len(port.out)
        t.draw(screen("uno", "due"))
        self.assertLess(len(port.out) - first, 20)


class DecoderTests(unittest.TestCase):
    def test_printable_chars_and_defaults(self):
        d = KeyDecoder()
        self.assertEqual(d.feed(b"ab\r\x08\t"), ["a", "b", INVIO, CORREZIONE, SEGUENTE])

    def test_learned_multibyte_sequence(self):
        d = KeyDecoder({INDICE: [b"\x1b[H"]})
        self.assertEqual(d.feed(b"\x1b["), [])          # waits for more
        self.assertEqual(d.feed(b"H"), [INDICE])

    def test_lone_prefix_resolves_on_flush(self):
        d = KeyDecoder({ANNUL: [b"\x1b"], INDICE: [b"\x1b[H"]})
        self.assertEqual(d.feed(b"\x1b"), [])
        self.assertEqual(d.flush(), [ANNUL])

    def test_unknown_control_bytes_are_dropped(self):
        d = KeyDecoder()
        self.assertEqual(d.feed(b"\x01a\x02"), ["a"])

    def test_text_before_sequence(self):
        d = KeyDecoder({INDICE: [b"\x1b[H"]})
        self.assertEqual(d.feed(b"x\x1b[H"), ["x", INDICE])


class AppOverSerialTests(unittest.TestCase):
    def test_keys_drive_app_and_redraw(self):
        app = App(FakeShop())  # 80 columns
        port = FakePort()
        term = SerialTerminal(port, "ansi", margin=0)
        term.draw(app.screen(), full=True)
        port.out = b""
        for k in KeyDecoder().feed(b"5"):   # "Cerca" on the home screen
            app.key(k)
        term.draw(app.screen())
        self.assertIn(b"CERCA", port.out)


if __name__ == "__main__":
    unittest.main()
