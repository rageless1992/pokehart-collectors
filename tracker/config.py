"""Load config.json into typed accessors plus a Product watchlist."""

import json
from pathlib import Path
from typing import List, Optional

from .models import PokeSet, Product

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


class Config:
    def __init__(self, data: dict, path: Path):
        self.data = data
        self.path = path

    @property
    def poll_interval(self) -> int:
        return int(self.data.get("poll_interval_seconds", 300))

    @property
    def price_interval(self) -> int:
        return int(self.data.get("price_interval_seconds", 86400))

    @property
    def db_path(self) -> str:
        # Resolve a relative db_path against the project root (config dir), not the
        # current working directory, so the dashboard/CLI find the same DB anywhere.
        p = Path(self.data.get("db_path", "data/tracker.db"))
        if not p.is_absolute():
            p = self.path.parent / p
        return str(p)

    @property
    def alerts(self) -> dict:
        return self.data.get("alerts", {})

    @property
    def store_defs(self) -> dict:
        # Drop "_comment_*" keys used for inline documentation.
        return {k: v for k, v in self.data.get("stores", {}).items() if not k.startswith("_")}

    @property
    def price_source_defs(self) -> dict:
        return {k: v for k, v in self.data.get("price_sources", {}).items() if not k.startswith("_")}

    @property
    def ingest(self) -> dict:
        return self.data.get("ingest", {})

    def sets(self) -> List[PokeSet]:
        out = []
        for sid, s in self.data.get("sets", {}).items():
            if sid.startswith("_"):
                continue
            out.append(PokeSet(
                id=sid, name=s.get("name", sid), code=s.get("code", ""),
                era=s.get("era", ""), release_date=s.get("release_date", ""),
                count=s.get("count"), logo_url=s.get("logo_url", ""),
            ))
        return out

    def set_map(self) -> dict:
        return {s.id: s for s in self.sets()}

    def products(self) -> List[Product]:
        ebay_on = self.data.get("ebay", {}).get("enabled", True)
        out = []
        for p in self.data.get("watchlist", []):
            price_sources = dict(p.get("price_sources", {}))
            if ebay_on and p.get("ebay_query"):
                price_sources.setdefault("ebay_sold", "auto")
            out.append(
                Product(
                    id=p["id"],
                    name=p.get("name", p["id"]),
                    kind=p.get("kind", "sealed"),
                    set_name=p.get("set_name", ""),
                    set_id=p.get("set", ""),
                    image_url=p.get("image_url", ""),
                    stores=p.get("stores", {}),
                    price_sources=price_sources,
                    ebay_query=p.get("ebay_query", ""),
                    target_buy_price=p.get("target_buy_price"),
                    target_sell_price=p.get("target_sell_price"),
                    notes=p.get("notes", ""),
                )
            )
        return out


def load_config(path: Optional[str] = None) -> Config:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Config(data, cfg_path)
