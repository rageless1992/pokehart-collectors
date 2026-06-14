"""Awin product datafeed loader.

Awin publishers can pull a per-merchant product datafeed (CSV) from a datafeed
URL. The standard schema includes price + availability, which is the legitimate
way to get Argos / Smyths / Very / John Lewis / GAME data without scraping.

This loads a feed (from a URL or a local file), auto-detects the relevant
columns (their names vary by feed config), and indexes rows by merchant product
id and EAN so a store adapter can look products up.

Feed is BATCH (refreshed ~daily by Awin), so this is good for price + coarse
in/out-of-stock, not second-by-second restocks.
"""

import csv
import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

# Candidate column names (first present one wins). Awin feeds let the publisher
# choose columns/labels, so we accept the common variants.
COLUMN_CANDIDATES = {
    "id": ["merchant_product_id", "product_id", "aw_product_id"],
    "name": ["product_name", "product_short_description"],
    "price": ["store_price", "search_price", "display_price", "price"],
    "rrp": ["rrp_price", "rrp"],
    "currency": ["currency"],
    "in_stock": ["in_stock", "stock_status", "availability", "is_in_stock"],
    "stock_qty": ["stock_quantity"],
    "ean": ["ean", "product_GTIN", "gtin"],
    "url": ["aw_deep_link", "merchant_deep_link", "deep_link"],
}

_IN_STOCK_TRUE = {"1", "true", "yes", "y", "in stock", "instock", "in_stock", "available"}


@dataclass
class FeedRow:
    id: str
    name: str
    price: Optional[float]
    rrp: Optional[float]
    currency: str
    in_stock: Optional[bool]
    url: str


class AwinFeed:
    def __init__(self, source: str, ttl: int = 3600):
        self.source = source              # http(s) URL or local file path
        self.ttl = ttl
        self._loaded_at = 0.0
        self._by_id: dict = {}
        self._by_ean: dict = {}

    # --- public -------------------------------------------------------------
    def get(self, pid: Optional[str] = None, ean: Optional[str] = None) -> Optional[FeedRow]:
        self._ensure_loaded()
        if pid and str(pid) in self._by_id:
            return self._by_id[str(pid)]
        if ean and str(ean) in self._by_ean:
            return self._by_ean[str(ean)]
        return None

    @property
    def size(self) -> int:
        self._ensure_loaded()
        return len(self._by_id)

    # --- internals ----------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._by_id and (time.time() - self._loaded_at) < self.ttl:
            return
        try:
            text = self._read()
        except Exception as e:
            log.warning("Awin feed read failed (%s): %s", self.source, e)
            return
        self._parse(text)
        self._loaded_at = time.time()

    def _read(self) -> str:
        if str(self.source).lower().startswith("http"):
            resp = requests.get(self.source, timeout=60)
            resp.raise_for_status()
            return resp.text
        return Path(self.source).read_text(encoding="utf-8", errors="replace")

    def _resolve_columns(self, fieldnames) -> dict:
        present = {f.strip(): f for f in (fieldnames or [])}
        resolved = {}
        for key, candidates in COLUMN_CANDIDATES.items():
            for c in candidates:
                if c in present:
                    resolved[key] = present[c]
                    break
        return resolved

    def _parse(self, text: str) -> None:
        reader = csv.DictReader(io.StringIO(text))
        cols = self._resolve_columns(reader.fieldnames)
        if "id" not in cols and "ean" not in cols:
            log.warning("Awin feed has no id/ean column; columns=%s", reader.fieldnames)
            return
        by_id, by_ean = {}, {}
        for raw in reader:
            row = FeedRow(
                id=self._val(raw, cols, "id"),
                name=self._val(raw, cols, "name"),
                price=self._num(self._val(raw, cols, "price")),
                rrp=self._num(self._val(raw, cols, "rrp")),
                currency=self._val(raw, cols, "currency") or "GBP",
                in_stock=self._stock(self._val(raw, cols, "in_stock")),
                url=self._val(raw, cols, "url"),
            )
            if row.id:
                by_id[row.id] = row
            ean = self._val(raw, cols, "ean")
            if ean:
                by_ean[ean] = row
        self._by_id, self._by_ean = by_id, by_ean
        log.info("Awin feed loaded: %d products (%s)", len(by_id), self.source)

    @staticmethod
    def _val(raw: dict, cols: dict, key: str) -> str:
        col = cols.get(key)
        return (raw.get(col) or "").strip() if col else ""

    @staticmethod
    def _num(s: str) -> Optional[float]:
        if not s:
            return None
        try:
            return round(float(s.replace(",", "").replace("£", "").strip()), 2)
        except ValueError:
            return None

    @staticmethod
    def _stock(s: str) -> Optional[bool]:
        if s == "":
            return None
        return s.strip().lower() in _IN_STOCK_TRUE
