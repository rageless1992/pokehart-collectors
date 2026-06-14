# PokeStock Local Tracker — Chrome extension

Reads price + stock for the **bot-walled** UK retailers (Argos, Smyths, Very,
John Lewis, GAME) from inside **your own Chrome**, so it inherits the anti-bot
"clearance" and home IP your browser already has — then posts what it sees to your
local tracker app. This is the free way past walls that block server-side scraping.

It works two ways at once:
- **Scheduled:** on a gentle timer it opens each watched product in a background
  tab, reads the price/stock, and closes the tab.
- **Passive:** whenever *you* browse one of those product pages normally, it
  captures that too.

It **also tracks eBay UK last-sold prices**: every 8th tick it opens an eBay
sold/completed search for one product, reads the recent sealed sale prices, and
the app medians them into a "eBay last sold" figure (shown per product in the set
detail view, driving the BUY/SELL signals).

> **After updating the extension files, reload it** at `chrome://extensions`
> (the eBay feature added a new `ebay.co.uk` permission, so Chrome needs the reload).

## Setup

1. **Start the app's ingest server** (it prints your token):
   ```powershell
   cd "D:\Project Pokemon"
   .\.venv\Scripts\Activate.ps1
   python run.py ingest        # or `python run.py monitor` (runs ingest too)
   ```
   Copy the `X-Ingest-Token` it prints (also saved in `data/ingest_token.txt`).

2. **Load the extension** in Chrome:
   - Go to `chrome://extensions`, turn on **Developer mode**.
   - Click **Load unpacked** and select this `extension/` folder.

3. **Configure it:** the options page opens on install (or click *Details → Extension options*).
   - Endpoint: `http://127.0.0.1:8765`
   - Token: paste the one from step 1
   - Click **Test connection** — it should say "Connected ✓ N products to watch".
   - Click **Save**.

That's it. Watched products come from your `config.json` watchlist automatically
(the URLs at argos/smyths/very/john_lewis/game). New in-stock finds fire the same
desktop/Discord alerts as the rest of the app and show on the dashboard.

## Honest caveats

- **Your PC + Chrome must be running** for checks to happen.
- It polls **gently on purpose** (one product at a time, jittered). Don't crank the
  interval down — hammering can get your own IP/session challenged while you shop.
- If a retailer shows a bot-challenge page, that store is **backed off for an hour**
  automatically rather than retried.
- Extraction uses each page's JSON-LD / `__NEXT_DATA__` / add-to-cart button. If a
  retailer redesigns, its extractor may need a tweak in `extract.js` (verify on a
  live page — open the product, check the `ld+json` script or the buy button).
- It never invents data: if it can't read a clear price/stock signal, it stays silent.
