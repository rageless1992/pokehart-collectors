"""SQLite storage for stock checks, price history, inventory, and fired alerts."""

import sqlite3
from pathlib import Path
from typing import List, Optional

from .models import PricePoint, StockResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_checks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT    NOT NULL,
    store      TEXT    NOT NULL,
    in_stock   INTEGER NOT NULL,
    price      REAL,
    currency   TEXT,
    url        TEXT,
    raw_status TEXT,
    checked_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_product ON stock_checks(product_id, store, checked_at);

CREATE TABLE IF NOT EXISTS prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    price       REAL    NOT NULL,
    currency    TEXT,
    kind        TEXT,
    observed_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prices_product ON prices(product_id, source, observed_at);

CREATE TABLE IF NOT EXISTS inventory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT    NOT NULL,
    qty        INTEGER NOT NULL DEFAULT 1,
    buy_price  REAL,
    buy_date   TEXT,
    sold_price REAL,
    sold_date  TEXT,
    notes      TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT,
    type       TEXT,
    message    TEXT,
    created_at TEXT NOT NULL
);

-- Cheapest active Buy-It-Now eBay listing per product (one upserted row each).
CREATE TABLE IF NOT EXISTS ebay_listings (
    product_id  TEXT PRIMARY KEY,
    price       REAL,
    currency    TEXT,
    url         TEXT,
    title       TEXT,
    observed_at TEXT NOT NULL
);
"""


class DB:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)
            self._ensure_columns(con)

    @staticmethod
    def _ensure_columns(con) -> None:
        # Additive migration for eBay-sold metadata (SQLite has no ADD COLUMN IF NOT EXISTS).
        have = {r["name"] for r in con.execute("PRAGMA table_info(prices)")}
        for col, decl in (("sample_size", "INTEGER"), ("price_min", "REAL"),
                          ("price_max", "REAL"), ("sold_at", "TEXT")):
            if col not in have:
                con.execute(f"ALTER TABLE prices ADD COLUMN {col} {decl}")

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5.0)
        con.row_factory = sqlite3.Row
        # WAL + busy_timeout let the poller thread and the ingest server write
        # concurrently without "database is locked". Each thread uses its own
        # connection (created per call here), which is the safe SQLite pattern.
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    # --- writes -------------------------------------------------------------
    def record_stock(self, r: StockResult) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO stock_checks
                   (product_id, store, in_stock, price, currency, url, raw_status, checked_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (r.product_id, r.store, int(r.in_stock), r.price, r.currency,
                 r.url, r.raw_status, r.checked_at.isoformat()),
            )

    def record_price(self, p: PricePoint) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO prices
                   (product_id, source, price, currency, kind, observed_at,
                    sample_size, price_min, price_max, sold_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (p.product_id, p.source, p.price, p.currency, p.kind, p.observed_at.isoformat(),
                 p.sample_size, p.price_min, p.price_max, p.sold_at),
            )

    def record_cheapest_bin(self, product_id: str, price: float, url: str,
                            title: str = "", currency: str = "GBP",
                            observed_at: Optional[str] = None) -> None:
        from .models import utcnow
        ts = observed_at or utcnow().isoformat()
        with self.connect() as con:
            con.execute(
                """INSERT INTO ebay_listings
                   (product_id, price, currency, url, title, observed_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(product_id) DO UPDATE SET
                     price=excluded.price, currency=excluded.currency,
                     url=excluded.url, title=excluded.title,
                     observed_at=excluded.observed_at""",
                (product_id, price, currency, url, title, ts),
            )

    def record_alert(self, product_id: str, type_: str, message: str) -> None:
        from .models import utcnow
        with self.connect() as con:
            con.execute(
                "INSERT INTO alerts (product_id, type, message, created_at) VALUES (?,?,?,?)",
                (product_id, type_, message, utcnow().isoformat()),
            )

    # --- reads --------------------------------------------------------------
    def last_stock(self, product_id: str, store: str) -> Optional[sqlite3.Row]:
        with self.connect() as con:
            cur = con.execute(
                """SELECT * FROM stock_checks
                   WHERE product_id=? AND store=?
                   ORDER BY checked_at DESC LIMIT 1""",
                (product_id, store),
            )
            return cur.fetchone()

    def latest_price(self, product_id: str, source: Optional[str] = None) -> Optional[sqlite3.Row]:
        q = "SELECT * FROM prices WHERE product_id=?"
        args = [product_id]
        if source:
            q += " AND source=?"
            args.append(source)
        q += " ORDER BY observed_at DESC LIMIT 1"
        with self.connect() as con:
            return con.execute(q, args).fetchone()

    def price_history(self, product_id: str, source: Optional[str] = None) -> List[sqlite3.Row]:
        q = "SELECT * FROM prices WHERE product_id=?"
        args = [product_id]
        if source:
            q += " AND source=?"
            args.append(source)
        q += " ORDER BY observed_at ASC"
        with self.connect() as con:
            return con.execute(q, args).fetchall()

    def checkpoint(self) -> None:
        """Flush the WAL side-file into tracker.db on disk. Run after a write pass so
        the committed DB snapshot (and git) actually see the new data."""
        with self.connect() as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def latest_cheapest_bin(self, product_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM ebay_listings WHERE product_id=?", (product_id,)
            ).fetchone()

    def open_holdings(self, product_id: Optional[str] = None) -> List[sqlite3.Row]:
        q = "SELECT * FROM inventory WHERE sold_date IS NULL"
        args = []
        if product_id:
            q += " AND product_id=?"
            args.append(product_id)
        with self.connect() as con:
            return con.execute(q, args).fetchall()
