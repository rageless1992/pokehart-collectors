"""Build store adapter instances from the config 'stores' section."""

import logging
from typing import List

from .awin_store import AwinStore
from .base import StoreAdapter
from .browser_store import BrowserStore
from .generic_html import GenericHtmlStore
from .jsonld_store import JsonLdStore
from .mock_store import MockStore
from .pokemoncenter_uk import PokemonCenterUK
from .shopify_store import ShopifyStore

log = logging.getLogger(__name__)

ADAPTERS = {cls.adapter: cls
            for cls in (MockStore, GenericHtmlStore, PokemonCenterUK, BrowserStore,
                        ShopifyStore, JsonLdStore, AwinStore)}


def build_stores(store_defs: dict) -> List[StoreAdapter]:
    stores = []
    for name, sd in store_defs.items():
        sd = sd or {}
        if sd.get("enabled", True) is False:
            continue  # configured but switched off (e.g. needs Awin/proxy setup)
        adapter = sd.get("adapter", "generic_html")
        cls = ADAPTERS.get(adapter)
        if not cls:
            log.warning("store '%s' uses unknown adapter '%s' -- skipping", name, adapter)
            continue
        stores.append(cls(name=name, settings=sd))
    return stores
