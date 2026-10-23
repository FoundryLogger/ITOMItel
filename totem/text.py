"""Text helpers: HTML to plain text, character cleanup, wrapping.

The terminal only has a small character set, so everything shown on screen
goes through sanitize() first.
"""
from __future__ import annotations

import re
import textwrap
import unicodedata
from html.parser import HTMLParser

# Characters the HCS 80 keyboard shows (Italian accents and a few symbols).
KEEP = set("àèéìòùÀÈÉÌÒÙçÇ€£§°")

_TABLE = str.maketrans({
    "‘": "'", "’": "'", "‚": ",", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-", "•": "-",
    "…": "...", " ": " ", "​": "", "®": "(R)",
    "™": "(TM)", "©": "(C)", "×": "x", "→": "->",
})


# Accents and symbols spelled out for terminals that only have plain ASCII.
_ACCENTS = {"à": "a'", "è": "e'", "é": "e'", "ì": "i'", "ò": "o'", "ù": "u'",
            "À": "A'", "È": "E'", "É": "E'", "Ì": "I'", "Ò": "O'", "Ù": "U'",
            "ç": "c", "Ç": "C", "€": "EUR", "£": "GBP", "§": "par.", "°": "o"}

# When True (real terminal in Ascii mode), sanitize() already spells everything
# in plain ASCII, so the layout code sees the true width of each line.
ASCII_ONLY = False


def set_ascii_only(value: bool) -> None:
    global ASCII_ONLY
    ASCII_ONLY = value


def ascii_spell(s: str) -> str:
    """Spell out the characters plain ASCII lacks (è -> e', € -> EUR)."""
    s = "".join(_ACCENTS.get(ch, ch) for ch in s)
    return s.encode("ascii", "replace").decode("ascii")


def sanitize(s: str) -> str:
    """Replace characters the terminal can't show with plain ASCII."""
    out = []
    for ch in s.translate(_TABLE):
        if ch == "\n" or 32 <= ord(ch) < 127 or ch in KEEP:
            out.append(ch)
        else:
            folded = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in folded if 32 <= ord(c) < 127))
    result = "".join(out)
    return ascii_spell(result) if ASCII_ONLY else result


def fold(s: str) -> str:
    """Lowercase and strip accents, for searching."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


class _Extractor(HTMLParser):
    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol",
             "table", "tr", "section", "blockquote", "figure", "figcaption"}
    HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    SKIP = {"script", "style", "head", "iframe", "audio", "video"}

    def __init__(self, headings: bool = False):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.headings = headings      # headings in capitals, set apart by a blank line
        self.upper = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")
            if self.headings and tag in self.HEADINGS:
                self.parts.append("\n")
                self.upper += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")
            if self.headings and tag in self.HEADINGS:
                self.upper = max(0, self.upper - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data.upper() if self.upper else data)


def html_to_text(html: str, headings: bool = False) -> str:
    parser = _Extractor(headings)
    parser.feed(html or "")
    lines = [re.sub(r"[ \t\u00a0]+", " ", l).strip()
             for l in "".join(parser.parts).split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def wrap(text: str, width: int) -> list[str]:
    """Wrap text to width, keeping paragraph breaks and list bullets."""
    out: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out.append("")
            continue
        indent = "  " if line.startswith("- ") else ""
        out.extend(textwrap.wrap(line, width, subsequent_indent=indent,
                                 break_long_words=True) or [""])
    return out


def fit(s: str, width: int) -> str:
    """Cut s to width, marking the cut with a dot."""
    return s if len(s) <= width else s[: width - 1] + "."


def money(value) -> str:
    return f"{value:.2f}".replace(".", ",")
