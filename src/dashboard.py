#!/usr/bin/env python3
"""
Smart Package Monitor — Web Dashboard
ECE 510 | IIT | Team 1

TWO WAYS TO RUN:

  Option A — Standalone:
    python3 src/dashboard.py
    Open: http://<pi-ip>:5000

  Option B — Integrated (share already-running SensorMonitor from main.py):
    from dashboard import start_dashboard
    start_dashboard(sensor_monitor)
"""

import os
import sys
import time
import base64
import threading

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from flask import Flask, jsonify, render_template_string

# ── Shared SensorMonitor (set by start_dashboard or __main__) ───────────────
_sensor_monitor = None

def start_dashboard(monitor, host="0.0.0.0", port=5000):
    global _sensor_monitor
    _sensor_monitor = monitor
    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, threaded=True),
        daemon=True, name="dashboard",
    )
    t.start()
    print(f"[Dashboard] Started at http://{host}:{port}")

# ── Reference frame path ─────────────────────────────────────────────────────
def _find_file(*candidates):
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None

REFERENCE_FRAME = _find_file(
    os.path.join(SRC_DIR, "vision", "reference_frame_detected.jpg"),
    "/home/ece510/smart-package-monitor/src/vision/reference_frame_detected.jpg",
)
print(f"[Dashboard] REFERENCE_FRAME = {REFERENCE_FRAME}  (found={bool(REFERENCE_FRAME)})")

app = Flask(__name__)

def image_to_b64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None

# ════════════════════════════════════════════════════════════════════════════
#  API
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/status")
def api_status():
    if _sensor_monitor is not None:
        readings, alert, reasons = _sensor_monitor.get_status()
        sensor_available = True
    else:
        readings = {}
        alert = False
        reasons = []
        sensor_available = False

    x = readings.get("accel_x_g", 0)
    y = readings.get("accel_y_g", 0)
    z = readings.get("accel_z_g", 0)
    net_g = abs((x**2 + y**2 + z**2) ** 0.5 - 1.0) if readings else 0.0

    return jsonify({
        "ok": True,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "alert": alert,
        "reasons": reasons,
        "readings": readings,
        "net_accel_g": round(net_g, 3),
        "sensor_available": sensor_available,
    })


@app.route("/api/snapshot")
def api_snapshot():
    """Serve reference_frame_detected.jpg only when an alarm is active."""
    if _sensor_monitor is not None:
        _, alert, _ = _sensor_monitor.get_status()
    else:
        alert = False

    if alert and REFERENCE_FRAME:
        b64 = image_to_b64(REFERENCE_FRAME)
        if b64:
            mtime = time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(REFERENCE_FRAME)))
            return jsonify({
                "ok": True,
                "image": b64,
                "filename": os.path.basename(REFERENCE_FRAME),
                "captured": mtime,
                "alert": True,
            })

    return jsonify({"ok": False, "image": None, "filename": None, "captured": None, "alert": alert})


