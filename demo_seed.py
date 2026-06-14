"""Populate the DEMO database (data/demo.db) with realistic-looking sample data so
the dashboard shows a fully 'lit up' state: in-stock rows, price history charts,
buy/sell signals, and inventory P/L. Touches only the demo DB, never tracker.db.

    python demo_seed.py
"""

from tracker.config import load_config
from tracker.db import DB
from tracker.models import StockResult, utcnow
from tracker.prices.mock_price import MockPrice

cfg = load_config("config.demo.json")
db = DB(cfg.db_path)
products = cfg.products()
mock = MockPrice(name="mock")

# 1) 30 days of price history per product -> price charts + latest price for signals.
for p in products:
    for point in mock.backfill(p, days=30):
        db.record_price(point)

# 2) Stock status: make one product IN STOCK (green row + fires a restock alert),
#    leave the others out so the table shows the contrast.
in_stock_id = products[1].id  # Destined Rivals Booster Box
for p in products:
    is_in = p.id == in_stock_id
    price = round((db.latest_price(p.id) or {"price": 0})["price"], 2) if is_in else None
    db.record_stock(StockResult(
        product_id=p.id, store="mock", in_stock=is_in, price=price,
        url=p.stores["mock"], raw_status="demo",
    ))
db.record_alert(in_stock_id, "restock", "mock — back in stock (demo)")

# 3) One open holding so Inventory P/L shows a profit/loss figure.
held = products[0]  # Prismatic ETB
with db.connect() as con:
    con.execute(
        "INSERT INTO inventory (product_id, qty, buy_price, buy_date, notes) VALUES (?,?,?,?,?)",
        (held.id, 3, 30.00, utcnow().isoformat(), "demo holding"),
    )

print("Demo DB seeded at", cfg.db_path)
