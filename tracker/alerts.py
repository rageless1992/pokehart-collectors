"""Shared alert evaluation used by BOTH the scheduler (pull) and ingest (push).

Keeping this in one place guarantees a restock/price alert fires identically
whether the data came from a server-side store check or the browser extension.
"""

import logging
from typing import Optional

from .models import PricePoint, Product, StockResult, utcnow

log = logging.getLogger(__name__)


def evaluate_stock(db, notifier, product: Optional[Product], result: StockResult) -> bool:
    """Record a StockResult and fire a restock alert on an out->in transition.

    Returns True if a restock alert fired.
    """
    prev = db.last_stock(result.product_id, result.store)
    db.record_stock(result)
    came_in_stock = result.in_stock and (prev is None or not prev["in_stock"])
    if came_in_stock:
        price = f"£{result.price:.2f}" if result.price else "price n/a"
        name = product.name if product else result.product_id
        notifier.send(f"IN STOCK: {name}", f"{result.store} — {price}", result.url)
        db.record_alert(result.product_id, "restock", f"{result.store} {price} {result.url}")
    return came_in_stock


def evaluate_price(db, notifier, product: Optional[Product], price: float) -> None:
    """Fire buy/sell signal alerts against a product's targets."""
    if product is None:
        return
    if product.target_buy_price is not None and price <= product.target_buy_price:
        notifier.send(f"BUY signal: {product.name}",
                      f"£{price:.2f} at/below your buy target £{product.target_buy_price:.2f}")
        db.record_alert(product.id, "buy_signal", f"£{price:.2f}")
    elif product.target_sell_price is not None and price >= product.target_sell_price:
        notifier.send(f"SELL signal: {product.name}",
                      f"£{price:.2f} at/above your sell target £{product.target_sell_price:.2f}")
        db.record_alert(product.id, "sell_signal", f"£{price:.2f}")
