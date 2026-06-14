"""Stock + price via schema.org JSON-LD embedded in the product page.

Many retailers ship a <script type="application/ld+json"> Product block with an
`offers` object carrying `price`, `priceCurrency`, and `availability`
(schema.org InStock / OutOfStock / PreOrder / SoldOut). Verified to work with
realistic browser headers (no proxy, no headless browser) on Chaos Cards
(custom "Evosite") and Magic Madhouse (BigCommerce).

Advantages over scraping page text: it's an exact, structured signal, and the
price is usually present even when the item is out of stock -> real price history.
"""

import json
import logging
from typing import Optional

from bs4 import BeautifulSoup

from ..models import Product, StockResult
from .base import StoreAdapter

log = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


class JsonLdStore(StoreAdapter):
    adapter = "jsonld"

    def check(self, product: Product) -> Optional[StockResult]:
        url = self.url_for(product)
        if not url:
            return None
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = url.rsplit("/", 1)[0] + "/"
        try:
            resp = self.session.get(url, headers=headers, timeout=25)
            resp.raise_for_status()
        except Exception as e:
            log.warning("[%s] fetch failed for %s: %s", self.name, product.id, e)
            return None

        offer = self._find_offer(resp.text)
        if offer is None:
            log.info("[%s] no JSON-LD Product/offer for %s (blocked or no structured data)",
                     self.name, product.id)
            return None

        avail = str(offer.get("availability", "")).lower()
        price = self._to_float(offer.get("price") or offer.get("lowPrice"))
        in_stock = "instock" in avail or "limitedavailability" in avail
        # Record the price regardless of stock state (JSON-LD usually has it either way).
        return self._result(product, in_stock, price, url, raw=avail or "jsonld")

    # --- parsing helpers ----------------------------------------------------
    def _find_offer(self, html: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            for node in self._iter_nodes(data):
                if not isinstance(node, dict):
                    continue
                if "Product" in self._types(node) and node.get("offers"):
                    offers = node["offers"]
                    return offers[0] if isinstance(offers, list) and offers else offers
        return None

    def _iter_nodes(self, data):
        """Yield candidate dicts from a JSON-LD doc (handles list and @graph forms)."""
        if isinstance(data, list):
            for item in data:
                yield from self._iter_nodes(item)
        elif isinstance(data, dict):
            yield data
            if "@graph" in data:
                yield from self._iter_nodes(data["@graph"])

    def _types(self, node: dict):
        t = node.get("@type", "")
        return t if isinstance(t, list) else [t]

    def _to_float(self, val) -> Optional[float]:
        if val is None:
            return None
        try:
            return round(float(str(val).replace(",", "").replace("£", "").strip()), 2)
        except ValueError:
            return None
