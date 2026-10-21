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


def sanitize(s: str) -> str:
    """Replace characters the terminal can't show with plain ASCII."""
    out = []
    for ch in s.translate(_TABLE):
        if ch == "\n" or 32 <= ord(ch) < 127 or ch in KEEP:
            out.append(ch)
        else:
            folded = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in folded if 32 <= ord(c) < 127))
    return "".join(out)


def fold(s: str) -> str:
    """Lowercase and strip accents, for searching."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


class _Extractor(HTMLParser):
    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol",
             "table", "tr", "section", "blockquote"}
    SKIP = {"script", "style", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Extractor()
    parser.feed(html or "")
    lines = [re.sub(r"[ \t ]+", " ", l).strip()
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
