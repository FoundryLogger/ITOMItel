import unittest

from totem import logo
from totem.app import App, BODY, HEIGHT


class FakeShop:
    def collections(self):
        return []

    def refresh(self):
        pass


class LogoTests(unittest.TestCase):
    def test_compact_logo_is_40_wide_and_wide_logo_is_42(self):
        self.assertEqual({len(r) for r in logo.lines()}, {40})
        self.assertEqual({len(r) for r in logo.lines(compact=False)}, {42})
        self.assertEqual(len(logo.lines()), 12)

    def test_home_80_has_centred_logo_with_menu_below(self):
        screen = App(FakeShop()).screen()
        self.assertEqual(len(screen), HEIGHT)
        self.assertEqual({len(r) for r in screen}, {80})
        self.assertEqual(screen[0], "ITOMItel".center(80))
        self.assertEqual(set(screen[1]), {"-"})
        art = logo.lines(compact=False)
        self.assertTrue(all(screen[2 + i] == (" " * 19 + art[i]).ljust(80)
                            for i in range(12)))
        menu_rows = screen[15:19]                    # two columns: items 1-4 and 5-7
        self.assertTrue(all(r.startswith(" ") and r.strip() for r in menu_rows))
        text = "\n".join(screen)
        self.assertIn("1  Sfoglia le categorie", text)
        self.assertIn("5  Cerca un prodotto", text)
        self.assertIn("6  Credits", text)
        self.assertIn("7  Televideo RAI", text)

    def test_home_40_stacks_logo_over_menu(self):
        screen = App(FakeShop(), width=40).screen()
        self.assertEqual({len(r) for r in screen}, {40})
        self.assertEqual(screen[2:14], logo.lines())
        self.assertEqual(screen[0], "ITOMItel".center(40))
        self.assertLessEqual(12 + 7, BODY)


class HeaderTests(unittest.TestCase):
    def test_every_view_keeps_the_centred_header(self):
        from totem.app import GUIDA, Message, Search
        app = App(FakeShop())
        views = [app.screen()]
        app.key(GUIDA)
        views.append(app.screen())
        app.key("INDICE")
        app.key("5")
        views.append(app.screen())
        for w in (80, 40):
            self.assertEqual(App(FakeShop(), width=w).screen()[0], "ITOMItel".center(w))
        for screen in views[:2]:
            self.assertEqual(len(screen), HEIGHT)
            self.assertEqual(screen[0][36:44], "ITOMItel")
            self.assertEqual(set(screen[1]), {"-"})


class HeaderLayoutTests(unittest.TestCase):
    def test_title_left_header_centre_page_right(self):
        from totem.app import render
        row = render(80, "BESTSELLER", [], page=(0, 4))[0]
        self.assertEqual(len(row), 80)
        self.assertTrue(row.startswith("BESTSELLER "))
        self.assertEqual(row[36:44], "ITOMItel")
        self.assertTrue(row.endswith("1/4"))

    def test_no_page_number_for_a_single_page(self):
        from totem.app import render
        self.assertEqual(render(80, "GUIDA", [], page=(0, 1))[0].rstrip()[-8:], "ITOMItel")

    def test_long_titles_are_cut_before_the_header(self):
        from totem.app import render
        for w in (80, 40):
            row = render(w, "X" * 100, [], page=(11, 12))[0]
            self.assertEqual(len(row), w)
            self.assertEqual(row[(w - 8) // 2:(w - 8) // 2 + 8], "ITOMItel")
            self.assertEqual(row[(w - 8) // 2 - 1], " ")


class CreditsTests(unittest.TestCase):
    def _open(self, width):
        app = App(FakeShop(), width=width)
        app.key("6")
        return app

    def test_credits_has_the_full_text_on_80_columns(self):
        app = self._open(80)
        screen = app.screen()
        self.assertEqual(len(screen), HEIGHT)
        self.assertTrue(screen[0].startswith("CREDITS"))
        self.assertIn("ITOMItel", screen[0])
        text = " ".join(" ".join(screen).split())
        for phrase in ("ITOMItel è un progetto creato da ITOMI.studio",
                       "Alessandro Tullio e Michele Giorgi",
                       "Philips HCS 80/08 (Videotex/Minitel)",
                       "grazie alla connessione Wi-Fi",
                       "liberamente consultabile durante gli Open Days.",
                       "Il progetto è open source su GitHub:",
                       "https://github.com/itomistudio/ITOMItel"):
            self.assertIn(phrase, text)
        self.assertEqual(app.view.pages(), 2)   # thanks on page 1, technical sheet on page 2
        self.assertNotIn("SCHEDA TECNICA", text)

    def test_credits_pages_on_40_columns_without_losing_text(self):
        app = self._open(40)
        view, seen = app.view, []
        for _ in range(view.pages()):
            seen += [r.strip() for r in app.screen()[2:21]]
            app.key("SEGUENTE")
        self.assertGreater(view.pages(), 1)
        text = " ".join(" ".join(seen).split())
        self.assertIn("liberamente consultabile durante gli Open Days.", text)
        self.assertIn("È stato estremamente divertente", text)

    def test_technical_sheet_is_page_two_and_uses_the_real_line_settings(self):
        app = App(FakeShop())
        app.line_info = "1200 baud, 7 bit, parità pari, 1 stop"
        app.key("6")
        app.key("SEGUENTE")
        screen = app.screen()
        text = " ".join(" ".join(screen).split())
        self.assertIn("2/2", screen[0])
        for phrase in ("SCHEDA TECNICA", "Philips HCS 80/08", "CEPT P2/P3",
                       "Raspberry Pi 3 Model B", "1200 baud, 7 bit, parità pari, 1 stop"):
            self.assertIn(phrase, text)
        self.assertEqual({len(r) for r in screen}, {80})
        self.assertIn("tre fili dalla presa DIN", text)
        self.assertIn("senza adattatori", text)
        self.assertNotIn("USB", text)         # the USB-serial adapter was never used
        self.assertIn("sequenze ANSI", text)
        self.assertIn("i contenuti sono di RAI", text)
        self.assertEqual(app.view.pages(), 2)          # the sheet, with the serial line row, fits on one page

    def test_no_line_row_when_the_speed_is_not_known(self):
        app = App(FakeShop())          # console and web emulator have no serial line
        app.key("6")
        app.key("SEGUENTE")
        self.assertNotIn("Linea seriale", "\n".join(app.screen()))

    def test_annul_returns_to_the_menu(self):
        app = self._open(80)
        app.key("ANNUL")
        self.assertEqual(app.screen()[0].strip(), "ITOMItel")


if __name__ == "__main__":
    unittest.main()
