"""RAI Televideo, text-only edition, read on request.

RAI publishes every Televideo page on the web in a "solo testo" form: a
40-column <pre> block per page (solotesto.jsp?pagina=103). The content belongs
to RAI, so this client is deliberately polite and discreet:

- it fetches a page only when somebody asks for it, never in the background;
- it keeps pages in memory for two minutes at most, never on disk;
- it leaves a short pause between two requests and identifies itself;
- the screens always show the source (see SOURCE).

Nothing from Televideo is stored in this repository.
"""
from __future__ import annotations

import html
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

BASE = "https://www.servizitelevideo.rai.it/televideo/pub/solotesto.jsp"
SOURCE = "Fonte: RAI Televideo - servizitelevideo.rai.it"
USER_AGENT = "itomitel/0.1 (hobby kiosk; +https://github.com/itomistudio/ITOMItel)"
FIRST_PAGE, LAST_PAGE = 100, 899


@dataclass
class TvPage:
    number: int
    sub: int = 1
    subs: list[int] = field(default_factory=lambda: [1])
    lines: list[str] = field(default_factory=list)


def parse(markup: str, number: int, sub: int = 1) -> TvPage | None:
    """The page text and the sub-pages it links to, or None for an empty/missing page."""
    m = re.search(r"<pre[^>]*>(.*?)</pre>", markup, re.S | re.I)
    if not m:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).replace("\r", "")
    lines = [l.rstrip() for l in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None
    subs = {sub}
    for p, s in re.findall(r"solotesto\.jsp\?pagina=(\d+)(?:&amp;|&)sottopagina=(\d+)", markup):
        if int(p) == number:
            subs.add(int(s))
    return TvPage(number, sub, sorted(subs), lines)


def _download(number: int, sub: int, timeout: float = 10.0) -> str:
    url = f"{BASE}?pagina={number}&sottopagina={sub}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


class TelevideoClient:
    """get(number, sub) -> TvPage, or None if the page doesn't exist.
    Raises OSError-family errors when the network is down."""

    def __init__(self, ttl: float = 120.0, pause: float = 0.4, fetch=None):
        self.ttl, self.pause = ttl, pause
        self._fetch = fetch or _download
        self._cache: dict[tuple[int, int], tuple[float, TvPage | None]] = {}
        self._lock = threading.Lock()
        self._last = 0.0

    def get(self, number: int, sub: int = 1) -> TvPage | None:
        key = (number, sub)
        with self._lock:
            now = time.monotonic()
            hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
            wait = self.pause - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            markup = self._fetch(number, sub)
            self._last = time.monotonic()
            page = parse(markup, number, sub)
            self._cache = {k: v for k, v in self._cache.items()
                           if self._last - v[0] < self.ttl}      # nothing lives longer than ttl
            self._cache[key] = (self._last, page)
            return page
