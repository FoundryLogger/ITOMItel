"""Screens and navigation for the totem.

The app is a pure state machine: feed it keys with App.key(), read the
current screen with App.screen(). It knows nothing about the serial port,
so the same code drives the console preview and the real terminal.

The screen is 80 columns by 24 rows (the terminal's Ascii 80 col mode).
App(width=40) gives the compact layout for Ascii 40 col.
"""
from __future__ import annotations

import threading

from . import logo
from .blog import Category, Post as StoryPost, WordPressClient
from .settings import ORDER, SPECS, Settings
from .shop import Product, Shop
from .televideo import FIRST_PAGE, LAST_PAGE, SOURCE, TelevideoClient
from .text import fit, money, sanitize, wrap

HEIGHT = 24
BODY = 19  # rows 2..20: header and rule above; rule, hint and keys below
HEADER = "ITOMItel"

# Named keys. Anything else is a single typed character.
INDICE, PRECEDENTE, SEGUENTE = "INDICE", "PRECEDENTE", "SEGUENTE"
INVIO, ANNUL, CORREZIONE = "INVIO", "ANNUL", "CORREZIONE"
GUIDA, RIPETIZ = "GUIDA", "RIPETIZ"

STORE_NAME = "ITOMI"
STORE_DOMAIN = "itomi.shop"

# Sites read through the WordPress API, key -> how they are shown. "category" is the one
# category to list; None means the reader first picks one (a city, for Nerdvana).
WP_SOURCES = {
    "stories": dict(site="https://www.whatisepic.it", category="storie", sort="date",
                    show_dates=True, list_title="STORIE EPIC", detail_title="STORIA",
                    index_name="Storie"),
    "nerdvana": dict(site="https://nerdvanaguides.com", category=None, sort="title",
                     show_dates=False, list_title="NERDVANA", detail_title="GUIDA",
                     index_name="Nerdvana"),
}

# (label, kind, argument) for the shortcuts on the home screen.
HOME_ITEMS = [
    ("Sfoglia Catalogo", "categories", None),
    ("Novità", "new", None),
    ("Bestseller", "collection", "bestseller"),
    ("In offerta", "collection", "in-offerta"),
    ("Cerca un prodotto", "search", None),
    ("Storie di EPIC", "stories", None),
    ("Guide Nerdvana", "nerdvana", None),
    ("Televideo RAI", "televideo", None),
    ("Impostazioni", "settings", None),
    ("Credits", "credits", None),
]

# Shorter names for the 40-column menu, where two columns have to fit side by side.
SHORT_LABELS = {"categories": "Catalogo", "search": "Cerca", "stories": "Storie EPIC",
                "nerdvana": "Nerdvana", "televideo": "Televideo", "settings": "Impostaz."}

CREDITS_TEXT = """\
ITOMItel è un progetto creato da ITOMI.studio con l'ausilio di Claude Code. La parte hardware è basata su un Raspberry Pi collegato via porta seriale a un terminale Videotel SIP Philips HCS 80/08 (Videotex/Minitel).

È possibile sfogliare e ricercare il catalogo di ITOMI.shop in tempo reale grazie alla connessione Wi-Fi del Raspberry Pi, che trasforma in schermate Videotex i prodotti del sito ufficiale.

Si ringraziano Alessandro Tullio e Michele Giorgi per la consulenza iniziale.

È stato estremamente divertente sviluppare questo progetto hardware e software. Il terminale è ora operativo all'interno dell'ITOMI Studio5 e liberamente consultabile durante gli Open Days.

Il progetto è open source su GitHub:
https://github.com/itomistudio/ITOMItel"""


def render(w: int, title: str, body: list[str], hint: str = "", keys: str = "",
           page: tuple[int, int] | None = None) -> list[str]:
    """Lay out a w x 24 screen.

    Row 0 is the header: the page title on the left, ITOMItel in the centre,
    the page number on the right when there is more than one page. Then a
    rule, the body, a rule, a hint line and a key line.
    """
    tag = f"{page[0] + 1}/{page[1]}" if page and page[1] > 1 else ""
    head = list(HEADER.center(w))
    room = (w - len(HEADER)) // 2 - 2  # keep two spaces between title and header
    left = fit(sanitize(title), room) if room > 0 else ""
    head[:len(left)] = left
    head[w - len(tag):] = tag
    rows = ["".join(head), "-" * w]
    rows += [fit(sanitize(l), w).ljust(w) for l in body[:BODY]]
    rows += [" " * w] * (BODY - len(body[:BODY]))
    rows += ["-" * w, fit(sanitize(hint), w).ljust(w), fit(sanitize(keys), w).ljust(w)]
    assert len(rows) == HEIGHT
    return rows


