"""
Web dashboard for testing the WhatsApp Stock Alert Bot.

Run separately from the main bot on port 5001:
    python dashboard.py

Open in browser:  http://localhost:5001

Features:
  - Live price table for all 15 symbols (auto-refreshes every 60s)
  - Send test WhatsApp message
  - Trigger price check / news scan manually
  - Add / remove custom symbols
  - View latest market news
  - See which stocks have triggered drop alerts
"""
import json
import os
import sys

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request

load_dotenv()
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

app = Flask(__name__)

# ── HTML template ──────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Alert Bot — Dashboard</title>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --border: #2a2d3a;
    --green: #00c853; --red: #ff1744; --yellow: #ffab00;
    --blue: #2979ff; --text: #e8eaf6; --muted: #8c8fa8;
    --accent: #7c4dff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; font-size: 14px; }

  /* ── Layout ── */
  .topbar { background: var(--card); border-bottom: 1px solid var(--border);
            padding: 14px 28px; display: flex; align-items: center; justify-content: space-between; }
  .topbar h1 { font-size: 18px; font-weight: 600; letter-spacing: .3px; }
  .topbar h1 span { color: var(--accent); }
  .badge { font-size: 11px; padding: 3px 10px; border-radius: 20px; font-weight: 600; }
  .badge.live { background: #00c85322; color: var(--green); border: 1px solid var(--green); }
  .badge.warn { background: #ffab0022; color: var(--yellow); border: 1px solid var(--yellow); }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; padding: 20px 28px; }
  .grid-full { grid-column: 1 / -1; }

  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }
  .card h2 { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase;
             letter-spacing: .6px; margin-bottom: 14px; }

  /* ── Buttons ── */
  .btn { cursor: pointer; border: none; border-radius: 7px; padding: 9px 18px;
         font-size: 13px; font-weight: 600; transition: opacity .15s; }
  .btn:hover { opacity: .85; }
  .btn:active { opacity: .7; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-green   { background: var(--green);  color: #000; }
  .btn-red     { background: var(--red);    color: #fff; }
  .btn-blue    { background: var(--blue);   color: #fff; }
  .btn-outline { background: transparent; color: var(--text); border: 1px solid var(--border); }
  .btn-sm { padding: 5px 12px; font-size: 12px; }
  .btn-row { display: flex; gap: 10px; flex-wrap: wrap; }

  /* ── Table ── */
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 8px 10px; font-size: 11px; color: var(--muted);
       text-transform: uppercase; letter-spacing: .5px; border-bottom: 1px solid var(--border); }
  td { padding: 9px 10px; border-bottom: 1px solid #1e2130; font-size: 13px; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #1e2130; }
  .up   { color: var(--green); font-weight: 600; }
  .dn   { color: var(--red);   font-weight: 600; }
  .alert-badge { font-size: 10px; padding: 2px 7px; border-radius: 10px;
                 font-weight: 700; margin-left: 4px; }
  .alert-drop { background: #ff174422; color: var(--red); border: 1px solid var(--red); }
  .alert-low  { background: #ffab0022; color: var(--yellow); border: 1px solid var(--yellow); }

  /* ── News ── */
  .news-item { padding: 12px 0; border-bottom: 1px solid var(--border); }
  .news-item:last-child { border-bottom: none; }
  .news-title { font-weight: 600; font-size: 13px; margin-bottom: 4px; }
  .news-meta  { font-size: 11px; color: var(--muted); margin-bottom: 6px; }
  .news-summary { font-size: 12px; color: #9ca3c4; line-height: 1.5; }
  .news-link  { font-size: 11px; color: var(--blue); text-decoration: none; margin-top: 4px; display: inline-block; }
  .label-high   { color: var(--red);    font-weight: 700; font-size: 11px; }
  .label-sector { color: var(--yellow); font-weight: 700; font-size: 11px; }
  .label-medium { color: var(--blue);   font-weight: 700; font-size: 11px; }

  /* ── Form ── */
  input[type=text] { background: var(--bg); border: 1px solid var(--border); border-radius: 7px;
                     color: var(--text); padding: 8px 12px; font-size: 13px; width: 100%; }
  input[type=text]:focus { outline: none; border-color: var(--accent); }
  .form-row { display: flex; gap: 8px; margin-bottom: 10px; }
  .form-row input { flex: 1; }

  /* ── Status ── */
  .stat-row { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 4px; }
  .stat { background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
          padding: 10px 16px; flex: 1; min-width: 120px; }
  .stat-val { font-size: 20px; font-weight: 700; margin-bottom: 2px; }
  .stat-lbl { font-size: 11px; color: var(--muted); }

  /* ── Toast ── */
  #toast { position: fixed; bottom: 28px; right: 28px; background: #2a2d3a; color: var(--text);
           padding: 12px 20px; border-radius: 8px; font-size: 13px; font-weight: 500;
           border-left: 3px solid var(--accent); display: none; z-index: 999;
           box-shadow: 0 4px 20px #0008; }

  /* ── Spinner ── */
  .spin { display: inline-block; width: 14px; height: 14px; border: 2px solid #ffffff44;
          border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .refresh-bar { font-size: 11px; color: var(--muted); text-align: right; margin-bottom: 8px; }
  #countdown { color: var(--accent); }

  .empty { color: var(--muted); font-size: 13px; padding: 20px 0; text-align: center; }
</style>
</head>
<body>

<div class="topbar">
  <h1>WhatsApp Stock Alert Bot &nbsp;<span>Dashboard</span></h1>
  <div style="display:flex;gap:10px;align-items:center">
    <span id="env-badge" class="badge warn">checking...</span>
    <span style="color:var(--muted);font-size:12px">NSE India &nbsp;|&nbsp; +91 9486196299</span>
  </div>
</div>

<div class="grid">

  <!-- ── Quick Actions ── -->
  <div class="card">
    <h2>Quick Actions</h2>
    <div class="btn-row">
      <button class="btn btn-green" onclick="sendTest()">📱 Send Test WhatsApp</button>
      <button class="btn btn-primary" onclick="checkPrices()">📊 Check Prices Now</button>
      <button class="btn btn-blue" onclick="fetchNews()">📰 Fetch News Now</button>
    </div>
    <div id="action-status" style="margin-top:12px;font-size:12px;color:var(--muted);min-height:18px"></div>
  </div>

  <!-- ── Stats ── -->
  <div class="card">
    <h2>Watchlist Summary</h2>
    <div class="stat-row" id="stats">
      <div class="stat"><div class="stat-val" id="stat-total">—</div><div class="stat-lbl">Total Symbols</div></div>
      <div class="stat"><div class="stat-val up" id="stat-alerts">—</div><div class="stat-lbl">Drop Alerts</div></div>
      <div class="stat"><div class="stat-val" style="color:var(--yellow)" id="stat-low">—</div><div class="stat-lbl">Near 52w Low</div></div>
      <div class="stat"><div class="stat-val" id="stat-up">—</div><div class="stat-lbl">Up Today</div></div>
    </div>
  </div>

  <!-- ── Price Table ── -->
  <div class="card grid-full">
    <h2>Live Prices</h2>
    <div class="refresh-bar">Auto-refresh in <span id="countdown">60</span>s &nbsp;
      <button class="btn btn-outline btn-sm" onclick="loadPrices()">↻ Refresh</button>
    </div>
    <div id="price-table-wrap">
      <div class="empty"><span class="spin"></span>&nbsp; Loading prices...</div>
    </div>
  </div>

  <!-- ── Add Symbol ── -->
  <div class="card">
    <h2>Add Custom Symbol</h2>
    <div class="form-row">
      <input type="text" id="sym-ticker" placeholder="Ticker  e.g. ZOMATO">
      <input type="text" id="sym-name"   placeholder="Name (optional)">
    </div>
    <div class="form-row">
      <input type="text" id="sym-sector" placeholder="Sector (optional)">
      <button class="btn btn-primary" onclick="addSymbol()">+ Add</button>
    </div>
    <div id="add-status" style="font-size:12px;color:var(--muted);min-height:16px"></div>
  </div>

  <!-- ── Remove Symbol ── -->
  <div class="card">
    <h2>Remove Custom Symbol</h2>
    <p style="font-size:12px;color:var(--muted);margin-bottom:12px">
      Only custom symbols can be removed. Default stocks &amp; ETFs are protected.
    </p>
    <div class="form-row">
      <input type="text" id="rem-ticker" placeholder="Ticker  e.g. ZOMATO">
      <button class="btn btn-red" onclick="removeSymbol()">Remove</button>
    </div>
    <div id="rem-status" style="font-size:12px;color:var(--muted);min-height:16px"></div>
  </div>

  <!-- ── News ── -->
  <div class="card grid-full">
    <h2>Market News &nbsp;<button class="btn btn-outline btn-sm" onclick="loadNews()">↻ Refresh</button></h2>
    <div id="news-wrap">
      <div class="empty">Click Refresh to load news</div>
    </div>
  </div>

</div>

<div id="toast"></div>

<script>
let countdown = 60;

// ── Toast ──────────────────────────────────────────────────────────────────
function toast(msg, color='var(--accent)') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderLeftColor = color;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3500);
}

// ── Check env ──────────────────────────────────────────────────────────────
async function checkEnv() {
  const r = await fetch('/api/env-status');
  const d = await r.json();
  const badge = document.getElementById('env-badge');
  if (d.ok) {
    badge.textContent = 'Configured';
    badge.className = 'badge live';
  } else {
    badge.textContent = 'Not configured';
    badge.className = 'badge warn';
  }
}

// ── Load prices ───────────────────────────────────────────────────────────
async function loadPrices() {
  document.getElementById('price-table-wrap').innerHTML =
    '<div class="empty"><span class="spin"></span>&nbsp; Fetching prices...</div>';
  try {
    const r = await fetch('/api/prices');
    const d = await r.json();
    renderPriceTable(d);
    countdown = 60;
  } catch(e) {
    document.getElementById('price-table-wrap').innerHTML =
      '<div class="empty" style="color:var(--red)">Failed to load prices. Is yfinance installed?</div>';
  }
}

function renderPriceTable(snaps) {
  let alerts = 0, nearLow = 0, up = 0;
  let rows = snaps.map(s => {
    if (s.error) return `<tr><td><b>${s.symbol}</b></td><td colspan="5" style="color:var(--muted)">unavailable</td></tr>`;
    const chgCls = s.day_chg_pct >= 0 ? 'up' : 'dn';
    const chgStr = (s.day_chg_pct >= 0 ? '+' : '') + s.day_chg_pct.toFixed(2) + '%';
    let badge = '';
    if (s.alert_drop)     { badge = '<span class="alert-badge alert-drop">DROP ALERT</span>'; alerts++; }
    else if (s.alert_near_low) { badge = '<span class="alert-badge alert-low">NEAR LOW</span>';  nearLow++; }
    if (s.day_chg_pct > 0) up++;
    return `<tr>
      <td><b>${s.symbol}</b>${badge}</td>
      <td>${s.name}</td>
      <td style="color:var(--text)">₹${s.price.toLocaleString('en-IN', {minimumFractionDigits:2})}</td>
      <td class="${chgCls}">${chgStr}</td>
      <td style="color:var(--muted)">₹${s.high_52w.toLocaleString('en-IN', {minimumFractionDigits:2})}</td>
      <td class="${s.drop_from_high >= 20 ? 'dn' : s.drop_from_high >= 10 ? '' : 'up'}">${s.drop_from_high.toFixed(1)}% below</td>
    </tr>`;
  }).join('');

  document.getElementById('price-table-wrap').innerHTML = `
    <table>
      <thead><tr>
        <th>Symbol</th><th>Name</th><th>Price</th>
        <th>Today</th><th>52W High</th><th>From High</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  document.getElementById('stat-total').textContent  = snaps.length;
  document.getElementById('stat-alerts').textContent = alerts;
  document.getElementById('stat-low').textContent    = nearLow;
  document.getElementById('stat-up').textContent     = up;
}

// ── Send test WhatsApp ─────────────────────────────────────────────────────
async function sendTest() {
  setActionStatus('<span class="spin"></span> Sending WhatsApp...');
  const r = await fetch('/api/test-whatsapp', {method:'POST'});
  const d = await r.json();
  if (d.ok) {
    setActionStatus('✓ WhatsApp sent to +91 9486196299');
    toast('WhatsApp sent!', 'var(--green)');
  } else {
    setActionStatus('✗ Failed: ' + d.error);
    toast('Send failed — check .env credentials', 'var(--red)');
  }
}

// ── Manual price check ────────────────────────────────────────────────────
async function checkPrices() {
  setActionStatus('<span class="spin"></span> Running price check...');
  const r = await fetch('/api/check-prices', {method:'POST'});
  const d = await r.json();
  if (d.alerts > 0) {
    setActionStatus(`✓ Found ${d.alerts} alert(s) — WhatsApp sent`);
    toast(`${d.alerts} alert(s) sent via WhatsApp`, 'var(--yellow)');
  } else {
    setActionStatus('✓ No alerts triggered — all stocks within range');
    toast('Price check done — no alerts', 'var(--green)');
  }
  loadPrices();
}

// ── Fetch news ────────────────────────────────────────────────────────────
async function fetchNews() {
  setActionStatus('<span class="spin"></span> Scanning news...');
  const r = await fetch('/api/fetch-news', {method:'POST'});
  const d = await r.json();
  setActionStatus(`✓ Found ${d.count} new item(s)${d.count > 0 ? ' — WhatsApp sent' : ''}`);
  toast(d.count > 0 ? `${d.count} news item(s) sent` : 'No new news', 'var(--blue)');
  loadNews();
}

// ── Load news display ─────────────────────────────────────────────────────
async function loadNews() {
  document.getElementById('news-wrap').innerHTML =
    '<div class="empty"><span class="spin"></span>&nbsp; Loading news...</div>';
  const r = await fetch('/api/news');
  const d = await r.json();
  if (!d.length) {
    document.getElementById('news-wrap').innerHTML =
      '<div class="empty">No recent news cached. Click "Fetch News Now" to scan.</div>';
    return;
  }
  const labelCls = {high:'label-high', sector:'label-sector', medium:'label-medium'};
  const labelTxt = {high:'URGENT', sector:'SECTOR UPDATE', medium:'MARKET NEWS'};
  document.getElementById('news-wrap').innerHTML = d.map(n => `
    <div class="news-item">
      <div class="news-meta">
        <span class="${labelCls[n.importance]||'label-medium'}">${labelTxt[n.importance]||'NEWS'}</span>
        &nbsp;·&nbsp; ${n.source}
        ${n.sectors.length ? '&nbsp;·&nbsp; ' + n.sectors.join(', ') : ''}
      </div>
      <div class="news-title">${n.title}</div>
      <div class="news-summary">${n.summary}</div>
      ${n.link ? `<a class="news-link" href="${n.link}" target="_blank">Read more →</a>` : ''}
    </div>`).join('');
}

// ── Add symbol ────────────────────────────────────────────────────────────
async function addSymbol() {
  const ticker = document.getElementById('sym-ticker').value.trim();
  if (!ticker) { document.getElementById('add-status').textContent = 'Enter a ticker symbol.'; return; }
  const r = await fetch('/api/add-symbol', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      ticker, name: document.getElementById('sym-name').value.trim(),
      sector: document.getElementById('sym-sector').value.trim()
    })
  });
  const d = await r.json();
  document.getElementById('add-status').textContent = d.message;
  document.getElementById('add-status').style.color = d.ok ? 'var(--green)' : 'var(--red)';
  if (d.ok) { ['sym-ticker','sym-name','sym-sector'].forEach(id => document.getElementById(id).value = ''); loadPrices(); }
}

// ── Remove symbol ─────────────────────────────────────────────────────────
async function removeSymbol() {
  const ticker = document.getElementById('rem-ticker').value.trim();
  if (!ticker) { document.getElementById('rem-status').textContent = 'Enter a ticker symbol.'; return; }
  const r = await fetch('/api/remove-symbol', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ticker})
  });
  const d = await r.json();
  document.getElementById('rem-status').textContent = d.message;
  document.getElementById('rem-status').style.color = d.ok ? 'var(--green)' : 'var(--red)';
  if (d.ok) { document.getElementById('rem-ticker').value = ''; loadPrices(); }
}

function setActionStatus(html) {
  document.getElementById('action-status').innerHTML = html;
}

// ── Countdown auto-refresh ────────────────────────────────────────────────
setInterval(() => {
  countdown--;
  document.getElementById('countdown').textContent = countdown;
  if (countdown <= 0) { loadPrices(); }
}, 1000);

// ── Init ──────────────────────────────────────────────────────────────────
checkEnv();
loadPrices();
</script>
</body>
</html>"""


# ── API routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/env-status")
def env_status():
    ok = bool(
        os.getenv("TWILIO_ACCOUNT_SID") and
        os.getenv("TWILIO_AUTH_TOKEN") and
        os.getenv("WHATSAPP_TO")
    )
    return jsonify({"ok": ok})


@app.route("/api/prices")
def api_prices():
    try:
        from stock_monitor import fetch_snapshots
        from watchlist_manager import get_all_symbols
        snaps = fetch_snapshots(get_all_symbols())
        return jsonify([{
            "symbol":         s.symbol,
            "name":           s.name,
            "sector":         s.sector,
            "price":          s.price,
            "high_52w":       s.high_52w,
            "low_52w":        s.low_52w,
            "day_chg_pct":    s.day_chg_pct,
            "drop_from_high": s.drop_from_high,
            "alert_drop":     s.alert_drop,
            "alert_near_low": s.alert_near_low,
            "error":          s.error,
        } for s in snaps])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-whatsapp", methods=["POST"])
def api_test_whatsapp():
    try:
        from whatsapp import send
        ok = send(
            "Stock Alert Bot is working!\n\n"
            "This is a test message from the dashboard.\n"
            "Your bot is configured correctly."
        )
        return jsonify({"ok": ok, "error": None if ok else "Send failed"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/check-prices", methods=["POST"])
def api_check_prices():
    try:
        from stock_monitor import fetch_snapshots, make_alert_messages
        from watchlist_manager import get_all_symbols
        from whatsapp import send
        snaps  = fetch_snapshots(get_all_symbols())
        alerts = make_alert_messages(snaps)
        for msg in alerts:
            send(msg)
        return jsonify({"alerts": len(alerts)})
    except Exception as e:
        return jsonify({"alerts": 0, "error": str(e)})


@app.route("/api/fetch-news", methods=["POST"])
def api_fetch_news():
    try:
        from news_monitor import fetch_news, format_news
        from watchlist_manager import get_all_symbols
        from whatsapp import send
        sectors = list({v["sector"] for v in get_all_symbols().values()})
        items   = fetch_news(watched_sectors=sectors, max_per_feed=5)
        for item in items:
            send(format_news(item))
        return jsonify({"count": len(items)})
    except Exception as e:
        return jsonify({"count": 0, "error": str(e)})


@app.route("/api/news")
def api_news():
    """Return cached recent news (no re-fetch)."""
    try:
        from news_monitor import fetch_news
        from watchlist_manager import get_all_symbols
        sectors = list({v["sector"] for v in get_all_symbols().values()})
        items = fetch_news(watched_sectors=sectors, max_per_feed=5)
        return jsonify([{
            "title":      i.title,
            "summary":    i.summary[:300],
            "link":       i.link,
            "source":     i.source,
            "importance": i.importance,
            "sectors":    i.sectors,
        } for i in items])
    except Exception as e:
        return jsonify([])


@app.route("/api/add-symbol", methods=["POST"])
def api_add_symbol():
    data   = request.get_json()
    ticker = data.get("ticker", "")
    name   = data.get("name",   "")
    sector = data.get("sector", "Custom")
    try:
        from watchlist_manager import add_symbol
        ok, msg = add_symbol(ticker, name=name, sector=sector)
        return jsonify({"ok": ok, "message": msg})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@app.route("/api/remove-symbol", methods=["POST"])
def api_remove_symbol():
    ticker = request.get_json().get("ticker", "")
    try:
        from watchlist_manager import remove_symbol
        ok, msg = remove_symbol(ticker)
        return jsonify({"ok": ok, "message": msg})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", 5001))
    print(f"\n  Stock Alert Bot — Dashboard")
    print(f"  Open in browser:  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
