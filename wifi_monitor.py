from collections import deque
import argparse, threading, webbrowser
from http.server import ThreadingHTTPServer
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, time
import socket


HISTORY_SECONDS = 120
samples = deque()          # (epoch_ms, latency_ms or None)
lock = threading.Lock()
target = {"host": "8.8.8.8", "port": 443}
cfg = {"interval": 0.5}


PAGE_STYLE = r"""
:root {
  --bg: #17181b;
  --card: #26272b;
  --line: #37383d;
  --text: #e8eaed;
  --muted: #a3a6ad;
  --grid: #4a4b50;
  --blue: #4a74f0;
  --yellow: #f5c242;
  --red: #e0503e;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 32px 14px;
  background: radial-gradient(1200px 600px at 50% -10%, #24262c, var(--bg));
  color: var(--text);
  font-family: "Google Sans", Roboto, system-ui, -apple-system, "Segoe UI", sans-serif;
}

.card {
  width: 100%;
  max-width: 980px;
  overflow: hidden;
  background: var(--card);
  border-radius: 30px 30px 10px 10px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.45);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 18px 26px 4px;
}

.title {
  font-size: 18px;
  font-weight: 500;
}

select {
  -webkit-appearance: none;
  appearance: none;
  max-width: 100%;
  padding: 9px 38px 9px 16px;
  background: #32343a url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' fill='none' stroke='%23a3a6ad' stroke-width='2'><path d='M1 1l5 5 5-5'/></svg>") no-repeat right 14px center;
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 99px;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

select:hover {
  border-color: #55575e;
}

select:focus {
  outline: 2px solid var(--blue);
  outline-offset: 1px;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  padding: 14px 26px 16px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 15px;
}

.legend .dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 8px;
  border-radius: 50%;
  vertical-align: -1px;
}

.dot.blue { background: var(--blue); }
.dot.red { background: var(--red); }
.dot.yellow { background: var(--yellow); }

.chart {
  position: relative;
  height: 380px;
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
}

#pause {
  position: absolute;
  top: 14px;
  right: 18px;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 50%;
  background: rgba(128, 128, 135, 0.25);
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s;
}

#pause:hover {
  background: rgba(128, 128, 135, 0.4);
}

.control {
  padding: 14px 26px 20px;
  border-top: 1px solid var(--line);
}

.control label {
  display: block;
  margin-bottom: 12px;
  color: var(--muted);
  font-size: 16px;
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 24px;
}

input[type=range] {
  -webkit-appearance: none;
  appearance: none;
  flex: 1;
  height: 8px;
  margin: 0;
  background: linear-gradient(to right, var(--blue) var(--fill, 25%), #35373d var(--fill, 25%));
  border-radius: 99px;
  outline: none;
  cursor: pointer;
}

input[type=range]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 26px;
  height: 26px;
  background: var(--blue);
  border: 0;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}

input[type=range]::-moz-range-thumb {
  width: 26px;
  height: 26px;
  background: var(--blue);
  border: 0;
  border-radius: 50%;
}

#interval-value {
  min-width: 84px;
  text-align: right;
  font-size: 20px;
  font-weight: 500;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  padding: 18px 8px 22px;
  border-top: 1px solid var(--line);
  text-align: center;
}

.stats span {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 15px;
}

.stats b {
  font-size: 21px;
  font-weight: 500;
}

@media (max-width: 560px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
    row-gap: 16px;
  }

  .chart {
    height: 300px;
  }
}
"""


PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wi-Fi Integrity</title>
  <style>
%STYLE%
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="title">Connection integrity</div>
      <select id="server" aria-label="Server to ping"></select>
    </div>

    <div class="legend">
      <span><i class="dot blue"></i>Latency (ms)</span>
      <span><i class="dot red"></i>Connection drop</span>
      <span><i class="dot yellow"></i>Elevated jitter</span>
    </div>

    <div class="chart">
      <canvas id="chart"></canvas>
      <button id="pause" aria-label="Pause">
        <svg id="pause-icon" width="18" height="18" viewBox="0 0 18 18" fill="currentColor"></svg>
      </button>
    </div>

    <div class="control">
      <label for="interval">Ping interval</label>
      <div class="slider-row">
        <input type="range" id="interval" min="100" max="2000" step="50" value="500">
        <b id="interval-value">500 ms</b>
      </div>
    </div>

    <div class="stats">
      <div><span>Ping</span><b id="current">&ndash;</b></div>
      <div><span>Drop rate</span><b id="drop">0.0%</b></div>
      <div><span>Avg latency</span><b id="average">&ndash;</b></div>
      <div><span>Jitter</span><b id="jitter">&ndash;</b></div>
    </div>
  </div>

  <script>
