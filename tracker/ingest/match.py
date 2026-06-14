"""Map an incoming {store, product_url} from the extension back to a watchlist item.

Reuses the URLs and per-store `id_regex` already in config.json, so there's no
new data to maintain. Match priority: explicit id -> exact URL -> store + id-from-URL.
"""

import re
from typing import Optional, Tuple
from urllib.parse import urlsplit

from ..models import Product


def normalize_url(url: str) -> str:
    try:
        s = urlsplit(url.lower())
    except Exception:
        return (url or "").lower()
    host = s.netloc[4:] if s.netloc.startswith("www.") else s.netloc
    return host + s.path.rstrip("/")


class Matcher:
    def __init__(self, cfg):
        self.products = cfg.products()
        self.id_regex = {}
        for name, sd in cfg.store_defs.items():
            rx = (sd or {}).get("id_regex")
            if rx:
                self.id_regex[name] = re.compile(rx)

        self.by_url = {}
        self.by_store_id = {}
        for p in self.products:
            for store, url in (p.stores or {}).items():
                self.by_url[normalize_url(url)] = (p, store)
                rx = self.id_regex.get(store)
                if rx:
                    m = rx.search(url)
                    if m:
                        self.by_store_id[(store, m.group(1))] = (p, store)

    def resolve(self, store: str, url: str, watchlist_id: str = None) -> Optional[Tuple[Product, str]]:
        # 1. explicit id + store
        if watchlist_id and store:
            for p in self.products:
                if p.id == watchlist_id and store in (p.stores or {}):
                    return (p, store)
        # 2. exact URL
        if url:
            hit = self.by_url.get(normalize_url(url))
            if hit:
                return hit
        # 3. store + id parsed from URL
        if store and url and store in self.id_regex:
            m = self.id_regex[store].search(url)
            if m:
                hit = self.by_store_id.get((store, m.group(1)))
                if hit:
                    return hit
        return None
