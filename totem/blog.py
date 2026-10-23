"""Articles of one category of a WordPress site, read through its public REST API.

Used for the "Storie" of whatisepic.it (category slug "storie"): the list comes
from /wp-json/wp/v2/posts?categories=<id>, the text of an article is fetched
only when somebody opens it. Answers are cached in memory and on disk, so the
stories stay readable if the network drops.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .text import html_to_text

MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
          "agosto", "settembre", "ottobre", "novembre", "dicembre"]
PAGE_LIMIT = 100


@dataclass
class Post:
    id: int
    date: str            # ISO, e.g. 2026-03-06T10:00:00
    title: str
    link: str
    text: str = ""

    @property
    def short_date(self) -> str:
        """06/03/26"""
        y, m, d = self.date[:10].split("-")
        return f"{d}/{m}/{y[2:]}"

    @property
    def long_date(self) -> str:
        """6 marzo 2026"""
        y, m, d = self.date[:10].split("-")
        return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _post(d: dict) -> Post:
    return Post(
        id=d["id"], date=d.get("date", "1970-01-01T00:00:00"),
        title=html_to_text(d.get("title", {}).get("rendered", "")),
        link=d.get("link", ""),
        text=html_to_text(d.get("content", {}).get("rendered", ""), headings=True),
    )


class WordPressClient:
    def __init__(self, site: str, category: str, cache_dir: str | Path | None = None,
                 ttl: float = 600.0, timeout: float = 15.0, fetch=None):
        self.site = site.rstrip("/")
        self.category = category
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl, self.timeout = ttl, timeout
        self._fetch = fetch or self._download
        self._mem: dict[str, tuple[float, object]] = {}
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def domain(self) -> str:
        return re.sub(r"^https?://(www\.)?", "", self.site)

    def refresh(self) -> None:
        self._mem.clear()

    def _download(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "itomitel/0.1 (hobby kiosk)"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def _json(self, path: str):
        url = self.site + path
        now = time.time()
        hit = self._mem.get(url)
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        disk = (self.cache_dir / ("wp-" + hashlib.sha1(url.encode()).hexdigest() + ".json")
                if self.cache_dir else None)
        try:
            data = self._fetch(url)
            if disk:
                disk.write_text(json.dumps(data))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            if hit:
                return hit[1]
            if disk and disk.exists():
                data = json.loads(disk.read_text())
            else:
                raise
        self._mem[url] = (now, data)
        return data

    def _category_id(self) -> int | None:
        found = self._json(f"/wp-json/wp/v2/categories?slug={self.category}&_fields=id")
        return found[0]["id"] if found else None

    def posts(self) -> list[Post]:
        """Titles and dates of every article in the category, newest first (no text)."""
        cid = self._category_id()
        if cid is None:
            return []
        out, page = [], 1
        while True:
            batch = self._json(f"/wp-json/wp/v2/posts?categories={cid}&per_page={PAGE_LIMIT}"
                               f"&page={page}&orderby=date&order=desc&_fields=id,date,title,link")
            out.extend(_post(d) for d in batch)
            if len(batch) < PAGE_LIMIT:
                return out
            page += 1

    def article(self, post_id: int) -> Post | None:
        """One article with its text."""
        d = self._json(f"/wp-json/wp/v2/posts/{post_id}?_fields=id,date,title,link,content")
        return _post(d) if d else None