%SCRIPT%
  </script>
</body>
</html>
"""


PAGE_SCRIPT = r"""
const WINDOW_MS = 25000;
const MIN_Y_MAX = %MIN_Y%;
const PLOT = { left: 56, right: 18, top: 24, bottom: 50 };

const PAUSE_ICON = '<rect x="3" y="2" width="4" height="14" rx="1"/><rect x="11" y="2" width="4" height="14" rx="1"/>';
const PLAY_ICON = '<path d="M5 2.5v13l11-6.5z"/>';

const SERVERS = [
  ['Google DNS \u00b7 8.8.8.8:443', '8.8.8.8', 443],
  ['Google DNS \u00b7 8.8.8.8:53', '8.8.8.8', 53],
  ['Google DNS \u00b7 8.8.4.4:53', '8.8.4.4', 53],
  ['Cloudflare \u00b7 1.1.1.1:443', '1.1.1.1', 443],
  ['Cloudflare \u00b7 1.1.1.1:53', '1.1.1.1', 53],
  ['Cloudflare \u00b7 1.0.0.1:53', '1.0.0.1', 53],
  ['Quad9 \u00b7 9.9.9.9:53', '9.9.9.9', 53],
  ['OpenDNS \u00b7 208.67.222.222:53', '208.67.222.222', 53],
  ['google.com:443', 'google.com', 443],
  ['microsoft.com:443', 'microsoft.com', 443],
  ['amazon.com:443', 'amazon.com', 443],
  ['apple.com:443', 'apple.com', 443],
  ['github.com:443', 'github.com', 443],
  ['wikipedia.org:443', 'wikipedia.org', 443],
];

const $ = id => document.getElementById(id);
const canvas = $('chart');
const ctx = canvas.getContext('2d');

const rootStyle = getComputedStyle(document.documentElement);
const cssVar = name => rootStyle.getPropertyValue(name).trim();
const COLORS = {
  blue: cssVar('--blue'),
  yellow: cssVar('--yellow'),
  red: cssVar('--red'),
  muted: cssVar('--muted'),
  grid: cssVar('--grid'),
  card: cssVar('--card'),
  average: '#8a7d5f',
};

const state = {
  samples: [],
  lastTimestamp: 0,
  generation: 0,
  target: null,
  paused: false,
  pausedAt: 0,
  delay: 700,
  delayTarget: 700,
  yMax: MIN_Y_MAX,
  width: 0,
  height: 0,
};

let serverList = SERVERS;
let intervalTimer;


function addSample(t, v) {
  const previous = [...state.samples].reverse().find(s => s.v != null);
  const jitter = v != null && previous && Math.abs(v - previous.v) > Math.max(25, previous.v * 0.35);
  state.samples.push({ t, v, jitter: Boolean(jitter) });
  state.lastTimestamp = Math.max(state.lastTimestamp, t);
}

function trimSamples() {
  const cutoff = Date.now() - WINDOW_MS - 5000;
  state.samples = state.samples.filter(s => s.t > cutoff);
}

async function pollSamples() {
  try {
    const generation = state.generation;
    const response = await fetch('/api/samples?since=' + state.lastTimestamp, { cache: 'no-store' });
    const rows = await response.json();
    if (generation === state.generation) rows.forEach(([t, v]) => addSample(t, v));
    trimSamples();
  } catch (error) {}
  setTimeout(pollSamples, 300);
}


function buildServerList() {
  const list = SERVERS.slice();
  const target = state.target;
  const known = target && list.some(([, host, port]) => host === target.host && port === target.port);
  if (target && !known) list.unshift([target.host + ':' + target.port, target.host, target.port]);
  return list;
}

function fillServerSelect() {
  const select = $('server');
  serverList = buildServerList();
  select.innerHTML = '';

  serverList.forEach(([label, host, port], index) => {
    const option = document.createElement('option');
    option.value = index;
    option.textContent = label;
    option.selected = Boolean(state.target) && host === state.target.host && port === state.target.port;
    select.appendChild(option);
  });

  const custom = document.createElement('option');
  custom.value = 'custom';
  custom.textContent = 'Custom\u2026';
  select.appendChild(custom);
}

async function setTarget(host, port) {
  const response = await fetch('/api/set?host=' + encodeURIComponent(host) + '&port=' + port);
  if (!response.ok) {
    alert('Invalid host or port');
    return false;
  }
  state.generation++;
  state.samples = [];
  state.lastTimestamp = 0;
  state.target = { host, port };
  return true;
}

