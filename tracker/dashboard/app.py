"""PokeHart Collectors — set-gallery dashboard.

Gallery of set tiles -> click a set -> see its products, per-store prices and
eBay last-sold. Run:  python run.py dashboard
"""

import hmac
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from tracker.config import load_config
from tracker.db import DB
from tracker.dashboard import data as D
from tracker.dashboard import branding as B
from tracker.prices.ebay import sold_url

st.set_page_config(page_title="PokeHart Collectors", page_icon=B.make_favicon(), layout="wide")
st.markdown(B.CSS, unsafe_allow_html=True)


def _authed() -> bool:
    """Password gate. Active only when an `app_password` secret is set (so local
    runs stay open; the public deploy requires the password)."""
    try:
        secret = st.secrets.get("app_password", "")
    except Exception:
        secret = ""
    if not secret or st.session_state.get("auth_ok"):
        return True
    st.markdown(B.header_html(), unsafe_allow_html=True)
    pw = st.text_input("Enter the family password to continue", type="password")
    if pw and hmac.compare_digest(pw, str(secret)):
        st.session_state.auth_ok = True
        return True
    if pw:
        st.error("Incorrect password")
    return False


if not _authed():
    st.stop()

_cfg_path = None
if "--config" in sys.argv:
    _cfg_path = sys.argv[sys.argv.index("--config") + 1]
cfg = load_config(_cfg_path)
db = DB(cfg.db_path)

SETS = D.list_sets(cfg)
SETS_BY_CODE = {s.code: s for s in SETS}
NCOLS = 4


# --- router -----------------------------------------------------------------
def go_to_set(code):
    if code:
        st.session_state.selected = code
        st.query_params["set"] = code
    else:
        st.session_state.pop("selected", None)
        st.query_params.clear()


if "selected" not in st.session_state:
    st.session_state.selected = st.query_params.get("set")


# --- gallery ----------------------------------------------------------------
def render_tile(s):
    products = D.products_in_set(cfg, s.id)
    with st.container(border=True, key=f"settile_{s.code}"):
        if s.logo_url:
            _, mid, _ = st.columns([1, 2, 1])   # logo at ~half width, centred
            mid.image(s.logo_url, use_container_width=True)
        else:
            st.markdown(f"### {s.name}")
        st.markdown(f"**{s.name}**")
        meta = f"`{s.code}`"
        if s.count:
            meta += f" · /{s.count}"
        if s.release_date:
            meta += f" · {s.release_date}"
        st.caption(meta)

        cheapest = D.cheapest_price(db, products)
        label = f"{len(products)} product(s)"
        if cheapest:
            label += f" · from £{cheapest:.2f}"
        st.caption(label)
        st.button("View set →", key=f"open_{s.code}", use_container_width=True,
                  on_click=go_to_set, args=(s.code,))


def render_gallery():
    st.markdown(B.header_html(), unsafe_allow_html=True)
    q = st.text_input("Search sets", placeholder="Name or code…").strip().lower()
    sets = [s for s in SETS if not q or q in s.name.lower() or q in s.code.lower()]

    for i in range(0, len(sets), NCOLS):
        cols = st.columns(NCOLS, gap="medium")
        for col, s in zip(cols, sets[i:i + NCOLS]):
            with col:
                try:
                    render_tile(s)
                except Exception as e:
                    st.warning(f"⚠️ Couldn't load set {getattr(s, 'code', '?')}")
                    st.caption(f"{type(e).__name__}: {e}")


# --- detail -----------------------------------------------------------------
def signal_for(product, market):
    if market is None:
        return ""
    if product.target_buy_price is not None and market <= product.target_buy_price:
        return "🟢 BUY"
    if product.target_sell_price is not None and market >= product.target_sell_price:
        return "🔴 SELL"
    return "⚪ HOLD"


PCOLS = 5  # product cards per row
KIND_LABEL = {
    "booster_box": "Booster Box", "etb": "Elite Trainer Box",
    "etb_pc": "Pokémon Center ETB", "booster_bundle": "Booster Bundle",
    "booster_pack": "Booster Pack", "build_battle": "Build & Battle Box",
}


def product_image(p, s):
    return p.image_url or (s.logo_url if s else "") or \
        "https://images.scrydex.com/pokemon/me1-logo/logo"


def render_product_card(p, s):
    with st.container(border=True):
        st.image(product_image(p, s), use_container_width=True)
        st.markdown(f"**{p.name}**")
        st.caption(KIND_LABEL.get(p.kind, p.kind))

        deal = D.cheapest_in_stock_store(db, p)
        if deal:
            store, price, url = deal
            st.markdown(f"#### £{price:.2f}")
            st.caption(f"in stock · {store}")
            st.link_button("Buy ↗", url, use_container_width=True)
        else:
            link = D.first_store_link(p)
            st.caption("Out of stock")
            if link:
                st.link_button(f"Check {link[0]} ↗", link[1], use_container_width=True)

        sold = D.latest_ebay_sold(db, p)
        market = sold["price"] if sold else (deal[1] if deal else None)
        sold_str = f"£{sold['price']:.2f}" if sold else "—"
        st.metric("eBay last sold", sold_str, signal_for(p, market))
        if sold and sold["sample_size"]:
            rng = f" (£{sold['price_min']:.0f}–£{sold['price_max']:.0f})" if sold["price_min"] else ""
            st.caption(f"median of {sold['sample_size']} sold{rng}")
        if p.ebay_query:
            st.markdown(f"[View sold listings ↗]({sold_url(p.ebay_query)})")

        # cheapest active Buy-It-Now listing (with a deal badge vs the sold median)
        bin_row = D.latest_cheapest_bin(db, p)
        if bin_row and bin_row["price"]:
            badge = ""
            if sold and sold["price"]:
                spread = (bin_row["price"] - sold["price"]) / sold["price"] * 100
                badge = (f" · :green[{abs(spread):.0f}% under sold]" if spread <= 0
                         else f" · :red[{spread:.0f}% over sold]")
            st.markdown(f"**Cheapest now: £{bin_row['price']:.2f}**{badge}")
            if bin_row["url"]:
                st.markdown(f"[Buy this on eBay ↗]({bin_row['url']})")
        elif p.ebay_query:
            st.caption("No active BIN listing yet")


def render_detail(s):
    st.button("← Back to all sets", on_click=go_to_set, args=(None,))
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    if s.logo_url:
        c1.image(s.logo_url, use_container_width=True)
    c2.title(s.name)
    meta = f"`{s.code}` · {s.era}"
    if s.count:
        meta += f" · /{s.count} cards"
    if s.release_date:
        meta += f" · released {s.release_date}"
    c2.caption(meta)
    st.divider()

    products = D.products_in_set(cfg, s.id)
    if not products:
        st.info("No products tracked for this set yet.")
        return

    for i in range(0, len(products), PCOLS):
        cols = st.columns(PCOLS, gap="medium")
        for col, p in zip(cols, products[i:i + PCOLS]):
            with col:
                try:
                    render_product_card(p, s)
                except Exception as e:
                    with st.container(border=True):
                        st.warning(f"⚠️ Couldn't load **{getattr(p, 'name', '?')}**")
                        st.caption(f"{type(e).__name__}: {e}")


# --- dispatch ---------------------------------------------------------------
selected = st.session_state.selected
if selected and selected in SETS_BY_CODE:
    render_detail(SETS_BY_CODE[selected])
else:
    render_gallery()
