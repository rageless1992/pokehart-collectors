/* Content script: reads price + stock from the rendered product page and sends
 * it to the background worker. Runs both on pages YOU browse (passive capture)
 * and on background tabs the worker opens (scheduled checks).
 *
 * Extraction precedence (per design):
 *   1. JSON-LD <script type="application/ld+json"> Product.offers  (Smyths/Very/JL/GAME)
 *   2. __NEXT_DATA__ deep-search for price + availability            (Argos)
 *   3. DOM add-to-cart button state                                 (fallback stock signal)
 * Anything ambiguous -> we send nothing (never fabricate a restock).
 *
 * NOTE: selectors/keys vary by site and change over time. The JSON-LD path is
 * the most durable; verify against a live page and tune if a retailer breaks.
 */

const STORE_BY_HOST = {
  "www.argos.co.uk": "argos",
  "www.smythstoys.com": "smyths",
  "www.very.co.uk": "very",
  "www.johnlewis.com": "john_lewis",
  "www.game.co.uk": "game",
};

const CHALLENGE_MARKERS = [
  "pardon our interruption", "access denied", "unusual traffic",
  "are you a robot", "verifying you are human", "reference #",
];

function isChallengePage() {
  const t = (document.title + " " + (document.body ? document.body.innerText.slice(0, 2000) : "")).toLowerCase();
  return CHALLENGE_MARKERS.some((m) => t.includes(m));
}

const ERROR_MARKERS = [
  "page you're looking for", "page you are looking for", "can't find the page",
  "cannot find the page", "page not found", "hang on", "no longer available",
  "we couldn't find", "sorry, this product",
];

function isErrorPage() {
  // A 404 / removed / redirected-to-listing page. Critical: such pages carry
  // "Add to basket" buttons for *recommended* products, which must never be
  // read as our product being in stock.
  const t = (document.title + " " + (document.body ? document.body.innerText.slice(0, 1500) : "")).toLowerCase();
  return ERROR_MARKERS.some((m) => t.includes(m));
}

function num(v) {
  if (v == null) return null;
  const m = String(v).replace(/,/g, "").match(/(\d+(?:\.\d{1,2})?)/);
  return m ? parseFloat(m[1]) : null;
}

// --- 1. JSON-LD -----------------------------------------------------------
function fromJsonLd() {
  const scripts = document.querySelectorAll('script[type="application/ld+json"]');
  for (const s of scripts) {
    let data;
    try { data = JSON.parse(s.textContent); } catch { continue; }
    for (const node of iterNodes(data)) {
      const types = [].concat(node["@type"] || []);
      if (types.includes("Product") && node.offers) {
        const offer = Array.isArray(node.offers) ? node.offers[0] : node.offers;
        const avail = String(offer.availability || "").toLowerCase();
        return {
          price: num(offer.price ?? offer.lowPrice),
          in_stock: avail.includes("instock") || avail.includes("limitedavailability"),
          has_avail: avail.length > 0,
          raw: avail,
        };
      }
    }
  }
  return null;
}

function* iterNodes(data) {
  if (Array.isArray(data)) { for (const x of data) yield* iterNodes(x); }
  else if (data && typeof data === "object") {
    yield data;
    if (data["@graph"]) yield* iterNodes(data["@graph"]);
  }
}

// --- 2. __NEXT_DATA__ (Argos) --------------------------------------------
function fromNextData() {
  const el = document.getElementById("__NEXT_DATA__");
  if (!el) return null;
  let data;
  try { data = JSON.parse(el.textContent); } catch { return null; }
  let price = null, inStock = null;
  (function walk(o) {
    if (!o || typeof o !== "object") return;
    for (const [k, v] of Object.entries(o)) {
      const key = k.toLowerCase();
      if (price == null && (key === "price" || key === "nowprice" || key === "currentprice") &&
          (typeof v === "number" || typeof v === "string")) price = num(v);
      if (inStock == null && (key === "isinstock" || key === "instock" || key === "available")) {
        if (typeof v === "boolean") inStock = v;
      }
      if (v && typeof v === "object") walk(v);
    }
  })(data);
  if (price == null && inStock == null) return null;
  return { price, in_stock: !!inStock, has_avail: inStock != null, raw: "next_data" };
}

// --- price fallback via meta tags (John Lewis etc.) ----------------------
function priceFromMeta() {
  const sels = [
    'meta[itemprop="price"]',
    'meta[property="product:price:amount"]',
    'meta[property="og:price:amount"]',
    'meta[name="twitter:data1"]',
    '[itemprop="price"]',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el) {
      const v = num(el.getAttribute("content") || el.getAttribute("value") || el.textContent);
      if (v) return v;
    }
  }
  return null;
}

// --- 3. DOM add-to-cart button -------------------------------------------
function fromButton() {
  const text = (document.body ? document.body.innerText : "").toLowerCase();
  const oos = ["out of stock", "sold out", "currently unavailable", "notify me", "coming soon"];
  const ok = ["add to trolley", "add to basket", "add to cart", "add to bag"];
  if (oos.some((m) => text.includes(m))) return { price: null, in_stock: false, has_avail: true, raw: "dom-oos" };
  if (ok.some((m) => text.includes(m))) return { price: null, in_stock: true, has_avail: true, raw: "dom-cta" };
  return null;
}

function extract() {
  const store = STORE_BY_HOST[location.hostname];
  if (!store) return null;
  if (isChallengePage()) return { challenge: true };
  if (isErrorPage()) return null;   // 404 / removed / redirect -> not our product, stay silent

  // REQUIRE real product structured data. This is the guard against 404/listing
  // pages whose recommendation carousels contain "Add to basket" buttons: no
  // Product JSON-LD / __NEXT_DATA__ for the page = not a product page = silent.
  const structured = fromJsonLd() || (store === "argos" ? fromNextData() : null);
  if (!structured) return null;

  const btn = fromButton();                       // corroborating signal only
  const price = structured.price != null ? structured.price : priceFromMeta();

  let in_stock;
  if (structured.has_avail) {
    in_stock = structured.in_stock;
    if (btn && btn.raw === "dom-oos") in_stock = false;  // a clear OOS button overrides stale JSON-LD
  } else if (btn) {
    in_stock = btn.in_stock;                       // only trusted because structured data confirmed a product page
  } else {
    return null;
  }

  return {
    store,
    product_url: location.origin + location.pathname,
    in_stock,
    price,
    currency: "GBP",
    raw_status: structured.raw || (btn && btn.raw) || "",
    observed_at: new Date().toISOString(),
    source: "pokestock-ext/0.1",
  };
}

(function run() {
  // Give SPA hydration a moment to populate JSON-LD / __NEXT_DATA__.
  setTimeout(() => {
    let payload;
    try { payload = extract(); } catch (e) { return; }
    if (!payload) return;
    if (payload.challenge) { chrome.runtime.sendMessage({ type: "challenge", url: location.href }); return; }
    chrome.runtime.sendMessage({ type: "observation", payload });
  }, 1800);
})();