async function onServerChange(event) {
  const select = event.target;

  if (select.value === 'custom') {
    const answer = prompt('Enter host:port (e.g. 192.168.1.1:80)', state.target.host + ':' + state.target.port);
    const match = answer && answer.trim().match(/^(.+):(\d{1,5})$/);
    if (match) await setTarget(match[1], Number(match[2]));
    fillServerSelect();
    return;
  }

  const [, host, port] = serverList[Number(select.value)];
  await setTarget(host, port);
}


function applyInterval(ms, notifyServer) {
  const slider = $('interval');
  const fraction = (ms - slider.min) / (slider.max - slider.min);

  slider.value = ms;
  slider.style.setProperty('--fill', fraction * 100 + '%');
  $('interval-value').textContent = ms + ' ms';
  state.delayTarget = Math.max(500, ms + 200);

  if (notifyServer) {
    clearTimeout(intervalTimer);
    intervalTimer = setTimeout(() => fetch('/api/interval?ms=' + ms), 60);
  }
}

function togglePause() {
  state.paused = !state.paused;
  if (state.paused) state.pausedAt = Date.now() - state.delay;
  $('pause-icon').innerHTML = state.paused ? PLAY_ICON : PAUSE_ICON;
}

function resize() {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  state.width = rect.width;
  state.height = rect.height;
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}


function computeView() {
  state.delay += (state.delayTarget - state.delay) * 0.05;
  const now = state.paused ? state.pausedAt : Date.now() - state.delay;

  const inWindow = state.samples.filter(s => s.t >= now - WINDOW_MS && s.t <= now);
  const valid = inWindow.filter(s => s.v != null);
  const average = valid.length ? valid.reduce((sum, s) => sum + s.v, 0) / valid.length : 0;

  const peak = Math.max(MIN_Y_MAX, ...valid.map(s => s.v));
  const yMaxTarget = peak > MIN_Y_MAX ? Math.ceil(peak / 50) * 50 + 20 : MIN_Y_MAX;
  state.yMax += (yMaxTarget - state.yMax) * 0.1;

  const plotWidth = state.width - PLOT.left - PLOT.right;
  const plotHeight = state.height - PLOT.top - PLOT.bottom;
  const base = PLOT.top + plotHeight;

  return {
    now,
    inWindow,
    valid,
    average,
    left: PLOT.left,
    right: state.width - PLOT.right,
    top: PLOT.top,
    base,
    plotWidth,
    x: t => PLOT.left + (t - (now - WINDOW_MS)) / WINDOW_MS * plotWidth,
    y: v => base - Math.min(v, state.yMax) / state.yMax * plotHeight,
  };
}

function buildRuns(samples, view) {
  const runs = [];
  let run = [];

  samples.forEach(s => {
    if (s.v == null) {
      if (run.length) runs.push(run);
      run = [];
    } else {
      run.push({ x: view.x(s.t), y: view.y(s.v), jitter: s.jitter });
    }
  });

  if (run.length) runs.push(run);
  return runs;
}

function traceCurve(points) {
  const n = points.length;
  const slopes = [];
  const tangents = [];

  for (let i = 0; i < n - 1; i++) {
    slopes[i] = (points[i + 1].y - points[i].y) / (points[i + 1].x - points[i].x || 1e-6);
  }

  tangents[0] = slopes[0];
  tangents[n - 1] = slopes[n - 2];
  for (let i = 1; i < n - 1; i++) {
    tangents[i] = slopes[i - 1] * slopes[i] <= 0 ? 0 : (slopes[i - 1] + slopes[i]) / 2;
  }

  for (let i = 0; i < n - 1; i++) {
    if (slopes[i] === 0) {
      tangents[i] = tangents[i + 1] = 0;
      continue;
    }
    const a = tangents[i] / slopes[i];
    const b = tangents[i + 1] / slopes[i];
    const magnitude = a * a + b * b;
    if (magnitude > 9) {
      const scale = 3 / Math.sqrt(magnitude);
      tangents[i] = scale * a * slopes[i];
      tangents[i + 1] = scale * b * slopes[i];
    }
  }

  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 0; i < n - 1; i++) {
    const dx = (points[i + 1].x - points[i].x) / 3;
    ctx.bezierCurveTo(
      points[i].x + dx, points[i].y + tangents[i] * dx,
      points[i + 1].x - dx, points[i + 1].y - tangents[i + 1] * dx,
      points[i + 1].x, points[i + 1].y,
    );
  }
}