def loading_screen(w: int, label: str = "") -> list[str]:
    """A deliberately cheap screen: at 1200 baud every character costs time.

    Just the header and two centred lines, no rules and no key hints.
    """
    rows = [HEADER.center(w)] + [" " * w] * (HEIGHT - 1)
    rows[10] = "Caricamento in corso...".center(w)
    if label:
        rows[12] = fit(sanitize(label), w).center(w)
    return rows


def pick(w: int, long: str, short: str) -> str:
    """The long wording when there's room, the short one on 40 columns."""
    return long if w >= 80 else short


class View:
    """Base class. on_key() returns True when it handled the key."""

    def __init__(self, app: "App"):
        self.app = app

    @property
    def w(self) -> int:
        return self.app.w

    def screen(self) -> list[str]:
        raise NotImplementedError

    def on_key(self, k: str) -> bool:
        return False


class Message(View):
    def __init__(self, app, title, lines):
        super().__init__(app)
        self.title, self.lines = title, lines

    def screen(self):
        return render(self.w, self.title, self.lines,
                      keys=pick(self.w, "Annul.=torna indietro   Indice=menu iniziale",
                                "Annul=indietro  Indice=menu"))


class Paged(View):
    """A view whose content is split in pages."""
    page = 0
    per_page = BODY

    def total(self) -> int:
        return 0

    def pages(self) -> int:
        return max(1, -(-self.total() // self.per_page))

    def paging_keys(self) -> str:
        if self.pages() == 1:
            return pick(self.w, "Annul.=torna indietro   Indice=menu iniziale",
                        "Annul=indietro  Indice=menu")
        return pick(self.w, "Seguente=pagina successiva   Precedente=pagina precedente"
                            "   Indice=menu",
                    "Seguente/Precedente=pagine  Indice=menu")

    def on_key(self, k):
        if k == SEGUENTE:
            self.page = min(self.page + 1, self.pages() - 1)
            return True
        if k == PRECEDENTE:
            if self.page == 0:
                return False  # lets the app go back one screen
            self.page -= 1
            return True
        return False


class Home(View):
    def __init__(self, app):
        super().__init__(app)
        self.items = list(HOME_ITEMS)

    def screen(self):
        wide = self.w >= 80
        menu = []
        for i, (label, kind, _) in enumerate(self.items, 1):
            # sanitize first: "Novità" is one character longer once spelled in ASCII, and the
            # columns are measured here, before render() sanitizes the screen
            menu.append(sanitize(f"{i % 10}  {label if wide else (SHORT_LABELS.get(kind) or label)}"))
        half = (len(menu) + 1) // 2
        left, right = menu[:half], menu[half:]
        wl, gap = max(map(len, left)), 8 if wide else 3
        wr = max(map(len, right)) if right else 0
        art = logo.lines(compact=not wide)
        # Logo centred (42 columns on 80, 40 on 40), the menu below it in two centred columns.
        pad = " " * ((self.w - len(art[0])) // 2)
        menu_pad = " " * max(0, (self.w - (wl + gap + wr)) // 2)
        rows = [menu_pad + left[i].ljust(wl) + (" " * gap + right[i] if i < len(right) else "")
                for i in range(len(left))]
        body = [pad + row for row in art] + ([""] if wide else []) + rows
        keys = "Guida=aiuto"
        return render(self.w, "", body, hint="Premi il numero desiderato",
                      keys=keys.ljust(self.w - len(STORE_DOMAIN)) + STORE_DOMAIN)

    def on_key(self, k):
        # 1..9 choose the first nine entries, 0 the tenth (the keypad of a phone)
        if k.isdigit() and (int(k) - 1) % 10 < len(self.items):
            label, kind, arg = self.items[(int(k) - 1) % 10]
            app = self.app
            if kind == "categories":
                app.push(app.slow(label, lambda: CategoryList(app)))
            elif kind == "new":
                app.push(app.slow(label, lambda: ProductList(
                    app, label, app.shop.newest())))
            elif kind == "collection":
                app.push(app.slow(label, lambda: ProductList(
                    app, dict(app.collection_titles()).get(arg, arg).title(),
                    app.shop.collection_products(arg))))
            elif kind == "search":
                self.app.push(Search(self.app))
            elif kind == "credits":
                self.app.push(Credits(self.app))
            elif kind == "settings":
                self.app.push(SettingsView(self.app))
            elif kind == "televideo":
                app.push(app.slow(label, lambda: Televideo(app)))
            elif kind in WP_SOURCES:
                app.push(app.slow(label, lambda: open_source(app, kind)))
            return True
        return False


class Credits(Paged):
    per_page = BODY - 1  # a blank row sits above the text

    def __init__(self, app):
        super().__init__(app)
        self.lines = [("  " + l).rstrip()
                      for l in wrap(sanitize(CREDITS_TEXT), self.w - 4)]
        while len(self.lines) % self.per_page:   # the technical sheet starts a new page
            self.lines.append("")
        self.lines += self._tech_sheet()

    def _tech_sheet(self) -> list[str]:
        """Label/value rows with the values wrapped under each other."""
        label_w = 14
        rows = [("Terminale", "Philips HCS 80/08, terminale Videotel SIP costruito dalla "
                              "Radiotechnique Industrielle et Commerciale (Suresnes, Francia)"),
                ("Standard", "Videotex multistandard: CEPT P2/P3, ASCII 40 e 80 col."),
                ("Schermo", f"monocromatico, in modalità ASCII a {self.w} colonne"),
                ("Computer", "Raspberry Pi 3 Model B, collegato in Wi-Fi alla rete"),
                ("Collegamento", "tre fili dalla presa DIN a 5 poli del terminale ai pin "
                                 "della seriale del Raspberry Pi, a 3,3 V e senza adattatori")]
        if self.app.line_info:
            rows.append(("Linea seriale", self.app.line_info))
        rows.append(("Disegno", "sequenze ANSI per posizionare il cursore: si "
                                "ridisegnano solo le righe cambiate"))
        rows.append(("Televideo", "pagine RAI lette solo su richiesta e tenute in memoria "
                                  "2 minuti: i contenuti sono di RAI"))
        rows.append(("Software", "Python 3. Il catalogo di ITOMI.shop viene letto in tempo "
                                 "reale e tenuto in memoria per 5 minuti: se la rete cade, "
                                 "si usa l'ultima copia salvata"))
        out = ["  SCHEDA TECNICA", ""]
        for label, value in rows:
            chunks = wrap(sanitize(value), self.w - 4 - label_w)
            for i, chunk in enumerate(chunks):
                out.append("  " + (label if i == 0 else "").ljust(label_w) + chunk)
        return out

    def total(self):
        return len(self.lines)

    def screen(self):
        start = self.page * self.per_page
        return render(self.w, "CREDITS", [""] + self.lines[start:start + self.per_page],
                      keys=self.paging_keys(), page=(self.page, self.pages()))


class CategoryList(Paged):
    per_page = 9

    def __init__(self, app):
        super().__init__(app)
        self.items = app.shop.collections()

    def total(self):
        return len(self.items)

    def screen(self):
        w = self.w
        start = self.page * self.per_page
        body = [""]
        for i, c in enumerate(self.items[start:start + self.per_page], 1):
            count = f"({c.count})"
            body.append(f" {i}  {fit(sanitize(c.title), w - 8 - len(count))}".ljust(w - len(count) - 1)
                        + " " + count)
        return render(w, "CATEGORIE", body, hint="Premi il numero desiderato",
                      keys=self.paging_keys(), page=(self.page, self.pages()))

    def on_key(self, k):
        if k.isdigit() and k != "0":
            i = self.page * self.per_page + int(k) - 1
            if i < len(self.items):
                c, app = self.items[i], self.app
                app.push(app.slow(c.title, lambda: ProductList(
                    app, c.title, app.shop.collection_products(c.handle))))
            return True
        return super().on_key(k)


class ProductList(Paged):
    per_page = 9

    def __init__(self, app, title, products: list[Product]):
        super().__init__(app)
        self.title, self.items = title, products

    def total(self):
        return len(self.items)

    @staticmethod
    def _price(p: Product) -> str:
        if not p.available:
            return "esaurito"
        pre = "da " if p.price_from != p.price_to else ""
        return sanitize(f"{pre}{money(p.price_from)}€")

    @staticmethod
    def _info(p: Product) -> str:
        bits = [p.product_type or "Prodotto"]
        if len(p.variants) > 1:
            bits.append(f"{len(p.variants)} varianti")
        if p.on_sale and p.available:
            bits.append("IN OFFERTA")
        return sanitize(" - ".join(bits))

    def screen(self):
        w = self.w
        if not self.items:
            return render(w, self.title, ["", "  Nessun prodotto trovato."],
                          keys=pick(w, "Annul.=torna indietro   Indice=menu iniziale",
                                    "Annul=indietro  Indice=menu"))
        start = self.page * self.per_page
        body = [""]
        for i, p in enumerate(self.items[start:start + self.per_page], 1):
            price = self._price(p)
            name = fit(sanitize(p.title), w - 5 - len(price))
            body.append(f" {i}  {name}".ljust(w - len(price) - 1) + " " + price)
            if w >= 80:  # room for a second line per product
                body.append("    " + self._info(p))
        return render(w, self.title.upper(), body, hint="Premi il numero desiderato",
                      keys=self.paging_keys(), page=(self.page, self.pages()))

    def on_key(self, k):
        if k.isdigit() and k != "0":
            i = self.page * self.per_page + int(k) - 1
            if i < len(self.items):
                self.app.push(ProductDetail(self.app, self.items[i]))
            return True
        return super().on_key(k)


class ProductDetail(Paged):
    def __init__(self, app, product: Product):
        super().__init__(app)
        self.p = product
        self.lines = self._build()

    def total(self):
        return len(self.lines)

    def _build(self) -> list[str]:
        w, p = self.w, self.p
        lines = wrap(sanitize(p.title), w) + [""]
        if p.available:
            pre = "da " if p.price_from != p.price_to else ""
            price = sanitize(f"{pre}{money(p.price_from)}€")
            if p.on_sale:
                was = max(v.compare_at for v in p.variants if v.compare_at)
                price += sanitize(f"  (era {money(was)}€)")
            lines.append(price)
        else:
            lines.append("Esaurito")
        if len(p.variants) > 1:
            lines.append("")
            for v in p.variants[:8]:
                right = sanitize(money(v.price) + "€") if v.available else "esaurito"
                name = fit(sanitize(v.title), w - len(right) - 3)
                lines.append(f"- {name}".ljust(w - len(right)) + right)
            if len(p.variants) > 8:
                n = len(p.variants) - 8
                lines.append(f"  ...e altre {n} " + ("variante" if n == 1 else "varianti"))
        lines += ["", f"{STORE_DOMAIN}/products/{p.handle}", ""]
        lines += wrap(sanitize(p.description), w)
        return lines

    def screen(self):
        start = self.page * BODY
        return render(self.w, self.p.product_type or "PRODOTTO",
                      self.lines[start:start + BODY], keys=self.paging_keys(),
                      page=(self.page, self.pages()))


def site_keys(w: int, client: WordPressClient, with_zero: bool) -> str:
    """The key line of the pages of a WordPress site; 0 goes back to the site's index."""
    zero = f"   0=indice {client.index_name}" if with_zero else ""
    if w >= 80:
        return f"Seguente/Precedente=pagine{zero}   Indice=menu"
    return "Segu/Prec  0=indice  Indice=menu" if with_zero else "Seguente/Precedente=pagine  Indice=menu"


def open_source(app, key: str) -> View:
    """The first screen of a WordPress source: the articles of its one category,
    or the list of categories (cities) when the reader has to pick one."""
    client = app.sources[key]
    return StoryList(app, client, client.category) if client.category else CityList(app, client)


class CityList(Paged):
    """The categories of a WordPress site (the cities of Nerdvana), with their article counts."""
    per_page = 9
    is_index = True            # what the 0 key goes back to

    def __init__(self, app, client: WordPressClient):
        super().__init__(app)
        self.client = client
        self.items: list[Category] = client.categories()

    def total(self):
        return len(self.items)

    def screen(self):
        w, start = self.w, self.page * self.per_page
        body = [""]
        for i, c in enumerate(self.items[start:start + self.per_page], 1):
            count = f"({c.count})"
            body.append(f" {i}  {fit(sanitize(c.name), w - 8 - len(count))}".ljust(w - len(count) - 1)
                        + " " + count)
        return render(w, self.client.list_title, body, hint="Premi il numero desiderato",
                      keys=site_keys(w, self.client, with_zero=False), page=(self.page, self.pages()))

    def on_key(self, k):
        if k == "0":
            self.app.go_to_site_index()
            return True
        if k.isdigit():
            i = self.page * self.per_page + int(k) - 1
            if i < len(self.items):
                c, app, client = self.items[i], self.app, self.client
                app.push(app.slow(c.name, lambda: StoryList(
                    app, client, c.slug, f"{client.list_title} - {c.name.upper()}")))
            return True
        return super().on_key(k)


class StoryList(Paged):
    """The articles of one category: newest first, or A-Z, as the site is set up."""
    per_page = 9

    def __init__(self, app, client: WordPressClient, slug: str | None = None, title: str | None = None):
        super().__init__(app)
        self.client, self.title = client, title or client.list_title
        self.items: list[StoryPost] = client.posts(slug)
        # On a site with one fixed category this list IS the index; on Nerdvana the index
        # is the list of cities and this is one city's guides.
        self.is_index = slug is not None and slug == client.category

    def total(self):
        return len(self.items)

    def screen(self):
        w, start, client = self.w, self.page * self.per_page, self.client
        if not self.items:
            return render(w, self.title, ["", "  Nessun articolo trovato."],
                          keys=pick(w, "Annul.=torna indietro   Indice=menu iniziale",
                                    "Annul=indietro  Indice=menu"))
        body = [""]
        for i, p in enumerate(self.items[start:start + self.per_page], 1):
            date = p.short_date if client.show_dates else ""
            name = fit(sanitize(p.title), w - 6 - len(date))
            body.append((f" {i}  {name}".ljust(w - len(date) - 1) + " " + date) if date else f" {i}  {name}")
        return render(w, self.title, body,
                      hint=pick(w, f"Premi il numero desiderato   (fonte: {client.domain})",
                                "Premi il numero desiderato"),
                      keys=site_keys(w, client, with_zero=not self.is_index),
                      page=(self.page, self.pages()))

    def on_key(self, k):
        if k == "0":
            self.app.go_to_site_index()
            return True
        if k.isdigit():
            i = self.page * self.per_page + int(k) - 1
            if i < len(self.items):
                post, app, client = self.items[i], self.app, self.client
                app.push(app.slow(post.title, lambda: StoryDetail(app, post, client)))
            return True
        return super().on_key(k)


class StoryDetail(Paged):
    """One article: title, date (if it means anything) and text, paged."""

    def __init__(self, app, post: StoryPost, client: WordPressClient):
        super().__init__(app)
        self.post, self.client = post, client
        article = client.article(post.id)
        w = self.w
        self.lines = [("  " + l).rstrip() for l in wrap(sanitize(post.title.upper()), w - 4)]
        self.lines += (["  " + post.long_date, ""] if client.show_dates else [""])
        if article and article.text:
            self.lines += [("  " + l).rstrip() for l in wrap(sanitize(article.text), w - 4)]
        else:
            self.lines += ["  Articolo non disponibile."]
        if post.link:
            self.lines += ["", "  " + sanitize(post.link.replace("https://", "").replace("http://", ""))]

    def total(self):
        return len(self.lines)

    def screen(self):
        start = self.page * BODY
        return render(self.w, self.client.detail_title, self.lines[start:start + BODY],
                      hint=f"Fonte: {self.client.domain}",
                      keys=site_keys(self.w, self.client, with_zero=True),
                      page=(self.page, self.pages()))

    def on_key(self, k):
        if k == "0":
            self.app.go_to_site_index()
            return True
        return super().on_key(k)


class Televideo(View):
    """RAI Televideo, text only. Type a 3-digit page number (it loads at the third
    digit, like on a TV); Seguente/Precedente scroll, then change sub-page, then page."""

    def __init__(self, app, number: int = FIRST_PAGE, sub: int = 1):
        super().__init__(app)
        self.entry = ""
        self.error = ""
        self.scroll = 0
        self.page = None
        self._open(number, sub)

    def _open(self, number: int, sub: int = 1) -> None:
        """Fetch a page; on any problem keep the current one and say why."""
        self.error = ""
        try:
            page = self.app.tv.get(number, sub)
        except (OSError, ValueError):
            self.error = "Televideo non raggiungibile, riprova"
            return
        if page is None:
            self.error = f"Pagina {number} non disponibile"
            return
        self.page, self.scroll = page, 0

    def _go(self, number: int, sub: int = 1) -> None:
        self.app.slow(f"Televideo {number}", lambda: self._open(number, sub))

    def _per_screen(self) -> int:
        return BODY if len(self.page.lines) <= BODY else BODY - 1

    def screen(self):
        w, page = self.w, self.page
        shown = self.entry.ljust(3, "_") if self.entry else (str(page.number) if page else "")
        pad = " " * ((w - 40) // 2) if w >= 80 else ""
        body = []
        if page:
            per = self._per_screen()
            body = [pad + sanitize(l) for l in page.lines[self.scroll:self.scroll + per]]
            if self.scroll + per < len(page.lines):
                body.append(pad + "  --- continua (Seguente) ---")
        tag = (page.subs.index(page.sub), len(page.subs)) if page and page.sub in page.subs else None
        hint = self.error or SOURCE
        return render(w, f"TELEVIDEO  {shown}", body, hint=hint,
                      keys=pick(w, "Digita 3 cifre per cambiare pagina   Seguente/Precedente   Indice=menu",
                                "3 cifre=pagina  Segu/Prec  Indice=menu"),
                      page=tag)

    def on_key(self, k):
        if k.isdigit():
            self.error = ""
            self.entry += k
            if len(self.entry) == 3:
                number, self.entry = int(self.entry), ""
                if FIRST_PAGE <= number <= LAST_PAGE:
                    self._go(number)
                else:
                    self.error = f"Le pagine vanno da {FIRST_PAGE} a {LAST_PAGE}"
            return True
        if k == CORREZIONE:
            self.entry = self.entry[:-1]
            return True
        if k == ANNUL and self.entry:
            self.entry = ""
            return True
        if k == INVIO:
            self.entry = ""
            return True
        if k in (SEGUENTE, PRECEDENTE) and self.page:
            return self._move(forward=k == SEGUENTE)
        return False

    def _move(self, forward: bool) -> bool:
        page, per = self.page, self._per_screen()
        self.entry = self.error = ""
        if forward and self.scroll + per < len(page.lines):
            self.scroll += per
            return True
        if not forward and self.scroll > 0:
            self.scroll = max(0, self.scroll - per)
            return True
        later = [s for s in page.subs if (s > page.sub if forward else s < page.sub)]
        if later:
            self._go(page.number, min(later) if forward else max(later))
            return True
        number = page.number + (1 if forward else -1)
        if FIRST_PAGE <= number <= LAST_PAGE:
            self._go(number)
            return True
        return False        # before the first page: lets the app go back to the menu


class Search(View):
    def __init__(self, app):
        super().__init__(app)
        self.text = ""

    def screen(self):
        body = ["", "  Scrivi cosa cerchi (ad esempio: pixel, notebook, calze):", "",
                f"  > {self.text}_"]
        return render(self.w, "CERCA", body, hint="Scrivi e premi Invio",
                      keys=pick(self.w, "Correzione=cancella una lettera   Annul.=torna indietro",
                                "Correzione=cancella  Annul=indietro"))

    def on_key(self, k):
        if k == INVIO:
            if self.text.strip():
                app, text = self.app, self.text.strip()
                app.push(app.slow(f"Cerca: {text}", lambda: ProductList(
                    app, f"Cerca: {text}", app.shop.search(text))))
            return True
        if k == CORREZIONE:
            self.text = self.text[:-1]
            return True
        if k == ANNUL and self.text:
            self.text = ""
            return True
        if len(k) == 1 and k.isprintable() and len(self.text) < 30:
            self.text += k
            return True
        return False


HELP = [
    "",
    "  Indice      torna al menu iniziale",
    "  Seguente    pagina successiva",
    "  Precedente  pagina precedente",
    "  Annul.      torna indietro",
    "  Correzione  cancella una lettera",
    "  Ripetiz.    aggiorna lo schermo e i prodotti",
    "  0           nelle Storie e nelle Guide: torna all'indice",
    "",
    "  Per scegliere premi il numero.",
    "  Per cercare scrivi e premi Invio.",
]


class Guide(View):
    """The Guida screen: what the keys do, and the way into Impostazioni."""

    def screen(self):
        body = HELP + ["", "  1  Impostazioni"]
        return render(self.w, "GUIDA", body, hint="Premi 1 per le impostazioni",
                      keys=pick(self.w, "Annul.=torna indietro   Indice=menu iniziale",
                                "Annul=indietro  Indice=menu"))

    def on_key(self, k):
        if k == "1":
            self.app.push(SettingsView(self.app))
            return True
        return False


class SettingsView(View):
    """Impostazioni: press a number to move that setting to its next value."""

    def screen(self):
        w, settings = self.w, self.app.settings
        body = [""]
        for i, key in enumerate(ORDER, 1):
            label = SPECS[key][0] if w >= 80 else SPECS[key][1]
            value = settings.text(key)
            head = f"  {i}  {label} "
            body.append(head.ljust(w - 2 - len(value) - 1, ".") + " " + value)
        body += ["", "  Premi il numero per cambiare il valore.",
                 "  Le impostazioni restano salvate anche dopo lo spegnimento."]
        return render(w, "IMPOSTAZIONI", body, hint="Premi il numero da cambiare",
                      keys=pick(w, "Annul.=torna alla guida   Indice=menu iniziale",
                                "Annul=indietro  Indice=menu"))

    def on_key(self, k):
        if k.isdigit() and 1 <= int(k) <= len(ORDER):
            self.app.settings.cycle(ORDER[int(k) - 1])
            return True
        return False


class App:
    def __init__(self, shop: Shop, width: int = 80, on_loading=None,
                 loading_delay: float = 0.5, settings: Settings | None = None,
                 televideo: TelevideoClient | None = None, stories: WordPressClient | None = None,
                 nerdvana: WordPressClient | None = None):
        self.shop = shop
        self.tv = televideo or TelevideoClient()
        cache = getattr(shop, "cache_dir", None)
        given = {"stories": stories, "nerdvana": nerdvana}
        self.sources = {key: given[key] or WordPressClient(cache_dir=cache, **cfg)
                        for key, cfg in WP_SOURCES.items()}
        self.stories = self.sources["stories"]          # kept as a name of its own: Storie EPIC
        self.w = width
        self.settings = settings or Settings()   # in memory unless the runner gives a file
        # Called with a screen when a fetch takes longer than loading_delay.
        self.on_loading = on_loading
        self.loading_delay = loading_delay
        # Set by the serial runner, e.g. "1200 baud, 7 bit, parità pari, 1 stop".
        self.line_info: str | None = None
        self.stack: list[View] = []
        self._collections = None
        self.reset()

    def reset(self):
        self.stack = [Home(self)]

    def collection_titles(self):
        if self._collections is None:
            self._collections = [(c.handle, c.title) for c in self.shop.collections()]
        return self._collections

    @property
    def view(self) -> View:
        return self.stack[-1]

    def go_to_site_index(self):
        """Back to the index of the WordPress site being read: its list of cities, or
        its list of articles when it has one fixed category, at the first page."""
        while len(self.stack) > 1 and not getattr(self.view, "is_index", False):
            self.stack.pop()
        if hasattr(self.view, "page"):
            self.view.page = 0

    def push(self, view: View):
        self.stack.append(view)

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()

    def slow(self, label: str, build):
        """Run build() and return its result. If it takes longer than
        loading_delay seconds, hand the loading screen to on_loading first,
        so the user sees something while the shop answers."""
        box: dict = {}

        def run():
            try:
                box["value"] = build()
            except BaseException as e:  # re-raised below, in the caller's thread
                box["error"] = e

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(self.loading_delay)
        if worker.is_alive():
            if self.on_loading:
                self.on_loading(loading_screen(self.w, label))
            worker.join()
        if "error" in box:
            raise box["error"]
        return box["value"]

    def key(self, k: str):
        try:
            self._key(k)
        except Exception as e:  # network errors must not kill the totem
            self.push(Message(self, "ERRORE", ["", "  Servizio non raggiungibile.",
                                                "  Riprova tra poco.", "",
                                                f"  {type(e).__name__}"]))

    def _key(self, k: str):
        if k == INDICE:
            self.reset()
        elif k == RIPETIZ:
            self.shop.refresh()
            self._collections = None
        elif k == GUIDA:
            if not isinstance(self.view, (Guide, SettingsView)):
                self.push(Guide(self))
        elif self.view.on_key(k):
            pass
        elif k in (ANNUL, PRECEDENTE):
            self.pop()

    def screen(self) -> list[str]:
        return self.view.screen()
