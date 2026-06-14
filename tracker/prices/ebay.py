"""Server-side eBay UK SOLD-listing fetch + parse + aggregate (no extension).

Fetch:  a requests.Session with a homepage cookie warm-up + full browser headers
        returns HTTP 200 for sold-search pages (a bare GET 403s). Cookies persist
        between runs; challenges are detected so we record nothing rather than junk.
Parse:  eBay's current ".s-card" / ".su-card-container" markup. Genuine sold cards
        carry a span[aria-label="Sold item"] caption; templates/ads don't. The
        strikethrough price is the WAS price and is rejected.
Aggregate: filter to the right sealed product + variant, bound by kind, take recent
        sales, reject outliers (MAD), then median / trimmed-mean.
"""

import logging
import pickle
import random
import re
import statistics as st
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HOME = "https://www.ebay.co.uk/"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
               "image/webp,*/*;q=0.8"),
    "Accept-Language": "en-GB,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
CHALLENGE_MARKERS = ("pardon our interruption", "px-captcha", "please verify",
                     "splashui", "checkcaptcha")
MONEY_RE = re.compile(r"[0-9][0-9,]*(?:\.[0-9]{2})?")


def sold_url(query: str, ipg: int = 60) -> str:
    return (f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(query)}"
            f"&LH_Sold=1&LH_Complete=1&_sop=13&_ipg={ipg}")


def bin_url(query: str, ipg: int = 60) -> str:
    """Active Buy-It-Now search, sorted price + postage ascending (_sop=15)."""
    return (f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(query)}"
            f"&LH_BIN=1&_sop=15&_ipg={ipg}")


