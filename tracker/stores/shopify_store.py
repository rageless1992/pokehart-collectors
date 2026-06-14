"""Shopify storefront stock check via the public /products/<handle>.js endpoint.

Far more reliable than scraping page text: Shopify returns JSON with a per-product
`available` boolean and the price in pence, so we don't get false "out of stock"
from unrelated "sold out" text elsewhere on the page. Used for Total Cards and
365Games (both Shopify).
"""

import logging
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from ..models import Product, StockResult
from .base import StoreAdapter

log = logging.getLogger(__name__)


class ShopifyStore(StoreAdapter):
    adapter = "shopify"

    def _js_url(self, url: str) -> Optional[str]:
        parts = urlsplit(url)
        if "/products/" not in parts.path:
            return None
        handle = parts.path.split("/products/", 1)[1].strip("/").split("/")[0]
        return urlunsplit((parts.scheme, parts.netloc, f"/products/{handle}.js", "", ""))

    def check(self, product: Product) -> Optional[StockResult]:
        url = self.url_for(product)
        if not url:
            return None
        js = self._js_url(url)
        if not js:
            log.warning("[%s] not a Shopify product URL: %s", self.name, url)
            return None
        try:
            resp = self.session.get(js, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("[%s] shopify fetch failed for %s: %s", self.name, product.id, e)
            return None

        available = bool(data.get("available"))
        price = self._price(data) if available else None
        return self._result(product, available, price, url,
                            raw="in_stock" if available else "unavailable")

    def _price(self, data: dict) -> Optional[float]:
        pence = data.get("price")
        if pence is None:
            for v in data.get("variants", []):
                if v.get("available"):
                    pence = v.get("price")
                    break
        return round(pence / 100.0, 2) if pence else None
