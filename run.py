#!/usr/bin/env python
"""Pokemon card tracker CLI.

  python run.py check            one stock pass across all stores
  python run.py prices           one price pass across all sources
  python run.py refresh-listings one full cheapest-Buy-It-Now pass (for Task Scheduler)
  python run.py report           print buy/sell signals + inventory P/L
  python run.py seed             backfill mock price history (demo data)
  python run.py monitor          run the polling loop forever (+ ingest server if enabled)
  python run.py ingest           run only the browser-extension ingest server
  python run.py dashboard        launch the Streamlit dashboard
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from tracker.config import load_config
from tracker.scheduler import Tracker


def _refresh_listings(tracker, cfg) -> int:
    """One full cheapest-BIN pass, guarded by a lock file so overlapping
    Task Scheduler runs (a slow pass + the next hour's trigger) don't pile up."""
    lock = Path(cfg.db_path).parent / "refresh-listings.lock"
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age < 50 * 60:                 # a previous pass is still running
            logging.getLogger("run").warning(
                "refresh-listings already running (lock %.0f min old) — skipping", age / 60)
            return 0                      # stale lock (>50m) falls through and is reclaimed
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(os.getpid()))
        n = tracker.refresh_bin_all()
        logging.getLogger("run").info("refresh-listings: refreshed %d product(s)", n)
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="pokemon-tracker")
    parser.add_argument("command",
                        choices=["check", "prices", "refresh-listings", "report", "seed",
                                 "monitor", "ingest", "dashboard"])
    parser.add_argument("--config", default=None, help="path to config.json")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "dashboard":
        app = Path(__file__).parent / "tracker" / "dashboard" / "app.py"
        return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)])

    cfg = load_config(args.config)
    tracker = Tracker(cfg)

    if args.command == "check":
        tracker.check_stock_once()
    elif args.command == "prices":
        tracker.fetch_prices_once()
    elif args.command == "refresh-listings":
        return _refresh_listings(tracker, cfg)
    elif args.command == "report":
        from tracker.strategy.analytics import print_report
        print_report(tracker.db, cfg)
    elif args.command == "seed":
        from tracker.prices.mock_price import MockPrice
        seeded = 0
        mock = MockPrice(name="mock")
        for product in cfg.products():
            if "mock" not in product.price_sources:
                continue
            for point in mock.backfill(product, days=30):
                tracker.db.record_price(point)
                seeded += 1
        print(f"Seeded {seeded} mock price points. Now run: python run.py report")
    elif args.command == "ingest":
        from tracker.ingest.server import run_ingest_server
        run_ingest_server(cfg)
    elif args.command == "monitor":
        if cfg.ingest.get("enabled", True):
            import threading
            from tracker.ingest.server import run_ingest_server
            threading.Thread(target=run_ingest_server, args=(cfg,), daemon=True).start()
        tracker.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
