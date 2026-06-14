"""Store adapter backed by an Awin product datafeed (price + availability).

For retailers blocked to direct scraping (Argos, Smyths, Very, John Lewis, GAME)
this is the legitimate route. Configure per store in config.json:

    "argos": {
      "adapter": "awin",
      "feed_url": "https://productdata.awin.com/datafeed/download/apikey/...",
      "id_regex": "/product/(\\d+)"
    }

`feed_url` can also be a local file path (`feed_path`) -- handy for testing with a
sample feed downloaded from the Awin UI before automating the URL. `id_regex`
extracts the merchant product id from the product's existing store URL so we can
match it against the feed (no per-product EANs needed). If the feed isn't
configured yet the adapter is a no-op (returns None), so the app keeps running.
"""

import logging
import re
from typing import Optional

from ..feeds.awin import AwinFeed
from ..models import Product, StockResult
from .base import StoreAdapter

log = logging.getLogger(__name__)


class AwinStore(StoreAdapter):
    adapter = "awin"

    def __init__(self, name, settings=None, session=None):
        super().__init__(name, settings, session)
        source = self.settings.get("feed_url") or self.settings.get("feed_path")
        self.feed = AwinFeed(source, ttl=self.settings.get("feed_ttl", 3600)) if source else None
        rx = self.settings.get("id_regex")
        self.id_regex = re.compile(rx) if rx else None

    def check(self, product: Product) -> Optional[StockResult]:
        url = self.url_for(product)
        if not url:
            return None
        if self.feed is None:
            log.info("[%s] Awin feed not configured yet -- skipping (add feed_url/feed_path)", self.name)
            return None

        pid = self._merchant_id(url)
        ean = product.price_sources.get("ean") if isinstance(product.price_sources, dict) else None
        row = self.feed.get(pid=pid, ean=ean)
        if row is None:
            log.info("[%s] %s not found in feed (pid=%s)", self.name, product.id, pid)
            return None
        if row.in_stock is None:
            return None  # feed doesn't populate stock for this merchant -> don't guess
        return self._result(product, row.in_stock, row.price, row.url or url, raw="awin")

    def _merchant_id(self, url: str) -> Optional[str]:
        if not self.id_regex:
            return None
        m = self.id_regex.search(url)
        return m.group(1) if m else None
