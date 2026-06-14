"""Headless-browser store check for bot-protected sites (Pokémon Center, Argos,
Smyths, Very, Chaos Cards, etc.) that block plain HTTP with 403 / JS walls.

Uses Playwright if it's installed; if not, it pauses cleanly (logs once and
returns None) so the rest of the app keeps working on the plain-HTTP stores.

To activate the bot-protected stores:
    .\.venv\Scripts\Activate.ps1
    pip install playwright
    python -m playwright install chromium
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from ..models import Product, StockResult
from .base import DEFAULT_HEADERS, StoreAdapter
from .generic_html import DEFAULT_OOS_MARKERS, PRICE_RE

log = logging.getLogger(__name__)

_playwright_warned = False

DEFAULT_INSTOCK_MARKERS = [
    "add to basket",
    "add to trolley",
    "add to cart",
    "add to bag",
    "buy now",
]


class BrowserStore(StoreAdapter):
    adapter = "browser"

    def check(self, product: Product) -> Optional[StockResult]:
        url = self.url_for(product)
        if not url:
            return None
        html = self._render(url, product)
        if html is None:
            return None
        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True).lower()

        oos = [m.lower() for m in self.settings.get("oos_markers", DEFAULT_OOS_MARKERS)]
        instock = [m.lower() for m in self.settings.get("instock_markers", DEFAULT_INSTOCK_MARKERS)]
        m = PRICE_RE.search(text)
        price = float(m.group(1)) if m else None

        # Conservative precedence to avoid false "in stock" alerts:
        #   1. explicit out-of-stock wording  -> OUT
        #   2. an actual purchase control + a price  -> IN
        #   3. neither (challenge page, cookie wall, JS not rendered) -> UNKNOWN (no alert)
        if any(w in text for w in oos):
            return self._result(product, False, None, url, raw="oos")
        if any(w in text for w in instock) and price is not None:
            return self._result(product, True, price, url, raw="instock-control")
        log.info("[%s] could not determine stock for %s (likely a bot/consent wall) -- skipping",
                 self.name, product.id)
        return None

    def _render(self, url: str, product: Product) -> Optional[str]:
        global _playwright_warned
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            if not _playwright_warned:
                log.warning(
                    "Playwright not installed -- bot-protected stores (%s) are paused. "
                    "Activate them with: pip install playwright && python -m playwright install chromium",
                    self.name,
                )
                _playwright_warned = True
            return None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"],
                                        locale="en-GB")
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)  # let client-side stock state render
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            log.warning("[%s] browser render failed for %s: %s", self.name, product.id, e)
            return None
