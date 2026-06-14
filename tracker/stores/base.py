"""Base class for store restock adapters.

A store adapter answers one question for a product: is it in stock right now,
and at what price? Each adapter is constructed from a store definition in
config.json ("stores") and reads the per-product URL from product.stores.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import requests

from ..models import Product, StockResult

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


class StoreAdapter(ABC):
    adapter = "base"

    def __init__(self, name: str, settings: Optional[dict] = None, session: Optional[requests.Session] = None):
        self.name = name
        self.settings = settings or {}
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def url_for(self, product: Product) -> Optional[str]:
        return product.stores.get(self.name)

    @abstractmethod
    def check(self, product: Product) -> Optional[StockResult]:
        """Return a StockResult, or None if this product isn't tracked here / check failed."""

    def _result(self, product: Product, in_stock: bool, price: Optional[float], url: str, raw: str = "") -> StockResult:
        return StockResult(
            product_id=product.id,
            store=self.name,
            in_stock=in_stock,
            price=price,
            url=url,
            raw_status=raw,
        )
