/* Background service worker. On a gentle timer it opens, one at a time:
 *   - a watched retailer product page (Argos/Smyths/...) -> price + stock, OR
 *   - an eBay UK SOLD-search page for a product -> last-sold listings.
 * The content scripts scrape the rendered page in YOUR real session and message
 * back; we POST to the local app and close the tab. Also passively forwards
 * retailer product pages you browse yourself.
 */

const DEFAULTS = {
  endpoint: "http://127.0.0.1:8765",
  token: "",
  enabled: true,
  tickSeconds: 120,   // one target per tick
  ebayEvery: 0,       // eBay is now scraped SERVER-SIDE by the app; 0 disables it here. Set >0 to also use the browser for eBay.
};

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
}

chrome.runtime.onInstalled.addListener(async () => { await scheduleAlarm(); chrome.runtime.openOptionsPage(); });
chrome.runtime.onStartup.addListener(scheduleAlarm);

async function scheduleAlarm() {
  const { tickSeconds } = await settings();
  chrome.alarms.create("poll", { periodInMinutes: Math.max(1, tickSeconds / 60) });
}
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "poll") tick().catch(() => {}); });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function tick() {
  const cfg = await settings();
  if (!cfg.enabled || !cfg.token) return;
  await closeStaleTabs();

  const { tickCount = 0 } = await chrome.storage.local.get("tickCount");
  await chrome.storage.local.set({ tickCount: tickCount + 1 });
  const doEbay = cfg.ebayEvery > 0 && tickCount % cfg.ebayEvery === (cfg.ebayEvery - 1);

  if (doEbay) await openEbay(cfg);
  else await openRetailer(cfg);
}

// --- retailer product check -------------------------------------------------
async function openRetailer(cfg) {
  const targets = await fetchTargets(cfg, "/watchlist");
  if (!targets.length) return;
  const { pollIndex = 0 } = await chrome.storage.local.get("pollIndex");
  const t = targets[pollIndex % targets.length];
  await chrome.storage.local.set({ pollIndex: (pollIndex + 1) % targets.length });
  if (await inCooldown(t.store)) return;
  await openTab(t.url, { store: t.store });
}

// --- eBay sold-search check -------------------------------------------------
async function openEbay(cfg) {
  const targets = await fetchTargets(cfg, "/ebay-targets");
  if (!targets.length) return;
  const { ebayIndex = 0 } = await chrome.storage.local.get("ebayIndex");
  const t = targets[ebayIndex % targets.length];
  await chrome.storage.local.set({ ebayIndex: (ebayIndex + 1) % targets.length });
  if (await inCooldown("ebay")) return;
  await openTab(t.url, { store: "ebay", product_id: t.product_id });
}

async function fetchTargets(cfg, path) {
  try {
    const r = await fetch(`${cfg.endpoint}${path}`, { headers: { "X-Ingest-Token": cfg.token } });
    if (r.ok) { const j = await r.json(); return Array.isArray(j.targets) ? j.targets : []; }
  } catch {}
  return [];
}

async function openTab(url, meta) {
  await sleep(Math.random() * 4000); // jitter
  const tab = await chrome.tabs.create({ url, active: false });
  const open = (await chrome.storage.session.get("openTabs")).openTabs || {};
  open[tab.id] = { ...meta, openedAt: Date.now() };
  await chrome.storage.session.set({ openTabs: open });
}

async function closeStaleTabs() {
  const open = (await chrome.storage.session.get("openTabs")).openTabs || {};
  const now = Date.now();
  for (const [id, meta] of Object.entries(open)) {
    if (now - meta.openedAt > 45000) { chrome.tabs.remove(Number(id)).catch(() => {}); delete open[id]; }
  }
  await chrome.storage.session.set({ openTabs: open });
}

async function inCooldown(store) {
  const cd = (await chrome.storage.session.get("cooldown")).cooldown || {};
  return cd[store] && Date.now() < cd[store];
}

// --- receive scraped data ---------------------------------------------------
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === "observation") postObservation(msg.payload);
  else if (msg.type === "ebay_listings") postEbay(msg.listings, sender);
  else if (msg.type === "challenge") handleChallenge(sender);
  if (sender.tab) closeIfOurs(sender.tab.id);
});

async function postObservation(payload) {
  const cfg = await settings();
  if (!cfg.token) return;
  await post(cfg, "/ingest", payload);
}

async function postEbay(listings, sender) {
  const cfg = await settings();
  const open = (await chrome.storage.session.get("openTabs")).openTabs || {};
  const meta = sender.tab && open[sender.tab.id];
  if (!meta || !meta.product_id || !cfg.token) return; // only scheduled eBay tabs have a product_id
  await post(cfg, "/ebay", { product_id: meta.product_id, listings });
}

async function post(cfg, path, body) {
  try {
    await fetch(`${cfg.endpoint}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Ingest-Token": cfg.token },
      body: JSON.stringify(body),
    });
  } catch {}
}

async function handleChallenge(sender) {
  const open = (await chrome.storage.session.get("openTabs")).openTabs || {};
  const store = sender.tab && open[sender.tab.id] && open[sender.tab.id].store;
  if (!store) return;
  const cd = (await chrome.storage.session.get("cooldown")).cooldown || {};
  cd[store] = Date.now() + 60 * 60 * 1000;
  await chrome.storage.session.set({ cooldown: cd });
}

async function closeIfOurs(tabId) {
  const open = (await chrome.storage.session.get("openTabs")).openTabs || {};
  if (open[tabId]) { delete open[tabId]; await chrome.storage.session.set({ openTabs: open }); chrome.tabs.remove(tabId).catch(() => {}); }
}
