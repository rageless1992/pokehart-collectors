"""Local HTTP ingest server: receives price/stock observations from the browser
extension and feeds them into the same DB + alert path as the scheduler.

Security: binds 127.0.0.1 only, requires a shared X-Ingest-Token header (so other
sites on the machine can reach the port but can't post valid data), and reflects
CORS only for a configured extension origin.
"""

import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote_plus

from .. import alerts
from ..db import DB
from ..models import PricePoint, StockResult, utcnow
from ..notify import Notifier
from .ebay_agg import aggregate
from .match import Matcher


def ebay_sold_url(query: str, ipg: int = 60) -> str:
    return (f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(query)}"
            f"&LH_Sold=1&LH_Complete=1&_sop=13&_ipg={ipg}")

log = logging.getLogger(__name__)
MAX_BODY = 64 * 1024


def _resolve_token(cfg) -> str:
    tok = os.environ.get("TRACKER_INGEST_TOKEN") or cfg.ingest.get("token")
    if tok:
        return tok
    sidecar = Path(cfg.db_path).parent / "ingest_token.txt"
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8").strip()
    tok = secrets.token_urlsafe(24)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(tok, encoding="utf-8")
    return tok


def _parse_dt(s: str) -> datetime:
    if not s:
        return utcnow()
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return utcnow()


class IngestHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence default per-request stderr logging

    def _cors(self):
        origin = self.server.allowed_origin
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Ingest-Token")
        self.end_headers()

    def do_GET(self):
        path = self.path.rstrip("/")
        if path not in ("/watchlist", "/ebay-targets"):
            return self._send(404, {"error": "not found"})
        if not hmac.compare_digest(self.headers.get("X-Ingest-Token", ""), self.server.token):
            return self._send(401, {"error": "bad or missing X-Ingest-Token"})
        if path == "/watchlist":
            return self._send(200, {"targets": self.server.watchlist})
        return self._send(200, {"targets": self.server.ebay_targets})

    def do_POST(self):
        path = self.path.rstrip("/")
        if path not in ("/ingest", "/ebay"):
            return self._send(404, {"error": "not found"})
        if not hmac.compare_digest(self.headers.get("X-Ingest-Token", ""), self.server.token):
            return self._send(401, {"error": "bad or missing X-Ingest-Token"})
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self._send(413, {"error": "missing or oversized body"})
        try:
            data = json.loads(self.rfile.read(n))
        except Exception:
            return self._send(400, {"error": "invalid json"})

        try:
            if path == "/ebay":
                return self._send(200, self._handle_ebay(data))
            items = data.get("observations") if isinstance(data, dict) else None
            items = items if isinstance(items, list) else [data]
            results = [self._handle_one(o) for o in items]
        except Exception as e:  # never let one bad payload kill the server
            log.warning("ingest handler error: %s", e)
            return self._send(500, {"error": "internal"})
        return self._send(200, {"results": results})

    def _handle_ebay(self, o: dict) -> dict:
        srv = self.server
        pid = o.get("product_id")
        listings = o.get("listings")
        product = srv.product_by_id.get(pid)
        if product is None or not isinstance(listings, list):
            return {"status": "error", "reason": "unknown product_id or missing listings"}
        agg = aggregate(listings, product, max_samples=srv.ebay_max_samples)
        if agg is None:
            return {"status": "no_data", "product_id": pid, "raw": len(listings)}
        pt = PricePoint(
            product_id=pid, source="ebay_sold", price=agg["median"], currency="GBP",
            kind="sold_median", sample_size=agg["n"],
            price_min=agg["min"], price_max=agg["max"],
            sold_at=str(o.get("observed_at") or utcnow().date()),
        )
        srv.db.record_price(pt)
        alerts.evaluate_price(srv.db, srv.notifier, product, agg["median"])
        return {"status": "ok", "product_id": pid, "median": agg["median"], "n": agg["n"]}

    def _handle_one(self, o: dict) -> dict:
        srv = self.server
        store, url, wid = o.get("store"), o.get("product_url"), o.get("watchlist_id")
        if not store or (not url and not wid) or "in_stock" not in o:
            return {"status": "error", "reason": "missing store / product_url / in_stock"}

        match = srv.matcher.resolve(store, url, wid)
        if not match:
            log.info("ingest unmatched: store=%s url=%s", store, url)
            return {"status": "unmatched", "store": store, "url": url}
        product, store_name = match

        price = o.get("price")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None

        result = StockResult(
            product_id=product.id,
            store=store_name,
            in_stock=bool(o.get("in_stock")),
            price=price,
            url=url or product.stores.get(store_name, ""),
            currency=o.get("currency", "GBP"),
            raw_status=str(o.get("raw_status", ""))[:200],
            checked_at=_parse_dt(o.get("observed_at")),
        )
        fired = alerts.evaluate_stock(srv.db, srv.notifier, product, result)

        if result.in_stock and price is not None and srv.record_prices:
            srv.db.record_price(PricePoint(
                product_id=product.id, source=f"retail:{store_name}",
                price=price, currency=result.currency, kind="market",
                observed_at=result.checked_at,
            ))
            alerts.evaluate_price(srv.db, srv.notifier, product, price)

        return {"status": "ok", "product_id": product.id, "store": store_name,
                "restock_alert": fired}


def run_ingest_server(cfg) -> None:
    ing = cfg.ingest
    host, port = ing.get("host", "127.0.0.1"), int(ing.get("port", 8765))
    token = _resolve_token(cfg)

    httpd = ThreadingHTTPServer((host, port), IngestHandler)
    httpd.db = DB(cfg.db_path)
    httpd.notifier = Notifier(cfg.alerts)
    httpd.matcher = Matcher(cfg)
    httpd.token = token
    httpd.allowed_origin = ing.get("allowed_origin") or None
    httpd.record_prices = ing.get("record_price_points", True)

    # Precompute the extension's watch targets: product URLs at the walled stores.
    ext_stores = set(ing.get("extension_stores",
                             ["argos", "smyths", "very", "john_lewis", "game"]))
    httpd.watchlist = [
        {"store": store, "url": url, "product_id": p.id, "name": p.name}
        for p in httpd.matcher.products
        for store, url in (p.stores or {}).items()
        if store in ext_stores
    ]

    # eBay last-sold: targets (one sold-search URL per product with an ebay_query)
    # and the aggregation settings.
    ebay = getattr(cfg, "data", {}).get("ebay", {}) if hasattr(cfg, "data") else {}
    httpd.product_by_id = {p.id: p for p in httpd.matcher.products}
    httpd.ebay_max_samples = int(ebay.get("max_samples", 15))
    ipg = int(ebay.get("ipg", 60))
    httpd.ebay_targets = [
        {"product_id": p.id, "name": p.name, "query": p.ebay_query,
         "url": ebay_sold_url(p.ebay_query, ipg)}
        for p in httpd.matcher.products
        if p.ebay_query and ebay.get("enabled", True)
    ]

    log.info("Ingest server listening on http://%s:%d/ingest", host, port)
    print(f"\n  Ingest endpoint : http://{host}:{port}/ingest")
    print(f"  X-Ingest-Token  : {token}")
    print("  -> paste this token into the browser extension's settings\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Ingest server stopped.")
        httpd.shutdown()
