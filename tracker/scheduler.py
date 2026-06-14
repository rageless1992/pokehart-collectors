"""The engine: wires config -> stores/prices -> db -> alerts, and runs the loop."""

import logging
import random
import time

from . import alerts
from .config import Config
from .db import DB
from .notify import Notifier
from .prices.ebay import EbayClient, cheapest_bin
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
        self._bin_client = None
        self._bin_cycle = []   # shuffled product list, refilled each full pass
        self._bin_pos = 0

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

    # --- cheapest Buy-It-Now (staggered rolling refresh) --------------------
    def _bin_products(self):
        cfg = self.config.ebay_bin
        if not cfg.get("enabled", True):
            return []
        return [p for p in self.config.products() if p.ebay_query]

    def refresh_bin_batch(self, n: int = None) -> int:
        """Refresh the cheapest BIN for the next `n` products in a rolling cycle.

        Staggered on purpose: a couple per call (with polite jittered gaps) so a full
        pass over the watchlist lands every few hours instead of one synchronized burst.
        Returns the number of products refreshed.
        """
        cfg = self.config.ebay_bin
        products = self._bin_products()
        if not products:
            return 0
        if n is None:
            n = int(cfg.get("batch", 2))
        if self._bin_client is None:
            self._bin_client = EbayClient(cookie_path=cfg.get("cookie_path"))
        ipg = int(cfg.get("ipg", 60))
        delay = cfg.get("delay_seconds", 6)
        jitter = cfg.get("jitter_seconds", 6)

        done = 0
        for i in range(min(n, len(products))):
            if self._bin_pos >= len(self._bin_cycle):
                self._bin_cycle = products[:]
                random.shuffle(self._bin_cycle)      # spread load, avoid fixed order
                self._bin_pos = 0
            product = self._bin_cycle[self._bin_pos]
            self._bin_pos += 1
            if done and delay:                       # polite gap between products
                time.sleep(delay + random.uniform(0, jitter))
            try:
                hit = cheapest_bin(self._bin_client, product, ipg=ipg)
            except Exception as e:                   # one bad product shouldn't kill the pass
                log.warning("[ebay_bin] error for %s: %s", product.id, e)
                hit = None
            done += 1
            if hit:
                self.db.record_cheapest_bin(product.id, hit["price"], hit["url"], hit.get("title", ""))
                log.info("[ebay_bin] %s -> £%.2f", product.id, hit["price"])
            else:
                log.info("[ebay_bin] no active BIN for %s", product.id)
        return done

    def refresh_bin_all(self) -> int:
        """One full pass over every product (used by `run.py refresh-listings`)."""
        return self.refresh_bin_batch(n=len(self._bin_products()))

    # --- loop ---------------------------------------------------------------
    def run(self) -> None:
        log.info("Tracker started. Stock every %ds, prices every %ds, BIN %d/cycle. Ctrl-C to stop.",
                 self.config.poll_interval, self.config.price_interval,
                 int(self.config.ebay_bin.get("batch", 2)))
        next_price = 0.0
        try:
            while True:
                self.check_stock_once()
                now = time.time()
                if now >= next_price:
                    self.fetch_prices_once()
                    next_price = now + self.config.price_interval
                self.refresh_bin_batch()             # rolling cheapest-BIN slice
                time.sleep(self.config.poll_interval)
        except KeyboardInterrupt:
            log.info("Stopped.")