# ════════════════════════════════════════════════════════════════════════════
#  Dashboard HTML
# ════════════════════════════════════════════════════════════════════════════

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Smart Package Monitor</title>
<style>
  :root {
    --bg:        #0d1117;
    --surface:   #161b22;
    --surface2:  #1c2330;
    --border:    #30363d;
    --accent:    #58a6ff;
    --ok:        #3fb950;
    --warn:      #d29922;
    --danger:    #f85149;
    --text:      #e6edf3;
    --muted:     #8b949e;
    --mono:      'JetBrains Mono', 'Fira Code', monospace;
    --ui:        'Inter', system-ui, sans-serif;
    --radius:    10px;
    --radius-sm: 6px;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--ui); font-size: 14px; line-height: 1.5; min-height: 100vh; }

  header {
    display: flex; align-items: center; gap: 14px;
    padding: 14px 24px; border-bottom: 1px solid var(--border);
    background: var(--surface); position: sticky; top: 0; z-index: 100;
  }
  .logo { width: 32px; height: 32px; background: var(--accent); border-radius: 8px; display: grid; place-items: center; font-size: 18px; flex-shrink: 0; }
  header h1 { font-size: 15px; font-weight: 600; }
  header p  { font-size: 12px; color: var(--muted); }
  .spacer { flex: 1; }
  #status-badge {
    display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600;
    padding: 5px 12px; border-radius: 20px; border: 1px solid var(--border); transition: all .3s;
  }
  #status-badge .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:.3;} }
  #status-badge.alert { background: #3a1010; border-color: var(--danger); color: var(--danger); }
  #status-badge.alert .dot { background: var(--danger); }

  main { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 20px 24px; max-width: 1280px; margin: 0 auto; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
  .card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
  .card-icon { font-size: 18px; background: var(--surface2); border-radius: var(--radius-sm); width: 36px; height: 36px; display: grid; place-items: center; flex-shrink: 0; }
  .card-title { font-size: 13px; font-weight: 600; }
  .card-sub   { font-size: 11px; color: var(--muted); margin-top: 1px; }
  .card-badge { margin-left: auto; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px; background: var(--surface2); color: var(--muted); border: 1px solid var(--border); transition: all .3s; }

  .sensor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .sensor-tile { background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px; transition: border-color .3s; }
  .sensor-tile.alert-tile { border-color: var(--danger); background: #1a0f0f; }
  .tile-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 6px; }
  .tile-value { font-family: var(--mono); font-size: 22px; font-weight: 700; color: var(--text); line-height: 1; }
  .tile-unit  { font-size: 11px; color: var(--muted); margin-top: 4px; }
  .tile-bar   { margin-top: 8px; height: 3px; background: var(--border); border-radius: 2px; overflow: hidden; }
  .tile-bar-fill { height: 100%; border-radius: 2px; background: var(--accent); width: 0%; transition: width .4s, background .3s; }

  .accel-row { display: flex; gap: 10px; margin-bottom: 12px; }
  .accel-axis { flex: 1; background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 14px; }
  .axis-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 4px; }
  .axis-value { font-family: var(--mono); font-size: 20px; font-weight: 700; }
  .axis-x { color: #ff7b72; } .axis-y { color: #79c0ff; } .axis-z { color: #56d364; }
  .net-accel { background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px; display: flex; align-items: center; gap: 14px; }
  .net-label { font-size: 11px; color: var(--muted); }
  .net-value { font-family: var(--mono); font-size: 28px; font-weight: 700; white-space: nowrap; }
  .net-bar-wrap { flex: 1; }
  .net-bar { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; margin-top: 6px; }
  .net-bar-fill { height: 100%; border-radius: 3px; background: var(--ok); width: 0%; transition: width .4s, background .3s; }
  .threshold-line { font-size: 10px; color: var(--muted); margin-top: 4px; display: flex; justify-content: space-between; }

  .camera-card { grid-column: 1 / -1; }
  .camera-wrap { position: relative; background: #000; border-radius: var(--radius-sm); overflow: hidden; min-height: 220px; display: flex; align-items: center; justify-content: center; }
  #snapshot { display: none; max-width: 100%; max-height: 460px; object-fit: contain; }
  .standby { color: var(--muted); display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 50px; }
  .standby-icon { font-size: 36px; }
  .standby-label { font-size: 13px; color: var(--muted); }
  .standby-sub { font-size: 11px; color: #555; }
  .img-meta { display: flex; gap: 16px; margin-top: 10px; font-size: 11px; color: var(--muted); }
  .img-meta strong { color: var(--text); }

  #alert-banner { grid-column: 1 / -1; background: #2a0f0f; border: 1px solid var(--danger); border-radius: var(--radius); padding: 14px 20px; display: flex; align-items: center; gap: 12px; font-size: 13px; font-weight: 600; color: var(--danger); }
  #alert-banner.hidden { display: none; }
  #alert-reasons { font-weight: 400; color: #ffb3b0; margin-left: 4px; }

  footer { text-align: center; padding: 16px; font-size: 11px; color: var(--muted); border-top: 1px solid var(--border); margin-top: 8px; }
  #last-update { color: var(--accent); }

  @media (max-width: 720px) {
    main { grid-template-columns: 1fr; }
    .camera-card, #alert-banner { grid-column: 1; }
  }
</style>
</head>
<body>

<header>
  <div class="logo">&#128230;</div>
  <div><h1>Smart Package Monitor</h1><p>ECE 510 &middot; IIT &middot; Team 1</p></div>
  <div class="spacer"></div>
  <div id="status-badge"><div class="dot"></div><span id="status-text">NOMINAL</span></div>
</header>

<main>

  <div id="alert-banner" class="hidden">
    &#128680; ALERT DETECTED &mdash; <span id="alert-reasons"></span>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-icon">&#127777;</div>
      <div><div class="card-title">Environment</div><div class="card-sub">AHT20 &middot; I2C &middot; 0x38</div></div>
      <div class="card-badge" id="env-status">OK</div>
    </div>
    <div class="sensor-grid">
      <div class="sensor-tile" id="tile-temp">
        <div class="tile-label">Temperature</div>
        <div class="tile-value" id="val-temp">&mdash;</div>
        <div class="tile-unit">&deg;C &middot; safe 0&ndash;30</div>
        <div class="tile-bar"><div class="tile-bar-fill" id="bar-temp"></div></div>
      </div>
      <div class="sensor-tile" id="tile-hum">
        <div class="tile-label">Humidity</div>
        <div class="tile-value" id="val-hum">&mdash;</div>
        <div class="tile-unit">% RH</div>
        <div class="tile-bar"><div class="tile-bar-fill" id="bar-hum"></div></div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-icon">&#128225;</div>
      <div><div class="card-title">Accelerometer</div><div class="card-sub">ADXL345 &middot; I2C &middot; 0x53</div></div>
      <div class="card-badge" id="accel-status">OK</div>
    </div>
    <div class="accel-row">
      <div class="accel-axis"><div class="axis-label">X</div><div class="axis-value axis-x" id="val-x">&mdash;</div><div class="tile-unit">g</div></div>
      <div class="accel-axis"><div class="axis-label">Y</div><div class="axis-value axis-y" id="val-y">&mdash;</div><div class="tile-unit">g</div></div>
      <div class="accel-axis"><div class="axis-label">Z</div><div class="axis-value axis-z" id="val-z">&mdash;</div><div class="tile-unit">g</div></div>
    </div>
    <div class="net-accel">
      <div>
        <div class="net-label">Net accel (gravity removed)</div>
        <div class="net-value" id="val-net">&mdash; <span style="font-size:14px;color:var(--muted)">g</span></div>
      </div>
      <div class="net-bar-wrap">
        <div class="net-bar"><div class="net-bar-fill" id="bar-net"></div></div>
        <div class="threshold-line"><span>0 g</span><span>&#9888; 0.3</span><span>1.0 g</span></div>
      </div>
    </div>
  </div>

  <div class="card camera-card">
    <div class="card-header">
      <div class="card-icon">&#128247;</div>
      <div><div class="card-title">Surveillance Camera</div><div class="card-sub">Reference frame shown when alarm triggers</div></div>
      <div class="card-badge" id="cam-status">MONITORING</div>
    </div>
    <div class="camera-wrap">
      <img id="snapshot" alt="Detection snapshot"/>
      <div class="standby" id="standby">
        <div class="standby-icon">&#127909;</div>
        <div class="standby-label">Monitoring&hellip;</div>
        <div class="standby-sub">Reference frame will appear when an alarm is triggered</div>
      </div>
    </div>
    <div class="img-meta">
      <div>File: <strong id="img-filename">&mdash;</strong></div>
      <div>Saved: <strong id="img-time">&mdash;</strong></div>
    </div>
  </div>

</main>

<footer>
  ECE 510 &middot; Smart Package Monitor &middot; Raspberry Pi &nbsp;|&nbsp;
  Last updated: <span id="last-update">&mdash;</span>
</footer>

<script>
const POLL = 5000;
function clamp(v,lo,hi){return Math.max(lo,Math.min(hi,v));}

function setTile(tileId, barId, value, lo, hi, isAlert) {
  const tile = document.getElementById(tileId);
  const bar  = document.getElementById(barId);
  const pct  = clamp((value - lo) / (hi - lo) * 100, 0, 100);
  if (bar) { bar.style.width = pct + '%'; bar.style.background = isAlert ? 'var(--danger)' : 'var(--accent)'; }
  tile.classList.toggle('alert-tile', isAlert);
}

async function fetchStatus() {
  try {
    const data = await fetch('/api/status').then(r => r.json());
    if (!data.ok) return;
    const r = data.readings;
    const alert = data.alert;

    document.getElementById('status-badge').classList.toggle('alert', alert);
    document.getElementById('status-text').textContent = alert ? 'ALERT' : 'NOMINAL';

    const banner = document.getElementById('alert-banner');
    if (alert && data.reasons.length) {
      banner.classList.remove('hidden');
      document.getElementById('alert-reasons').textContent = data.reasons.join(' · ');
    } else {
      banner.classList.add('hidden');
    }

    if (r.temp_c != null) {
      document.getElementById('val-temp').textContent = r.temp_c.toFixed(1);
      setTile('tile-temp', 'bar-temp', r.temp_c, 0, 40, r.temp_c < 0 || r.temp_c > 30);
    }
    if (r.hum_pct != null) {
      document.getElementById('val-hum').textContent = r.hum_pct.toFixed(1);
      setTile('tile-hum', 'bar-hum', r.hum_pct, 0, 100, false);
    }

    const envAlert = data.reasons.includes('TEMP') || data.reasons.includes('HUM');
    const eb = document.getElementById('env-status');
    eb.textContent = envAlert ? 'ALERT' : 'OK';
    eb.style.color = envAlert ? 'var(--danger)' : 'var(--ok)';
    eb.style.borderColor = envAlert ? 'var(--danger)' : 'var(--border)';

    if (r.accel_x_g != null) document.getElementById('val-x').textContent = (r.accel_x_g >= 0 ? '+' : '') + r.accel_x_g.toFixed(3);
    if (r.accel_y_g != null) document.getElementById('val-y').textContent = (r.accel_y_g >= 0 ? '+' : '') + r.accel_y_g.toFixed(3);
    if (r.accel_z_g != null) document.getElementById('val-z').textContent = (r.accel_z_g >= 0 ? '+' : '') + r.accel_z_g.toFixed(3);

    const net = data.net_accel_g;
    document.getElementById('val-net').innerHTML = (net != null ? net.toFixed(3) : '&mdash;') + ' <span style="font-size:14px;color:var(--muted)">g</span>';
    if (net != null) {
      const nb = document.getElementById('bar-net');
      nb.style.width = clamp(net / 1.0 * 100, 0, 100) + '%';
      nb.style.background = net > 0.3 ? 'var(--danger)' : net > 0.15 ? 'var(--warn)' : 'var(--ok)';
    }

    const accelAlert = data.reasons.includes('ACCEL');
    const ab = document.getElementById('accel-status');
    ab.textContent = accelAlert ? 'ALERT' : 'OK';
    ab.style.color = accelAlert ? 'var(--danger)' : 'var(--ok)';
    ab.style.borderColor = accelAlert ? 'var(--danger)' : 'var(--border)';

    document.getElementById('last-update').textContent = data.ts;
  } catch(e) { console.error('[status]', e); }
}

async function fetchSnapshot() {
  try {
    const data = await fetch('/api/snapshot').then(r => r.json());
    const img     = document.getElementById('snapshot');
    const standby = document.getElementById('standby');
    const camBadge= document.getElementById('cam-status');

    if (data.alert && data.ok && data.image) {
      img.src = 'data:image/jpeg;base64,' + data.image;
      img.style.display     = 'block';
      standby.style.display = 'none';
      document.getElementById('img-filename').textContent = data.filename;
      document.getElementById('img-time').textContent     = data.captured;
      camBadge.textContent       = 'ALARM';
      camBadge.style.color       = 'var(--danger)';
      camBadge.style.borderColor = 'var(--danger)';
    } else {
      img.style.display     = 'none';
      standby.style.display = 'flex';
      document.getElementById('img-filename').textContent = '\u2014';
      document.getElementById('img-time').textContent     = '\u2014';
      camBadge.textContent       = 'MONITORING';
      camBadge.style.color       = 'var(--muted)';
      camBadge.style.borderColor = 'var(--border)';
    }
  } catch(e) { console.error('[snapshot]', e); }
}

fetchStatus();
fetchSnapshot();
setInterval(fetchStatus,   POLL);
setInterval(fetchSnapshot, POLL);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        from sensors.sensors import SensorMonitor
        _sensor_monitor = SensorMonitor()
        _sensor_monitor.start()
        print("[Dashboard] SensorMonitor started (standalone mode).")
    except Exception as e:
        print(f"[Dashboard] SensorMonitor unavailable: {e}")

    print("=" * 50)
    print("  Smart Package Monitor — Dashboard")
    print("  http://0.0.0.0:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)