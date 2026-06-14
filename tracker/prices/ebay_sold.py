"""eBay UK last-sold price source (server-side; no browser extension).

Activated for any product with an `ebay_query`. Runs on the slow price cadence
(daily) -- it's polite (serial, jittered) so a full pass over the watchlist takes
a few minutes. Records a PricePoint with source="ebay_sold" + sample metadata.
"""

import logging
import random
import time
from typing import Optional

from ..models import PricePoint, Product
from .base import PriceSource
from .ebay import EbayClient, aggregate, parse_sold

log = logging.getLogger(__name__)


class EbaySold(PriceSource):
    adapter = "ebay_sold"

    def __init__(self, name, settings=None, session=None):
        super().__init__(name, settings, session)
        self.client = EbayClient(cookie_path=self.settings.get("cookie_path"))
        self.ipg = int(self.settings.get("ipg", 60))
        self.max_samples = int(self.settings.get("max_samples", 15))
        self.delay = self.settings.get("delay_seconds", 10)
        self.jitter = self.settings.get("jitter_seconds", 10)
        self._first = True

    def fetch(self, product: Product) -> Optional[PricePoint]:
        if self.identifier_for(product) is None:
            return None
        query = product.ebay_query or product.name
        if not query:
            return None

        if not self._first and self.delay:  # polite gap between products
            time.sleep(self.delay + random.uniform(0, self.jitter))
        self._first = False

        html = self.client.fetch(query, ipg=self.ipg)
        if html is None:
            log.warning("[ebay_sold] no page for %s (%r)", product.id, query)
            return None
        agg = aggregate(parse_sold(html), product, max_samples=self.max_samples)
        if agg is None:
            log.info("[ebay_sold] no usable sold data for %s", product.id)
            return None

        pt = self._point(product, agg["median"], kind="sold_median", currency="GBP")
        pt.sample_size = agg["n"]
        pt.price_min = agg["min"]
        pt.price_max = agg["max"]
        pt.sold_at = agg["sold_at"]
        log.info("[ebay_sold] %s -> £%.2f (median of %d)", product.id, agg["median"], agg["n"])
        return pt
