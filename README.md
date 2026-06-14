# Pokémon Card Tracker (UK)

Local app to **monitor UK restocks**, **track card/sealed prices over time**, and
**generate buy/sell profit signals** — for sealed boxes, ETBs, packs, and singles.

> **On buying:** this tool does *assisted* buying — the moment something restocks it
> alerts you and gives you the direct product link so *you* check out fast. It does
> **not** auto-checkout. Automated checkout bots violate Pokémon Center / retailer
> terms of service, fight anti-bot systems, and risk account + payment bans. Staying
> assisted keeps your accounts safe and is within the rules.

## Install

```powershell
cd "D:\Project Stock Market\pokemon_tracker"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Quick start (works out of the box with demo data)

```powershell
python run.py seed       # backfill 30 days of mock price history
python run.py prices     # take a price reading now
python run.py report     # print buy/sell signals + inventory P/L
python run.py check      # one restock pass (mock store flips in/out of stock)
python run.py dashboard  # open the Streamlit dashboard in your browser
python run.py monitor    # run the polling loop forever (Ctrl-C to stop); also serves the ingest endpoint
python run.py ingest     # run ONLY the local ingest server for the browser extension
```

For the **browser extension** that covers the bot-walled retailers (Argos, Smyths,
Very, John Lewis, GAME) from your own Chrome, see [extension/README.md](extension/README.md).

## How it's wired

```
config.json ──► scheduler ──► stores/   (restock check)  ──► SQLite ──► alerts
                          └─► prices/   (price reading)  ──► SQLite ──► strategy ──► dashboard
```

- **config.json** is the whole control panel: your watchlist, which stores/sources
  are enabled, alert settings, and poll intervals.
- **stores/** are restock monitors. `mock` runs offline. `generic_html` works for many
  simple UK shops via out-of-stock text markers. `pokemoncenter_uk` is a tuned variant.
- **prices/** are price sources. `mock` is a random walk; `pricecharting` scrapes a
  PriceCharting product page.
- **strategy/analytics.py** turns prices + your targets + holdings into BUY/SELL/HOLD
  signals and unrealised P/L.

## Add a real item to watch

In `config.json` → `watchlist`, add the product and point each store at the real URL:

```json
{
  "id": "destined-rivals-booster-box",
  "name": "Destined Rivals Booster Box",
  "kind": "sealed",
  "stores": {
    "smyths": "https://www.smythstoys.com/uk/en-gb/...",
    "argos":  "https://www.argos.co.uk/product/..."
  },
  "price_sources": {
    "pricecharting": "pokemon-destined-rivals/booster-box"
  },
  "target_buy_price": 90.0,
  "target_sell_price": 140.0
}
```

To enable Discord alerts, paste a webhook URL into `alerts.discord_webhook`.

## How each store's price + stock is read (the three tiers)

Not all UK retailers can be read the same way. After testing, here's the reality:

| Tier | Stores | Adapter | Status |
|------|--------|---------|--------|
| **1 — free & reliable** | Total Cards, 365Games | `shopify` (`/products/<handle>.js`) | ✅ active |
| **1 — free & reliable** | Chaos Cards, Magic Madhouse | `jsonld` (schema.org Product/offers + browser headers) | ✅ active |
| **2 — needs Awin feed** | Argos, Smyths, Very, John Lewis, GAME | `awin` (affiliate datafeed) | ⏸ disabled until you add a feed |
| **3 — no free path** | Pokémon Center, Amazon | — | ⏸ disabled (would need a paid scraper) |

`jsonld` is preferred where it works: it returns the **price even when out of stock**, so price
history keeps building. Tier-3 stores block both browser headers and headless Chromium
(Akamai/DataDome); a real-time read there needs a paid managed scraper (Decodo/ScrapFly/Bright Data).

### Awin setup (unlocks Argos / Smyths / Very / John Lewis / GAME)

This is the legitimate way to get those retailers' price + (roughly daily) availability:

1. Sign up as a publisher at **awin.com** (small refundable verification fee).
2. Apply to each retailer's programme and get approved (needs a website/app).
3. In Awin's UI, **Create-a-Feed** for the retailer, choose CSV with columns incl.
   `merchant_product_id, product_name, store_price, in_stock, ean, aw_deep_link`, and copy the
   **datafeed download URL**.
4. In `config.json`, paste it into that store's `feed_url` and set `"enabled": true`:
   ```json
   "argos": { "adapter": "awin", "enabled": true,
              "feed_url": "https://productdata.awin.com/datafeed/download/apikey/.../", 
              "id_regex": "/product/(\\d+)" }
   ```
   `id_regex` pulls the product id out of each watchlist URL to match feed rows — already set per store.
   You can also point `feed_path` at a downloaded CSV first to test before automating the URL.

Caveat: Awin feeds are **batch (refreshed ~daily)**, great for price + coarse in/out-of-stock,
not second-by-second restocks. The `in_stock` column is advertiser-optional — check it's populated.

## Roadmap ideas

- eBay Browse API price source (free OAuth, live UK resale asking-prices) → sell-side signals
- A paid managed scraper (ScrapFly/Decodo) module for Pokémon Center real-time stock
- Telegram/Pushover alerts
- A "cart deep-link" helper per store for one-click assisted checkout
```
