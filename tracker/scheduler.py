"""The engine: wires config -> stores/prices -> db -> alerts, and runs the loop."""

import logging
import time

from . import alerts
from .config import Config
from .db import DB
from .notify import Notifier
from .prices.registry import build_price_sources
from .stores.registry import build_stores

log = logging.getLogger(__name__)


class Tracker:
    def __init__(self, config: Config):
        self.config = config
        self.db = DB(config.db_path)
        self.notifier = Notifier(config.alerts)
        self.stores = build_stores(config.store_defs)
        self.price_sources = build_price_sources(config.price_source_defs)

    # --- stock --------------------------------------------------------------
    def check_stock_once(self) -> None:
        products = self.config.products()
        log.info("Checking stock: %d product(s) across %d store(s)", len(products), len(self.stores))
        for product in products:
            for store in self.stores:
                if store.name not in product.stores:
                    continue
                result = store.check(product)
                if result is None:
                    continue
                fired = alerts.evaluate_stock(self.db, self.notifier, product, result)
                if not fired:
                    log.debug("%s @ %s: %s", product.id, store.name, "in" if result.in_stock else "out")

    # --- prices -------------------------------------------------------------
    def fetch_prices_once(self) -> None:
        products = self.config.products()
        log.info("Fetching prices: %d product(s) across %d source(s)", len(products), len(self.price_sources))
        for product in products:
            for source in self.price_sources:
                if source.name not in product.price_sources:
                    continue
                point = source.fetch(product)
                if point is None:
                    continue
                self.db.record_price(point)
                alerts.evaluate_price(self.db, self.notifier, product, point.price)

    # --- loop ---------------------------------------------------------------
    def run(self) -> None:
        log.info("Tracker started. Stock every %ds, prices every %ds. Ctrl-C to stop.",
                 self.config.poll_interval, self.config.price_interval)
        next_price = 0.0
        try:
            while True:
                self.check_stock_once()
                now = time.time()
                if now >= next_price:
                    self.fetch_prices_once()
                    next_price = now + self.config.price_interval
                time.sleep(self.config.poll_interval)
        except KeyboardInterrupt:
            log.info("Stopped.")
