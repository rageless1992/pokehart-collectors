"""Turn a list of scraped eBay SOLD listings into one robust 'last sold' figure.

Sold listings are noisy (empty boxes, lots, singles, proxies), so we filter to
genuine sealed sales of the right product, trim outliers, and take the median.
"""

import re
import statistics
from typing import List, Optional

EXCLUDE = (
    "empty", "proxy", "repack", "art only", "damaged", " lot ", "lot of",
    "bundle of", "code card", "opened", "no cards", "single pack", "display only",
    "read description", "x2", "x3", "x4", "job lot",
)

KIND_TOKENS = {
    "booster_box": ["booster box", "booster display"],
    "etb": ["elite trainer box", "etb"],
    "booster_pack": ["booster bundle", "booster pack", "bundle"],
}


def _num(v) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"([0-9][0-9,]*\.?[0-9]*)", str(v).replace(",", ""))
    return float(m.group(1)) if m else None


def aggregate(listings: List[dict], product, max_samples: int = 15) -> Optional[dict]:
    """listings: [{price, title}, ...] already sorted most-recent-sold first."""
    set_tokens = [t for t in re.split(r"[ \-/&]+", (product.set_name or "").lower()) if len(t) > 2]
    kinds = KIND_TOKENS.get(product.kind, [])

    prices = []
    for it in listings:
        title = str(it.get("title", "")).lower()
        price = _num(it.get("price"))
        if price is None or price <= 0:
            continue
        if any(b in f" {title} " for b in EXCLUDE):
            continue
        if kinds and not any(k in title for k in kinds):
            continue
        if set_tokens and not any(t in title for t in set_tokens):
            continue
        prices.append(price)
        if len(prices) >= max_samples:
            break

    if len(prices) < 2:
        return None
    prices.sort()
    k = int(len(prices) * 0.15)
    trimmed = prices[k: len(prices) - k] or prices
    return {
        "median": round(statistics.median(trimmed), 2),
        "n": len(trimmed),
        "min": round(min(trimmed), 2),
        "max": round(max(trimmed), 2),
    }
