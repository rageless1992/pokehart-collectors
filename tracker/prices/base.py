"""Base class for price sources.

A price source turns a product identifier (a slug, URL, or id you put in
product.price_sources) into an observed PricePoint.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import requests

from ..models import PricePoint, Product
from ..stores.base import DEFAULT_HEADERS

log = logging.getLogger(__name__)


class PriceSource(ABC):
    adapter = "base"

    def __init__(self, name: str, settings: Optional[dict] = None, session: Optional[requests.Session] = None):
        self.name = name
        self.settings = settings or {}
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def identifier_for(self, product: Product) -> Optional[str]:
        return product.price_sources.get(self.name)

    @abstractmethod
    def fetch(self, product: Product) -> Optional[PricePoint]:
        """Return a PricePoint, or None if not tracked here / fetch failed."""

    def _point(self, product: Product, price: float, kind: str = "market", currency: str = "GBP") -> PricePoint:
        return PricePoint(product_id=product.id, source=self.name, price=price, kind=kind, currency=currency)
