"""PriceCharting price source.

product.price_sources["pricecharting"] should be either:
  * a full URL:  https://www.pricecharting.com/game/<set>/<product>
  * or a slug:   <set>/<product>   (we'll build the URL)

PriceCharting product pages expose price cells with ids #used_price (loose),
#complete_price (CIB), and #new_price (sealed/new). We read #new_price first
(best fit for sealed product), then fall back to the others.

Prices on PriceCharting are USD. If you want GBP, set "currency": "USD" handling
or add an FX step; for now we record the number as-is and tag currency from
settings (default USD). Verify selectors against a live page -- site markup can
change.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from ..models import PricePoint, Product
from .base import PriceSource

log = logging.getLogger(__name__)

BASE = "https://www.pricecharting.com/game/"
NUM_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]{2})?)")


class PriceCharting(PriceSource):
    adapter = "pricecharting"

    def _url(self, identifier: str) -> str:
        if identifier.startswith("http"):
            return identifier
        return BASE + identifier.strip("/")

    def fetch(self, product: Product) -> Optional[PricePoint]:
        ident = self.identifier_for(product)
        if not ident:
            return None
        url = self._url(ident)
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            log.warning("[pricecharting] fetch failed for %s: %s", product.id, e)
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        currency = self.settings.get("currency", "USD")

        for cell_id, kind in (("new_price", "sealed_new"), ("complete_price", "market"), ("used_price", "loose")):
            cell = soup.select_one(f"#{cell_id}")
            if not cell:
                continue
            m = NUM_RE.search(cell.get_text(" ", strip=True))
            if m:
                price = float(m.group(1).replace(",", ""))
                return self._point(product, price, kind=kind, currency=currency)

        log.warning("[pricecharting] no price cell parsed for %s (%s)", product.id, url)
        return None