class EbayClient:
    """One warm session reused across products in a run; cookies persisted to disk."""

    def __init__(self, cookie_path: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.cookie_path = Path(cookie_path) if cookie_path else None
        self._warmed = False
        self._load_cookies()

    def _load_cookies(self):
        if self.cookie_path and self.cookie_path.exists():
            try:
                self.session.cookies.update(pickle.loads(self.cookie_path.read_bytes()))
                self._warmed = True
            except Exception:
                pass

    def _save_cookies(self):
        if self.cookie_path:
            try:
                self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
                self.cookie_path.write_bytes(pickle.dumps(self.session.cookies))
            except Exception:
                pass

    def _warm_up(self):
        self.session.get(HOME, headers={"Sec-Fetch-Site": "none"}, timeout=20)
        self._warmed = True
        self._save_cookies()

    def fetch(self, query: str, ipg: int = 60) -> Optional[str]:
        return self.fetch_url(sold_url(query, ipg))

    def fetch_url(self, url: str) -> Optional[str]:
        for attempt, wait in enumerate((0, 5, 12)):
            if wait:
                time.sleep(wait)
            try:
                if not self._warmed:
                    self._warm_up()
                resp = self.session.get(url, timeout=25, headers={
                    "Referer": HOME, "Sec-Fetch-Site": "same-origin"})
            except Exception as e:
                log.warning("[ebay] fetch error for %s: %s", url, e)
                self._warmed = False
                continue
            if resp.status_code == 200 and not self._is_challenge(resp):
                self._save_cookies()
                return resp.text
            log.info("[ebay] %s on a search (attempt %d) -> re-warming", resp.status_code, attempt + 1)
            self._warmed = False
        return None

    @staticmethod
    def _is_challenge(resp) -> bool:
        if resp.status_code in (403, 429) or resp.status_code >= 500:
            return True
        u = resp.url.lower()
        if any(m in u for m in ("splashui", "captcha", "signin")):
            return True
        body = resp.text.lower()
        return any(m in body for m in CHALLENGE_MARKERS)


def parse_sold(html: str) -> List[dict]:
    """Extract genuine sold listings from an eBay UK sold SRP."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select(".su-card-container, .s-card"):
        caption = card.select_one('.s-card__caption span[aria-label="Sold item"]') \
            or card.select_one('.s-card__caption')
        if caption is None or "sold" not in caption.get_text(" ", strip=True).lower():
            continue  # template / non-sold card
        if card.select_one(".s-card__reviews, .s-card__product-reviews"):
            continue  # catalog/active card

        # price: positive, NON-strikethrough price span(s)
        prices = []
        for p in card.select(".s-card__price"):
            classes = p.get("class", [])
            if "strikethrough" in classes:
                continue
            for m in MONEY_RE.findall(p.get_text(" ", strip=True)):
                prices.append(float(m.replace(",", "")))
        if not prices:
            continue

        title_el = card.select_one(".s-card__title")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        cond_el = card.select_one(".s-card__subtitle")
        out.append({
            "price": min(prices),  # for a range, the low (sold) value
            "title": title,
            "sold_date": _parse_sold_date(caption.get_text(" ", strip=True)),
            "condition": cond_el.get_text(" ", strip=True) if cond_el else "",
        })
    return out


def _parse_sold_date(text: str) -> Optional[date]:
    t = re.sub(r"^\s*sold\s*", "", text, flags=re.I).strip()
    for fmt in ("%d %b %Y", "%d %b"):
        try:
            d = datetime.strptime(t, fmt).date()
            if fmt == "%d %b":
                d = d.replace(year=date.today().year)
                if d > date.today():
                    d = d.replace(year=d.year - 1)
            return d
        except ValueError:
            continue
    return None


# --- aggregation ------------------------------------------------------------
KIND_TOKENS = {
    "booster_box": ["booster box", "booster display"],
    "etb": ["elite trainer box", "etb"],
    "etb_pc": ["elite trainer box", "etb"],
    "booster_bundle": ["booster bundle"],
    "booster_pack": ["booster pack"],
    "build_battle": ["build & battle", "build battle", "build and battle"],
}
KIND_BOUNDS = {
    "booster_box": (60, 600),
    "etb": (15, 220),
    "etb_pc": (40, 400),
    "booster_bundle": (8, 130),
    "booster_pack": (2, 40),
    "build_battle": (12, 90),
}
EXCLUDE = [
    "empty", "box only", "no cards", "no packs", "proxy", "repack", "re-pack",
    "resealed", "custom", "job lot", "joblot", "bundle of", "bulk", " lot ",
    "x2", "x3", "x4", "2x", "3x", "4x", "twin pack", "code card", "codes only",
    "online code", "opened", "open box", "pre-owned", "preowned", "single pack",
    "loose pack", "art card", "graded", "psa", "cgc", "beckett", "bgs", "slab",
    "sleeve only", "see description", "read description", "for parts", "japanese",
    "japan", "half booster", "half box", "18 pack", "18 booster", "sleeved booster box",
    "mini tin", "blister", "checklane", "build & battle", "build and battle",
]


def _norm(t: str) -> str:
    t = t.lower().replace("é", "e")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


def _variant_of(tn: str) -> str:
    """tn is a normalized title padded with spaces."""
    if re.search(r"\bjapanese\b|\bjapan\b|\bjp\b", tn):
        return "japanese"
    if "pokemon center" in tn or "pokemon centre" in tn or "pc exclusive" in tn:
        return "pokemon_center"
    return "standard"


def _filter_params(product) -> dict:
    """Per-product matching parameters, shared by sold-aggregation and BIN."""
    kind = product.kind if product.kind in KIND_TOKENS else "etb"
    return {
        "set_tokens": [w for w in re.split(r"[^a-z0-9]+", (product.set_name or "").lower())
                       if len(w) >= 3 or w.isdigit()],
        "kinds": KIND_TOKENS[kind],
        "bounds": KIND_BOUNDS.get(kind, (8, 600)),
        "want_variant": "pokemon_center" if kind == "etb_pc" else "standard",
        # build & battle is a valid kind, so don't let its exclude-token reject it
        "excludes": [x for x in EXCLUDE if not (kind == "build_battle" and "build" in x)],
    }


def _relevant(it: dict, params: dict) -> bool:
    """True if a listing matches the product (right set, kind, variant, price band)."""
    tn = " " + _norm(it.get("title", "")) + " "
    if "pokemon" not in tn:
        return False
    if params["set_tokens"] and not all(
            re.search(rf"\b{re.escape(s)}\b", tn) for s in params["set_tokens"]):
        return False
    if not any(k in tn for k in params["kinds"]):
        return False
    if _variant_of(tn) != params["want_variant"]:   # reject PC<->standard<->Japanese bleed
        return False
    if any(x.strip() in tn for x in params["excludes"]):
        return False
    price = it.get("price")
    lo, hi = params["bounds"]
    return price is not None and lo <= price <= hi


def aggregate(listings: List[dict], product, *, max_samples: int = 15,
              days: int = 45, min_publish: int = 3) -> Optional[dict]:
    params = _filter_params(product)
    kept = [it for it in listings if _relevant(it, params)]

    if not kept:
        return None
    today = date.today()
    kept.sort(key=lambda x: x.get("sold_date") or date.min, reverse=True)
    recent = [x for x in kept if x.get("sold_date") and x["sold_date"] >= today - timedelta(days=days)]
    window = (recent if len(recent) >= max(min_publish, 5) else kept)[:max_samples]

    prices = sorted(x["price"] for x in window)
    if len(prices) < min_publish:
        return None

    med = st.median(prices)
    mad = st.median([abs(p - med) for p in prices])
    if mad > 0:
        sigma = 1.4826 * mad
        prices = [p for p in prices if abs(p - med) <= 3.5 * sigma] or prices

    n = len(prices)
    if n <= 6:
        est = st.median(prices)
    else:
        c = max(1, n // 10)
        est = st.fmean(sorted(prices)[c:n - c])

    dates = [x["sold_date"] for x in window if x.get("sold_date")]
    return {
        "median": round(est, 2),
        "n": n,
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "sold_at": max(dates).isoformat() if dates else str(today),
    }


# --- active Buy-It-Now listings --------------------------------------------
ITM_RE = re.compile(r"/itm/(?:[^/?#]+/)?(\d+)")


def _clean_itm(href: Optional[str]) -> Optional[str]:
    """Strip eBay tracking params -> canonical /itm/<id> URL."""
    m = ITM_RE.search(href or "")
    return f"https://www.ebay.co.uk/itm/{m.group(1)}" if m else None


def _is_sponsored(card) -> bool:
    if card.select_one('.s-card__sponsored, [aria-label="Sponsored"], [aria-label="SPONSORED"]'):
        return True
    return any(n.get_text(strip=True).lower() == "sponsored"
               for n in card.select(".s-card__caption span, .s-card__subtitle span"))


def parse_active(html: str) -> List[dict]:
    """Extract active Buy-It-Now listings (price + canonical item URL) from an SRP."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select(".su-card-container, .s-card"):
        if card.select_one(".s-card__reviews, .s-card__product-reviews"):
            continue  # catalog tile, not a real listing
        link = card.select_one('a.s-card__link, a[href*="/itm/"]')
        url = _clean_itm(link.get("href") if link else None)
        if not url:
            continue  # "Shop on eBay" template / non-listing card
        if _is_sponsored(card):
            continue

        prices = []
        for p in card.select(".s-card__price"):
            if "strikethrough" in p.get("class", []):
                continue
            for m in MONEY_RE.findall(p.get_text(" ", strip=True)):
                prices.append(float(m.replace(",", "")))
        if not prices:
            continue

        title_el = card.select_one(".s-card__title")
        out.append({
            "price": min(prices),
            "url": url,
            "title": title_el.get_text(" ", strip=True) if title_el else "",
        })
    return out


def cheapest_bin(client: "EbayClient", product, ipg: int = 60) -> Optional[dict]:
    """Cheapest active Buy-It-Now listing matching the product, or None.

    Uses the same query/filter as the sold source so the BIN is comparable to the
    sold median. `_sop=15` is only a hint — we always min() over filtered candidates.
    """
    if not getattr(product, "ebay_query", None):
        return None
    html = client.fetch_url(bin_url(product.ebay_query, ipg))
    if not html:
        return None
    params = _filter_params(product)
    candidates = [it for it in parse_active(html) if _relevant(it, params)]
    if not candidates:
        return None
    return min(candidates, key=lambda x: x["price"])
