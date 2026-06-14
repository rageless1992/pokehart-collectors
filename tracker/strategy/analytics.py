"""Profit strategy: buy/sell signals, price trends, and inventory P/L.

These are deliberately simple, transparent rules you can tune. They turn the
price history + your targets + your holdings into actionable signals.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..db import DB
from ..models import Product


@dataclass
class Signal:
    product_id: str
    name: str
    kind: str          # BUY | SELL | HOLD
    price: float
    reason: str


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def latest_market_price(db: DB, product_id: str) -> Optional[float]:
    row = db.latest_price(product_id)
    return row["price"] if row else None


def price_change_pct(db: DB, product_id: str, days: int = 7) -> Optional[float]:
    """Percent change between the oldest point within `days` and the latest."""
    hist = db.price_history(product_id)
    if len(hist) < 2:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    window = [h for h in hist if _parse_dt(h["observed_at"]) >= cutoff] or hist
    first, last = window[0]["price"], hist[-1]["price"]
    if not first:
        return None
    return round((last - first) / first * 100, 2)


def signals(db: DB, products: List[Product]) -> List[Signal]:
    out = []
    for p in products:
        price = latest_market_price(db, p.id)
        if price is None:
            continue
        if p.target_buy_price is not None and price <= p.target_buy_price:
            out.append(Signal(p.id, p.name, "BUY", price,
                              f"£{price:.2f} <= buy target £{p.target_buy_price:.2f}"))
        elif p.target_sell_price is not None and price >= p.target_sell_price:
            out.append(Signal(p.id, p.name, "SELL", price,
                              f"£{price:.2f} >= sell target £{p.target_sell_price:.2f}"))
        else:
            trend = price_change_pct(db, p.id, 7)
            trend_str = f", 7d {trend:+.1f}%" if trend is not None else ""
            out.append(Signal(p.id, p.name, "HOLD", price, f"£{price:.2f}{trend_str}"))
    return out


def inventory_pl(db: DB, products: List[Product]) -> List[dict]:
    """Unrealised profit/loss on open holdings using the latest market price."""
    by_id = {p.id: p for p in products}
    rows = []
    for h in db.open_holdings():
        pid = h["product_id"]
        price = latest_market_price(db, pid)
        buy = h["buy_price"] or 0.0
        qty = h["qty"] or 1
        cur_val = (price or 0.0) * qty
        cost = buy * qty
        rows.append({
            "product_id": pid,
            "name": by_id[pid].name if pid in by_id else pid,
            "qty": qty,
            "buy_price": buy,
            "market_price": price,
            "cost": round(cost, 2),
            "value": round(cur_val, 2),
            "pl": round(cur_val - cost, 2),
            "pl_pct": round((cur_val - cost) / cost * 100, 1) if cost else None,
        })
    return rows


def print_report(db: DB, config) -> None:
    products = config.products()
    print("\n=== SIGNALS ===")
    for s in signals(db, products):
        tag = {"BUY": "[BUY ]", "SELL": "[SELL]", "HOLD": "[hold]"}[s.kind]
        print(f"{tag} {s.name:<45} {s.reason}")

    rows = inventory_pl(db, products)
    if rows:
        print("\n=== INVENTORY P/L ===")
        total = 0.0
        for r in rows:
            mp = f"£{r['market_price']:.2f}" if r["market_price"] is not None else "n/a"
            pct = f"{r['pl_pct']:+.1f}%" if r["pl_pct"] is not None else ""
            print(f"{r['name']:<40} x{r['qty']}  buy £{r['buy_price']:.2f}  now {mp}  P/L £{r['pl']:+.2f} {pct}")
            total += r["pl"]
        print(f"{'TOTAL unrealised P/L':<40} £{total:+.2f}")
    else:
        print("\n(no open holdings recorded -- add rows to the 'inventory' table to track P/L)")
    print()
