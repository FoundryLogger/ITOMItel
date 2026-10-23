"""Check what a real ANSI terminal would show after our bytes, and that
layout widths are right once accents and the euro sign are spelled out."""
import unittest
from decimal import Decimal

from totem import text
from totem.app import App
from totem.shop import Product, Variant
from totem.terminal import encode_screen, estimate_seconds


class Ansi:
    """Just enough of an ANSI terminal: clear, home, cursor jumps, erase to end
    of line, CR/LF and plain text. Flags text written past the last column."""

    def __init__(self, w=80, h=24):
        self.w, self.h = w, h
        self.grid = [[" "] * w for _ in range(h)]
        self.r = self.c = 0
        self.overflow = False
        self.top, self.bottom = 0, h - 1            # scroll region (rows, 0-based, inclusive)

    def feed(self, data: bytes):
        i = 0
        while i < len(data):
            b = data[i]
            if b == 0x1B and data[i + 1:i + 2] == b"[":
                j = i + 2
                while chr(data[j]) not in "HJKmLMr":
                    j += 1
                params, cmd = data[i + 2:j].decode(), chr(data[j])
                if cmd == "J" and params == "2":
                    self.grid = [[" "] * self.w for _ in range(self.h)]
                elif cmd == "H":
                    parts = [int(x) if x else 1 for x in params.split(";")] if params else [1, 1]
                    self.r, self.c = parts[0] - 1, (parts[1] if len(parts) > 1 else 1) - 1
                elif cmd == "K":
                    for k in range(self.c, self.w):
                        self.grid[self.r][k] = " "
                elif cmd == "r":                      # scroll region, "" resets it
                    parts = [int(x) for x in params.split(";")] if params else [1, self.h]
                    self.top, self.bottom = parts[0] - 1, parts[1] - 1
                elif cmd in "LM" and self.top <= self.r <= self.bottom:
                    n = int(params or 1)
                    for _ in range(n):
                        if cmd == "M":                # delete the line: the ones below move up
                            del self.grid[self.r]
                            self.grid.insert(self.bottom, [" "] * self.w)
                        else:                         # insert a blank line: the ones below move down
                            del self.grid[self.bottom]
                            self.grid.insert(self.r, [" "] * self.w)
                i = j + 1
            elif b == 0x0D:
                self.c, i = 0, i + 1
            elif b == 0x0A:
                self.r, i = self.r + 1, i + 1
            else:
                if self.c >= self.w:
                    self.overflow = True
                else:
                    self.grid[self.r][self.c] = chr(b)
                    self.c += 1
                i += 1

    def rows(self):
        return ["".join(r).rstrip() for r in self.grid]


def product(title, price, available=True, was=None, n_variants=1):
    variants = [Variant(f"Variante {i} è bella", Decimal(price), Decimal(was) if was else None, available)
                for i in range(n_variants)]
    return Product(id=hash(title) % 10**6, handle=title.lower().replace(" ", "-"), title=title,
                   vendor="ITOMI", product_type="Libri", tags=[],
                   description="Perché è così: il caffè è già pronto. Costa 5 € o più.",
                   published_at="2026-01-01", variants=variants)


class FakeShop:
    products = [product("Quaderno à righe", "6.99", n_variants=3),
                product("PIXEL.01 – Terza Ristampa", "44.99", was="59.99", n_variants=2),
                product("Esaurito è un caso", "9.00", available=False)]

    def collections(self):
        return []

    def refresh(self):
        pass

    def newest(self):
        return list(self.products)

    def collection_products(self, handle):
        return list(self.products)

    def search(self, q):
        return list(self.products)


class AsciiLayoutTests(unittest.TestCase):
    def setUp(self):
        text.set_ascii_only(True)
        self.addCleanup(text.set_ascii_only, False)

    def screens(self, width=80):
        app = App(FakeShop(), width=width)
        out = [app.screen()]                    # home
        app.key("2")                            # novita' list
        out.append(app.screen())
        app.key("1")                            # product detail
        out.append(app.screen())
        app.key("SEGUENTE")
        out.append(app.screen())
        app.key("INDICE")
        app.key("0")                            # credits
        out.append(app.screen())
        app.key("SEGUENTE")
        out.append(app.screen())
        return out

    def test_every_row_is_exactly_the_screen_width_and_plain_ascii(self):
        for width in (80, 40):
            for screen in self.screens(width):
                for row in screen:
                    self.assertEqual(len(row), width, row)
                    self.assertTrue(row.isascii(), row)

    def test_prices_keep_their_right_edge(self):
        app = App(FakeShop())
        app.key("2")
        rows = [r for r in app.screen() if "Quaderno" in r or "PIXEL" in r]
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertTrue(r.endswith("EUR"), r)      # not cut, not wrapped
            self.assertIn("a'" if "Quaderno" in r else "PIXEL", r)


class TerminalOutputTests(unittest.TestCase):
    def setUp(self):
        text.set_ascii_only(True)
        self.addCleanup(text.set_ascii_only, False)
        app = App(FakeShop())
        shots = [app.screen()]
        for key in ("2", "1", "SEGUENTE", "INDICE", "0", "SEGUENTE", "ANNUL", "5", "c", "i", "INDICE"):
            app.key(key)
            shots.append(app.screen())
        self.shots = shots

    def test_full_draw_reproduces_each_screen(self):
        for rows in self.shots:
            t = Ansi()
            t.feed(encode_screen(rows, None, "ansi"))
            self.assertFalse(t.overflow)
            self.assertEqual(t.rows(), [r.rstrip() for r in rows])

    def test_diffs_between_consecutive_screens_reproduce_each_screen(self):
        t = Ansi()
        t.feed(encode_screen(self.shots[0], None, "ansi"))
        for prev, rows in zip(self.shots, self.shots[1:]):
            t.feed(encode_screen(rows, prev, "ansi"))
            self.assertFalse(t.overflow)
            self.assertEqual(t.rows(), [r.rstrip() for r in rows])

    def test_home_is_well_under_the_old_size(self):
        data = encode_screen(self.shots[0], None, "ansi")
        self.assertLess(len(data), 1000)                  # was about 1300 bytes
        self.assertLess(estimate_seconds(data), 8.5)


if __name__ == "__main__":
    unittest.main()
