const FIELDS = { endpoint: "http://127.0.0.1:8765", token: "", tickSeconds: 120, enabled: true };

async function load() {
  const s = await chrome.storage.local.get(FIELDS);
  document.getElementById("endpoint").value = s.endpoint;
  document.getElementById("token").value = s.token;
  document.getElementById("tickSeconds").value = s.tickSeconds;
  document.getElementById("enabled").checked = s.enabled;
}

async function save() {
  const data = {
    endpoint: document.getElementById("endpoint").value.trim().replace(/\/$/, ""),
    token: document.getElementById("token").value.trim(),
    tickSeconds: Math.max(60, parseInt(document.getElementById("tickSeconds").value, 10) || 120),
    enabled: document.getElementById("enabled").checked,
  };
  await chrome.storage.local.set(data);
  chrome.alarms.create("poll", { periodInMinutes: Math.max(1, data.tickSeconds / 60) });
  flash("Saved ✓");
}

async function test() {
  const endpoint = document.getElementById("endpoint").value.trim().replace(/\/$/, "");
  const token = document.getElementById("token").value.trim();
  try {
    const r = await fetch(`${endpoint}/watchlist`, { headers: { "X-Ingest-Token": token } });
    if (r.ok) {
      const j = await r.json();
      flash(`Connected ✓ ${j.targets.length} products to watch`);
    } else {
      flash(`HTTP ${r.status} (check token)`, true);
    }
  } catch (e) {
    flash("Could not reach app (is `run.py ingest` running?)", true);
  }
}

function flash(msg, err) {
  const s = document.getElementById("status");
  s.textContent = msg;
  s.style.color = err ? "crimson" : "green";
  setTimeout(() => (s.textContent = ""), 4000);
}

document.getElementById("save").addEventListener("click", save);
document.getElementById("test").addEventListener("click", test);
load();
