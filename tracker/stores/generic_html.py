"""Generic HTML store check driven by out-of-stock text markers.

Works for many simple UK shops (Smyths, Argos, Chaos Cards, Magic Madhouse, etc.):
fetch the product page, decide stock by the presence/absence of "out of stock"
style phrases, and best-effort parse a price.

Limitations to be honest about:
  * Pages rendered by JavaScript (the page is empty until JS runs) won't work with
    a plain HTTP fetch. Those need a headless browser (Playwright) -- see README.
  * Sites behind Cloudflare/Akamai bot protection may block or challenge requests.
  * The OOS markers and price parsing are heuristics; verify against the live page
    and tune `oos_markers` in config.json per store.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from ..models import Product, StockResult
from .base import StoreAdapter

log = logging.getLogger(__name__)

DEFAULT_OOS_MARKERS = [
    "out of stock",
    "sold out",
    "currently unavailable",
    "notify me when",
    "email when available",
]

PRICE_RE = re.compile(r"£\s*([0-9]+(?:\.[0-9]{2})?)")


class GenericHtmlStore(StoreAdapter):
    adapter = "generic_html"

    def check(self, product: Product) -> Optional[StockResult]:
        url = self.url_for(product)
        if not url:
            return None
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            log.warning("[%s] fetch failed for %s: %s", self.name, product.id, e)
            return None

        html = resp.text
        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True).lower()

        markers = [m.lower() for m in self.settings.get("oos_markers", DEFAULT_OOS_MARKERS)]
        out_of_stock = any(m in text for m in markers)
        price = self._parse_price(text)

        return self._result(
            product,
            in_stock=not out_of_stock,
            price=price,
            url=url,
            raw="oos" if out_of_stock else "in_stock",
        )

    def _parse_price(self, text: str) -> Optional[float]:
        m = PRICE_RE.search(text)
        return float(m.group(1)) if m else None
