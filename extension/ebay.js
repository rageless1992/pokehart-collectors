/* Content script for eBay UK SOLD-search pages. Scrapes the recent completed
 * sales (price + title) and sends them to the worker, which forwards them to the
 * local app for median aggregation. Runs on pages the worker opens (a product_id
 * is attached there); on pages you browse yourself it still scrapes but the
 * worker ignores it (no product_id to attribute to).
 *
 * NOTE: eBay result markup changes; if results stop coming through, verify the
 * `.s-item` / `.s-item__price` / `.s-item__title` selectors on a live sold page.
 */

function num(s) {
  const m = String(s).replace(/,/g, "").match(/([0-9]+(?:\.[0-9]{2})?)/);
  return m ? parseFloat(m[1]) : null;
}

function scrapeSold() {
  const out = [];
  const cards = document.querySelectorAll("li.s-item, .s-item");
  for (const c of cards) {
    const priceEl = c.querySelector(".s-item__price");
    const titleEl = c.querySelector(".s-item__title");
    if (!priceEl || !titleEl) continue;
    const title = titleEl.textContent.trim();
    if (!title || /shop on ebay/i.test(title)) continue; // skip the template card
    const priceTxt = priceEl.textContent.trim();
    if (/to/i.test(priceTxt)) continue; // skip "£X to £Y" ranges
    const price = num(priceTxt);
    if (price == null) continue;
    out.push({ price, title });
  }
  return out;
}

(function run() {
  // Only act on a sold/completed search results page.
  if (!/LH_Sold=1/.test(location.href) && !/LH_Complete=1/.test(location.href)) return;
  setTimeout(() => {
    let listings;
    try { listings = scrapeSold(); } catch { return; }
    if (listings && listings.length) {
      chrome.runtime.sendMessage({ type: "ebay_listings", listings });
    } else {
      chrome.runtime.sendMessage({ type: "challenge", url: location.href });
    }
  }, 1500);
})();
