import unittest

from test_encoding import Ansi
from totem import scrolltest
from totem.scrolltest import TESTS, setup


class ScrollTestTests(unittest.TestCase):
    def test_what_each_test_claims_is_what_a_standard_terminal_shows(self):
        """If the real terminal does what ANSI says, row 2 of the test is true."""
        for name, caption, ops, expected in TESTS:
            t = Ansi()
            t.feed(setup(name, caption, expected))
            t.feed(ops)
            rows = t.rows()
            for row, start in expected.items():
                self.assertEqual(rows[row - 1][:len(start)] if start else rows[row - 1], start,
                                 (name, row))

    def test_the_screen_fits_and_names_the_test_and_the_expectation(self):
        for name, caption, ops, expected in TESTS:
            t = Ansi()
            t.feed(setup(name, caption, expected))
            rows = t.rows()
            self.assertFalse(t.overflow)
            self.assertTrue(rows[0].startswith(f"TEST {name}:"))
            self.assertTrue(rows[1].startswith("ATTESO:"))
            self.assertEqual(rows[2], "03 riga di prova")
            self.assertEqual(rows[23], "24 riga di prova")

    def test_run_plays_each_test_and_clears_at_the_end(self):
        class Port:
            def __init__(self): self.out = []
            def write(self, b): self.out.append(b)
            def flush(self): pass
        sleeps, port = [], Port()
        orig, scrolltest.time.sleep = scrolltest.time.sleep, sleeps.append
        try:
            scrolltest.run(port, pause=7)
        finally:
            scrolltest.time.sleep = orig
        self.assertEqual(sleeps, [1.0, 7] * len(TESTS))
        self.assertEqual(port.out[-1], scrolltest.CLEAR)
        only = Port()
        scrolltest.time.sleep = lambda s: None
        try:
            scrolltest.run(only, only="c")
        finally:
            scrolltest.time.sleep = orig
        self.assertEqual(len(only.out), 3)                     # one test: screen, operation, final clear


if __name__ == "__main__":
    unittest.main()
