"""Thin read-layer over Config + DB for the dashboard (keeps app.py presentational)."""

from typing import List, Optional

from ..models import PokeSet, Product


def list_sets(cfg) -> List[PokeSet]:
    """Sets newest-first for the gallery."""
    return sorted(cfg.sets(), key=lambda s: s.release_date or "", reverse=True)


def products_in_set(cfg, set_id: str) -> List[Product]:
    return [p for p in cfg.products() if p.set_id == set_id]


def unassigned_products(cfg) -> List[Product]:
    return [p for p in cfg.products() if not p.set_id]


def latest_prices_per_store(db, product: Product) -> dict:
    """store_name -> last stock_checks row (price, in_stock, checked_at)."""
    return {s: db.last_stock(product.id, s) for s in product.stores}


def cheapest_in_stock_store(db, product: Product):
    """(store, price, url) for the cheapest IN-STOCK store, else None."""
    best = None
    for store, row in latest_prices_per_store(db, product).items():
        if row and row["in_stock"] and row["price"]:
            if best is None or row["price"] < best[1]:
                best = (store, row["price"], product.stores.get(store, ""))
    return best


def first_store_link(product: Product):
    """(store, url) of the first listed store -- a buy link even when out of stock."""
    for store, url in (product.stores or {}).items():
        if url:
            return (store, url)
    return None


def cheapest_price(db, products: List[Product]) -> Optional[float]:
    """Lowest current store price across a set's products (for the tile 'from £X')."""
    best = None
    for p in products:
        for row in latest_prices_per_store(db, p).values():
            if row and row["price"]:
                best = row["price"] if best is None else min(best, row["price"])
    return best


def latest_ebay_sold(db, product: Product):
    return db.latest_price(product.id, source="ebay_sold")


def ebay_history(db, product: Product):
    return db.price_history(product.id, source="ebay_sold")
