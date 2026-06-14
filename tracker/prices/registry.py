"""Build price source instances from the config 'price_sources' section."""

import logging
from typing import List

from .base import PriceSource
from .ebay_sold import EbaySold
from .mock_price import MockPrice
from .pricecharting import PriceCharting

log = logging.getLogger(__name__)

ADAPTERS = {cls.adapter: cls for cls in (MockPrice, PriceCharting, EbaySold)}


def build_price_sources(defs: dict) -> List[PriceSource]:
    sources = []
    for name, sd in defs.items():
        adapter = (sd or {}).get("adapter", name)
        cls = ADAPTERS.get(adapter)
        if not cls:
            log.warning("price source '%s' uses unknown adapter '%s' -- skipping", name, adapter)
            continue
        sources.append(cls(name=name, settings=sd))
    return sources
