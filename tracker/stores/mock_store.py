"""A fake store that randomly goes in/out of stock, so the pipeline runs with no network."""

import random
from typing import Optional

from ..models import Product, StockResult
from .base import StoreAdapter


class MockStore(StoreAdapter):
    adapter = "mock"

    def check(self, product: Product) -> Optional[StockResult]:
        url = self.url_for(product) or f"https://example.com/{product.id}"
        in_stock = random.random() < 0.20
        price = round(random.uniform(35, 65), 2) if in_stock else None
        return self._result(product, in_stock, price, url, raw="mock")
