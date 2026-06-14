"""A fake price source: a seeded random walk per product so charts/strategy have data."""

import hashlib
import math
import random
from datetime import timedelta
from typing import List, Optional

from ..models import PricePoint, Product, utcnow
from .base import PriceSource


class MockPrice(PriceSource):
    adapter = "mock"

    def _base(self, product: Product) -> float:
        # Deterministic anchor price per product so it's stable across runs.
        h = int(hashlib.md5(product.id.encode()).hexdigest(), 16)
        return 30 + (h % 60)

    def fetch(self, product: Product) -> Optional[PricePoint]:
        if self.identifier_for(product) is None:
            return None
        base = self._base(product)
        jitter = random.uniform(-0.08, 0.10)
        price = round(base * (1 + jitter), 2)
        return self._point(product, price, kind="market")

    def backfill(self, product: Product, days: int = 30) -> List[PricePoint]:
        """Generate a smooth-ish price history so the dashboard isn't empty on day one."""
        base = self._base(product)
        now = utcnow()
        points = []
        for d in range(days, 0, -1):
            wave = math.sin(d / 5.0) * 0.06
            noise = random.uniform(-0.03, 0.03)
            price = round(base * (1 + wave + noise), 2)
            p = self._point(product, price, kind="market")
            p.observed_at = now - timedelta(days=d)
            points.append(p)
        return points
