"""Read-only client for a Shopify store's public JSON endpoints.

No API token is needed: /products.json, /collections.json and
/collections/<handle>/products.json are public on any online store that is
not password protected. Responses are cached in memory and on disk, so the
totem keeps working if the network drops.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .text import fold, html_to_text

PAGE_LIMIT = 250


@dataclass
class Variant:
    title: str
    price: Decimal
    compare_at: Decimal | None
    available: bool


@dataclass
class Product:
    id: int
    handle: str
    title: str
    vendor: str
    product_type: str
    tags: list[str]
    description: str
    published_at: str
    variants: list[Variant] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return any(v.available for v in self.variants)

    @property
    def price_from(self) -> Decimal:
        return min((v.price for v in self.variants), default=Decimal(0))

    @property
    def price_to(self) -> Decimal:
        return max((v.price for v in self.variants), default=Decimal(0))

    @property
    def on_sale(self) -> bool:
        return any(v.compare_at and v.compare_at > v.price for v in self.variants)

    def haystack(self) -> str:
        return fold(" ".join([self.title, self.vendor, self.product_type,
                              " ".join(self.tags), self.description]))


@dataclass
class Collection:
    handle: str
    title: str
    count: int


def _parse_product(d: dict) -> Product:
    variants = []
    for v in d.get("variants", []):
        cmp_ = v.get("compare_at_price")
        variants.append(Variant(
            title=v.get("title") or "",
            price=Decimal(v.get("price") or "0"),
            compare_at=Decimal(cmp_) if cmp_ else None,
            available=bool(v.get("available")),
        ))
    return Product(
        id=d["id"], handle=d["handle"], title=d["title"],
        vendor=d.get("vendor") or "", product_type=d.get("product_type") or "",
        tags=d.get("tags") or [], description=html_to_text(d.get("body_html")),
        published_at=d.get("published_at") or "", variants=variants,
    )


class Shop:
    def __init__(self, base_url: str, cache_dir: str | Path | None = None,
                 ttl: int = 300, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl = ttl
        self.timeout = timeout
        self._mem: dict[str, tuple[float, dict]] = {}
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def refresh(self) -> None:
        """Drop the in-memory cache so the next read hits the network."""
        self._mem.clear()

    def _disk_path(self, path: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha1(path.encode()).hexdigest() + ".json")

    def _get_json(self, path: str) -> dict:
        now = time.time()
        hit = self._mem.get(path)
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        try:
            req = urllib.request.Request(self.base_url + path,
                                         headers={"User-Agent": "itomi-totem/0.1"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
            disk = self._disk_path(path)
            if disk:
                disk.write_text(json.dumps(data))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            disk = self._disk_path(path)
            if hit:
                return hit[1]
            if disk and disk.exists():
                data = json.loads(disk.read_text())
            else:
                raise
        self._mem[path] = (now, data)
        return data

    def _paged_products(self, base_path: str) -> list[Product]:
        out: list[Product] = []
        page = 1
        while True:
            sep = "&" if "?" in base_path else "?"
            data = self._get_json(f"{base_path}{sep}limit={PAGE_LIMIT}&page={page}")
            batch = data.get("products", [])
            out.extend(_parse_product(p) for p in batch)
            if len(batch) < PAGE_LIMIT:
                return out
            page += 1

    def products(self) -> list[Product]:
        return self._paged_products("/products.json")

    def collections(self) -> list[Collection]:
        out, page = [], 1
        while True:
            data = self._get_json(f"/collections.json?limit={PAGE_LIMIT}&page={page}")
            batch = data.get("collections", [])
            out.extend(Collection(c["handle"], c["title"], c.get("products_count", 0))
                       for c in batch)
            if len(batch) < PAGE_LIMIT:
                break
            page += 1
        return sorted((c for c in out if c.count > 0), key=lambda c: fold(c.title))

    def collection_products(self, handle: str) -> list[Product]:
        return self._paged_products(f"/collections/{handle}/products.json")

    def newest(self, n: int = 18) -> list[Product]:
        return sorted(self.products(), key=lambda p: p.published_at, reverse=True)[:n]

    def search(self, query: str) -> list[Product]:
        words = fold(query).split()
        if not words:
            return []
        def matches(p: Product) -> bool:
            # A search word must match the start of a word, so "casa"
            # doesn't hit "incasare" or "occasione".
            tokens = p.haystack().replace("-", " ").replace(".", " ").split()
            return all(any(t.startswith(w) for t in tokens) for w in words)

        hits = [p for p in self.products() if matches(p)]
        # Title matches first, then the rest.
        return sorted(hits, key=lambda p: not all(w in fold(p.title) for w in words))