function drawAxes(view) {
  const ticks = [0, Math.round(state.yMax / 3), Math.round(state.yMax * 2 / 3), Math.round(state.yMax)];

  ctx.clearRect(0, 0, state.width, state.height);
  ctx.font = '15px system-ui, sans-serif';
  ctx.textBaseline = 'middle';
  ctx.lineWidth = 1;
  ctx.strokeStyle = COLORS.grid;
  ctx.fillStyle = COLORS.muted;
  ctx.textAlign = 'right';

  ticks.forEach(tick => {
    if (tick) {
      ctx.setLineDash([4, 5]);
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      ctx.moveTo(view.left, view.y(tick));
      ctx.lineTo(view.right, view.y(tick));
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    ctx.fillText(tick, view.left - 12, view.y(tick));
  });

  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(view.left, view.base);
  ctx.lineTo(view.right, view.base);
  ctx.stroke();

  ctx.textAlign = 'left';
  ctx.fillText('-25s', view.left - 12, view.base + 34);
  ctx.textAlign = 'right';
  ctx.fillText(state.paused ? 'Paused' : 'Live (Now)', view.right, view.base + 34);
}

function drawSeries(runs, view) {
  const gradient = ctx.createLinearGradient(0, view.top, 0, view.base);
  gradient.addColorStop(0, 'rgba(74, 116, 240, 0.30)');
  gradient.addColorStop(1, 'rgba(74, 116, 240, 0.03)');

  runs.forEach(run => {
    if (run.length < 2) return;
    const first = run[0];
    const last = run[run.length - 1];

    traceCurve(run);
    ctx.lineTo(last.x, view.base);
    ctx.lineTo(first.x, view.base);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    traceCurve(run);
    ctx.strokeStyle = COLORS.blue;
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.stroke();
  });
}

function drawAverage(view) {
  if (!view.valid.length) return;
  ctx.setLineDash([6, 5]);
  ctx.strokeStyle = COLORS.average;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(view.left, view.y(view.average));
  ctx.lineTo(view.right, view.y(view.average));
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawDrops(samples, view) {
  samples.filter(s => s.v == null).forEach(s => {
    const x = view.x(s.t);
    const markerY = view.base - 24;

    ctx.fillStyle = 'rgba(224, 80, 62, 0.16)';
    ctx.fillRect(x - 8, view.top + 4, 16, view.base - view.top - 4);

    ctx.setLineDash([2, 4]);
    ctx.lineCap = 'round';
    ctx.strokeStyle = COLORS.red;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(x, view.top + 4);
    ctx.lineTo(x, view.base);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.lineCap = 'butt';

    ctx.fillStyle = COLORS.red;
    ctx.beginPath();
    ctx.arc(x, markerY, 12, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(x - 4, markerY - 4);
    ctx.lineTo(x + 4, markerY + 4);
    ctx.moveTo(x + 4, markerY - 4);
    ctx.lineTo(x - 4, markerY + 4);
    ctx.stroke();
  });
}

function drawDots(runs) {
  runs.forEach(run => run.forEach(point => {
    ctx.beginPath();
    ctx.arc(point.x, point.y, point.jitter ? 5.5 : 2.8, 0, Math.PI * 2);
    ctx.fillStyle = point.jitter ? COLORS.yellow : COLORS.blue;
    ctx.fill();
  }));
}

function drawHead(samples, view) {
  const latest = [...samples].reverse().find(s => s.t <= view.now && s.v != null);
  if (!latest || state.paused) return;

  const x = Math.min(view.x(latest.t), view.right - 2);
  const y = view.y(latest.v);

  ctx.beginPath();
  ctx.arc(x, y, 12, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(74, 116, 240, 0.25)';
  ctx.fill();

  ctx.beginPath();
  ctx.arc(x, y, 5, 0, Math.PI * 2);
  ctx.fillStyle = COLORS.blue;
  ctx.fill();
  ctx.strokeStyle = COLORS.card;
  ctx.lineWidth = 2;
  ctx.stroke();
}

function updateStats(view) {
  const { inWindow, valid } = view;
  const newest = inWindow[inWindow.length - 1];
  const newestValid = [...inWindow].reverse().find(s => s.v != null);
  const dropRate = inWindow.length ? (inWindow.length - valid.length) / inWindow.length * 100 : 0;

  let totalChange = 0;
  for (let i = 1; i < valid.length; i++) totalChange += Math.abs(valid[i].v - valid[i - 1].v);

  if (newest && newest.v == null) $('current').textContent = 'Timeout';
  else $('current').textContent = newestValid ? Math.round(newestValid.v) + ' ms' : '\u2013';

  $('average').textContent = valid.length ? view.average.toFixed(1) + ' ms' : '\u2013';
  $('drop').textContent = dropRate.toFixed(1) + '%';
  $('drop').style.color = dropRate > 0 ? COLORS.red : '';
  $('jitter').textContent = valid.length > 1 ? (totalChange / (valid.length - 1)).toFixed(1) + ' ms' : '\u2013';
}

function frame() {
  const view = computeView();
  const visible = state.samples.filter(s => s.t >= view.now - WINDOW_MS - 1500 && s.t <= view.now + 1500);
  const runs = buildRuns(visible, view);

  drawAxes(view);

  ctx.save();
  ctx.beginPath();
  ctx.rect(view.left, 0, view.plotWidth, state.height);
  ctx.clip();
  drawSeries(runs, view);
  drawAverage(view);
  drawDrops(visible, view);
  drawDots(runs);
  drawHead(visible, view);
  ctx.restore();

  updateStats(view);
  requestAnimationFrame(frame);
}


async function init() {
  const response = await fetch('/api/target');
  state.target = await response.json();
  applyInterval(Math.min(2000, Math.max(100, state.target.interval_ms)), false);
  state.delay = state.delayTarget;
  fillServerSelect();
  pollSamples();
}

$('pause').onclick = togglePause;
$('interval').oninput = event => applyInterval(Number(event.target.value), true);
$('server').onchange = onServerChange;
new ResizeObserver(resize).observe(canvas);

$('pause-icon').innerHTML = PAUSE_ICON;
resize();
init();
requestAnimationFrame(frame);
"""

PAGE = PAGE_HTML.replace("%STYLE%", PAGE_STYLE).replace("%SCRIPT%", PAGE_SCRIPT)

def make_handler(page):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/api/target":
                with lock:
                    body, ctype = json.dumps({**target, "interval_ms": int(cfg["interval"] * 1000)}).encode(), "application/json"
            elif u.path == "/api/interval":
                try:
                    ms = int(parse_qs(u.query).get("ms", ["0"])[0])
                except ValueError:
                    ms = 0
                if not (50 <= ms <= 5000):
                    self.send_error(400)
                    return
                cfg["interval"] = ms / 1000
                body, ctype = b"{}", "application/json"
            elif u.path == "/api/set":
                q = parse_qs(u.query)
                host = q.get("host", [""])[0].strip()
                try:
                    port = int(q.get("port", ["0"])[0])
                except ValueError:
                    port = 0
                if not host or len(host) > 253 or not (1 <= port <= 65535) or not all(c.isalnum() or c in ".-:" for c in host):
                    self.send_error(400)
                    return
                with lock:
                    target.update(host=host, port=port)
                    samples.clear()
                body, ctype = b"{}", "application/json"
            elif u.path == "/api/samples":
                since = int(parse_qs(u.query).get("since", ["0"])[0])
                with lock:
                    out = [s for s in samples if s[0] > since]
                body, ctype = json.dumps(out).encode(), "application/json"
            elif u.path == "/":
                body, ctype = page.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler

def ping(host, port, timeout):
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return (time.perf_counter() - t0) * 1000
    except OSError:
        return None

def sampler(timeout):
    while True:
        start = time.time()
        with lock:
            host, port = target["host"], target["port"]
        ms = ping(host, port, timeout)
        now = int(start * 1000)
        with lock:
            if (host, port) != (target["host"], target["port"]):
                continue  # target changed mid-ping; discard
            samples.append((now, None if ms is None else round(ms, 1)))
            while samples and samples[0][0] < now - HISTORY_SECONDS * 1000:
                samples.popleft()
        while time.time() < start + cfg["interval"]:   #rechecked live so the slider feels instant
            time.sleep(0.02)


def main():
    ap = argparse.ArgumentParser(description="Wi-Fi integrity graph")
    ap.add_argument("--host", default="8.8.8.8")
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--timeout", type=float, default=1.0, help="threshold in s for a drop to count")
    ap.add_argument("--listen", type=int, default=6767)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--min-y", type=int, default=50, help="lowest top value of the y-axis in ms")
    a = ap.parse_args()

    target.update(host=a.host, port=a.port)
    cfg["interval"] = max(0.05, a.interval)
    threading.Thread(target=sampler, args=(a.timeout,), daemon=True).start()
    page = PAGE.replace("%MIN_Y%", str(a.min_y))
    srv = ThreadingHTTPServer(("127.0.0.1", a.listen), make_handler(page))
    url = f"http://127.0.0.1:{a.listen}/"
    print(f"Pinging {a.host}:{a.port} every {a.interval}s  ->  {url}   (Ctrl+C to stop)")
    if not a.no_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()