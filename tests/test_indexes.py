"""Lists are indexed 1-9 and then A-J: one line per item, 19 items per page."""
import unittest
from decimal import Decimal

from totem import text
from totem.app import App, BODY, HEIGHT, INDEX_KEYS, chosen
from totem.shop import Collection, Product, Variant


def product(n, price="10.00", was=None, available=True):
    return Product(id=n, handle=f"p{n}", title=f"Prodotto numero {n:02d}", vendor="V", product_type="Libri",
                   tags=[], description="d", published_at="2026-01-01",
                   variants=[Variant("x", Decimal(price), Decimal(was) if was else None, available)])


class Shop:
    """25 products and 44 categories: more than one page of either."""
    def __init__(self):
        self.products = [product(i) for i in range(1, 26)]
        self.cats = [Collection(f"c{i}", f"Categoria {i:02d} è", 3) for i in range(1, 45)]

    def collections(self): return self.cats
    def collection_products(self, handle): return self.products
    def newest(self, n=18): return self.products
    def refresh(self): pass


def lines_of(screen):
    return [r for r in screen[2:2 + BODY] if r.strip()]


class IndexKeyTests(unittest.TestCase):
    def test_the_choices_are_1_to_9_then_letters(self):
        self.assertTrue(INDEX_KEYS.startswith("123456789ABCDEFGHIJ"))
        self.assertEqual(chosen("1", 0, 19), 0)
        self.assertEqual(chosen("9", 0, 19), 8)
        self.assertEqual(chosen("a", 0, 19), 9)             # lower case works too
        self.assertEqual(chosen("J", 0, 19), 18)
        self.assertIsNone(chosen("K", 0, 19))               # past the 19 rows of a page
        self.assertEqual(chosen("A", 2, 19), 2 * 19 + 9)   # on the third page
        for bad in ("0", "SEGUENTE", "", "?"):
            self.assertIsNone(chosen(bad, 0, 19))


class ListLayoutTests(unittest.TestCase):
    def open_new(self, width=80):
        app = App(Shop(), width=width, loading_delay=5)
        app.key("2")
        return app

    def test_a_page_has_19_items_labelled_1_to_9_and_a_to_j_filling_the_body(self):
        screen = self.open_new().screen()
        rows = lines_of(screen)
        self.assertEqual(len(rows), 19)
        self.assertEqual([r[1] for r in rows], list("123456789ABCDEFGHIJ"))
        self.assertIn("Prodotto numero 19", rows[18])
        self.assertIn("1/2", screen[0])

    def test_the_hint_mentions_letters_only_when_there_are_more_than_nine_choices(self):
        app = self.open_new()
        self.assertIn("numero o la lettera", app.screen()[-2])
        app.key("SEGUENTE")                                  # 6 items on the second page
        self.assertIn("numero desiderato", app.screen()[-2])

    def test_letters_pick_items_and_the_second_page_starts_again_at_1(self):
        app = self.open_new()
        app.key("a")                                         # the tenth product
        self.assertIn("Prodotto numero 10", "\n".join(app.screen()))
        app.key("ANNUL")
        app.key("j")                                         # the 19th
        self.assertIn("Prodotto numero 19", "\n".join(app.screen()))
        app.key("ANNUL")
        app.key("SEGUENTE")
        app.key("1")                                         # the 20th
        self.assertIn("Prodotto numero 20", "\n".join(app.screen()))

    def test_a_letter_with_no_item_behind_it_does_nothing(self):
        app = self.open_new()
        app.key("SEGUENTE")                                  # 6 items: 1-6
        before = app.screen()
        app.key("h")
        self.assertEqual(app.screen(), before)
        app.key("K")
        self.assertEqual(app.screen(), before)

    def test_the_shop_categories_use_the_same_indexes(self):
        app = App(Shop(), loading_delay=5)
        app.key("1")
        screen = app.screen()
        rows = lines_of(screen)
        self.assertEqual([r[1] for r in rows], list("123456789ABCDEFGHIJ"))
        self.assertIn("1/3", screen[0])                      # 44 categories: three pages
        app.key("b")
        self.assertTrue(app.screen()[0].startswith("CATEGORIA 11"))

    def test_a_sale_is_marked_in_the_price_column(self):
        shop = Shop()
        shop.products = [product(1, "24.99", was="39.99"), product(2, available=False), product(3)]
        app = App(shop, loading_delay=5)
        app.key("2")
        rows = lines_of(app.screen())
        self.assertTrue(rows[0].rstrip().endswith("offerta 24,99€"), rows[0])
        self.assertTrue(rows[1].rstrip().endswith("esaurito"))
        self.assertTrue(rows[2].rstrip().endswith("10,00€"))

    def test_layout_is_exact_in_ascii_mode_on_80_and_40_columns(self):
        text.set_ascii_only(True)
        self.addCleanup(text.set_ascii_only, False)
        for width in (80, 40):
            app = App(Shop(), width=width, loading_delay=5)
            shots = []
            app.key("1"); shots.append(app.screen())         # categories, with an accent in every name
            app.key("ANNUL"); app.key("2"); shots.append(app.screen())
            app.key("SEGUENTE"); shots.append(app.screen())
            for screen in shots:
                self.assertEqual(len(screen), HEIGHT)
                for row in screen:
                    self.assertEqual(len(row), width, row)
                    self.assertTrue(row.isascii(), row)


if __name__ == "__main__":
    unittest.main()
