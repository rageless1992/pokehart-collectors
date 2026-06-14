"""Plain data objects passed between the stores, prices, db, and strategy layers."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PokeSet:
    """A Pokemon TCG expansion set (catalog metadata for the gallery)."""

    id: str
    name: str
    code: str = ""                # 3-letter set code, e.g. CRI
    era: str = ""                 # "Mega Evolution" | "Scarlet & Violet"
    release_date: str = ""        # ISO YYYY-MM-DD
    count: Optional[int] = None   # base card count (the "/NN")
    logo_url: str = ""


@dataclass
class Product:
    """One thing you're watching: a sealed box, a pack, or a single card."""

    id: str
    name: str
    kind: str = "sealed"          # booster_box | etb | etb_pc | booster_bundle | booster_pack | build_battle
    set_name: str = ""
    set_id: str = ""              # FK into the sets catalog ("" = unassigned)
    image_url: str = ""           # product photo (Total Cards Shopify CDN); "" -> placeholder
    stores: dict = field(default_factory=dict)         # store_name -> product URL
    price_sources: dict = field(default_factory=dict)  # source_name -> identifier/slug
    ebay_query: str = ""          # eBay sold-search string for this product
    target_buy_price: Optional[float] = None
    target_sell_price: Optional[float] = None
    notes: str = ""


@dataclass
class StockResult:
    """Outcome of a single store check for a single product."""

    product_id: str
    store: str
    in_stock: bool
    price: Optional[float]
    url: str
    currency: str = "GBP"
    raw_status: str = ""
    checked_at: datetime = field(default_factory=utcnow)


@dataclass
class PricePoint:
    """A single observed price for a product from a price source."""

    product_id: str
    source: str
    price: float
    currency: str = "GBP"
    kind: str = "market"          # market | sealed_new | loose | sold_median
    observed_at: datetime = field(default_factory=utcnow)
    # eBay-sold metadata (None for other sources)
    sample_size: Optional[int] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    sold_at: Optional[str] = None
