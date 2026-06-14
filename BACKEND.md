# Backend: keeping the data fresh (hourly listings refresh)

The app shows two eBay numbers per product:

- **eBay last sold** — median of recent *sold* prices (`ebay_sold`, slow cadence ~daily).
- **Cheapest now** — the cheapest *active* Buy-It-Now listing, with a **Buy this on eBay ↗**
  link straight to that listing (`ebay_bin`, refreshed ~hourly).

## How the hourly refresh works

eBay blocks bursts from one IP, so we **don't** scrape all 73 products at once. The cheapest-BIN
refresh is **staggered**: a couple of products each cycle (`ebay_bin.batch`, default 2), in shuffled
order, with polite jittered gaps. A full pass over the watchlist lands **about every 3 hours**
(~0.5 requests/min — very gentle on eBay). Prices rarely move within a few hours, so this stays
fresh while keeping well clear of rate limits. Cookies are reused between runs.

There are two ways to run it. Pick **one**.

### Option A — leave the monitor running (simplest)

```powershell
cd "D:\Project Pokemon"
.\.venv\Scripts\Activate.ps1
python run.py monitor
```

`monitor` already checks stock + refreshes a BIN slice every cycle, so the listings stay ~hourly
fresh for as long as it's running. Closing the window stops it.

### Option B — Windows Task Scheduler (survives reboot, runs headless)

Runs one full BIN pass every 3 hours, even after a restart. A lock file
(`data/refresh-listings.lock`) stops a slow pass overlapping the next trigger.

```powershell
schtasks /Create /TN "PokeHart\EbayBIN" /SC HOURLY /MO 3 /F ^
  /TR "cmd /c cd /d \"D:\Project Pokemon\" && .venv\Scripts\python.exe run.py refresh-listings >> data\refresh-listings.log 2>&1"
```

Check it / run it once now / remove it:

```powershell
schtasks /Run    /TN "PokeHart\EbayBIN"
schtasks /Query  /TN "PokeHart\EbayBIN" /V /FO LIST
schtasks /Delete /TN "PokeHart\EbayBIN" /F
```

> Tweak cadence/volume in `config.json` under `ebay_bin` (`batch`, `delay_seconds`, `jitter_seconds`).
> For ~hourly instead, change `/MO 3` to `/MO 1`.

## Pushing the fresh data to the public site (optional)

The Streamlit Cloud app reads the committed `data/tracker.db` snapshot. To update what your family
sees after a refresh, commit + push the DB. To avoid bloating git history with binary DB diffs,
keep it to **one rolling commit**:

```powershell
cd "D:\Project Pokemon"
git add data/tracker.db
git commit --amend -m "data snapshot" --no-edit
git push --force-with-lease origin main
```

Streamlit Cloud auto-redeploys in ~1 minute. (Datacenters get blocked by eBay, so the scraping must
run here on your home PC — the cloud is just the showcase.)
