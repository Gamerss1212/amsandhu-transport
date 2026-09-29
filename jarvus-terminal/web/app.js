/* Jarvus app: one page, seven views. Talks only to the Jarvus server on this computer. */
"use strict";
const $ = id => document.getElementById(id);
const RM = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
const TITLES = {command: "Command", bots: "Bots", brain: "Brain", strategies: "Strategies", results: "Results", live: "Live money", settings: "Settings"};
let PAGE = "command";
let ST = {}, S = {}, BOTS = [], BRAIN = {}, TR = [], TICK = [], EV = [], SER = {};
let LIB = null, RES = null, BROKERS = null, LIVE = null, ELIG = null, eligAt = 0;
let CHART = {key: null, data: null}, BOOK = null, stateFilter = null, seenRecent = 0, DOWN = 0;

/* ---------------------------------------------------------------- formatting */
const fmt = (v, d = 2) => v == null || isNaN(v) ? "–" : Number(v).toLocaleString(undefined, {maximumFractionDigits: d, minimumFractionDigits: Math.min(d, 2)});
const cur = () => (S.account || ST.account || {}).currency || "USD";
const money = (v, d = 2) => v == null || isNaN(v) ? "–" : (v < 0 ? "-$" : "$") + fmt(Math.abs(v), d);
const sgn = (v, d = 2) => v == null || isNaN(v) ? "–" : (v >= 0 ? "+" : "-") + "$" + fmt(Math.abs(v), d);
const sgn0 = v => v ? sgn(v) : "$0.00";
const pct = (v, d = 1) => v == null || isNaN(v) ? "–" : (100 * v).toFixed(d) + "%";
const spct = (v, d = 2) => v == null || isNaN(v) ? "–" : (v >= 0 ? "+" : "") + (100 * v).toFixed(d) + "%";
const rr = (v, d = 2) => v == null || isNaN(v) ? "–" : (v >= 0 ? "+" : "") + fmt(v, d) + "R";
const big = v => {const a = Math.abs(v); return a >= 1e9 ? (v / 1e9).toFixed(1) + "B" : a >= 1e6 ? (v / 1e6).toFixed(1) + "M" : a >= 1e3 ? (v / 1e3).toFixed(1) + "K" : fmt(v, 0)};
const t = ms => ms ? new Date(ms).toLocaleString() : "–";
const hm = ms => ms ? new Date(ms).toLocaleTimeString([], {hour12: false}) : "–";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const pxf = v => fmt(v, v >= 100 ? 2 : v >= 1 ? 4 : 6);
const sid = v => esc(String(v || "").replace("@low", " · low-fee").replace("@mid", " · 0.2% fees"));
const cls = v => v == null ? "muted" : v >= 0 ? "up" : "dn";
const kv = rows => rows.map(([k, v]) => `<div>${k}</div><div>${v}</div>`).join("");
const FAMNAME = f => String(f || "").replace(/_/g, " ");
const FEENAME = {venue: "each bot's exchange", coinbase: "Coinbase", kraken: "Kraken", ndax: "NDAX", low_fee: "low-fee"};

/* ---------------------------------------------------------------- server */
async function get(p) {
  const r = await fetch(p, {cache: "no-store"});
  if (!r.ok && r.status !== 400) throw new Error(`${p}: HTTP ${r.status}`);
  return r.json();
}
const getF = p => get("/api/f/" + p);
async function post(p, body) {
  const r = await fetch(p, {method: "POST", headers: {"Content-Type": "application/json", "X-Jarvus": "1"}, body: JSON.stringify(body || {})});
  let j = {};
  try { j = await r.json(); } catch (e) { j = {error: `HTTP ${r.status}`}; }
  return j;
}
function toast(msg, kind = "") {
  const d = document.createElement("div");
  d.className = kind; d.textContent = msg; $("toast").appendChild(d);
  setTimeout(() => d.remove(), kind === "err" ? 9000 : 5000);
}
async function command(cmd, args = {}, quiet = false) {
  const j = await post("/api/command", {command: cmd, args});
  if (j.error) toast(String(j.error).replace(/^ValueError: /, ""), "err");
  else if (!quiet) toast(j.status === "queued" ? "Queued: applies when the bots are running." : "Done.", "ok");
  refresh();
  return j;
}

/* ---------------------------------------------------------------- router */
function show(page) {
  if (!TITLES[page]) page = "command";
  PAGE = page;
  for (const s of document.querySelectorAll(".page")) s.classList.toggle("on", s.id === "p-" + page);
  for (const a of $("nav").children) a.classList.toggle("on", a.dataset.page === page);
  $("pageTitle").textContent = TITLES[page];
  document.title = "Jarvus · " + TITLES[page];
  $("drawer").classList.remove("open");
  for (const c of document.querySelectorAll(`#p-${page} canvas`)) c.width = 0;       // re-fit canvases that were hidden
  if (page === "strategies") loadLibrary();
  if (page === "results") loadResults();
  if (page === "live") loadLive(true);
  if (page === "settings") loadFees();
  renderPage();
  if (page === "command") loadChart();
}
window.addEventListener("hashchange", () => show(location.hash.slice(1)));

/* ---------------------------------------------------------------- clock */
function tickClock() {
  const d = new Date();
  $("clk").textContent = d.toLocaleTimeString([], {hour12: false});
  $("clkd").textContent = d.toLocaleDateString([], {weekday: "short", month: "short", day: "numeric"}).toUpperCase();
}
setInterval(tickClock, 1000); tickClock();

/* ---------------------------------------------------------------- canvases */
function fit(c) {
  const r = c.getBoundingClientRect(), d = devicePixelRatio || 1;
  if (!c.dataset.h) { const hh = c.id === "net" ? c.clientHeight : (parseFloat(c.getAttribute("height")) || 150); if (hh) c.dataset.h = hh; }
  const h = +c.dataset.h || 0;
  if (c.width !== Math.round(r.width * d)) { c.width = Math.round(r.width * d); c.height = Math.round(h * d); }
  const x = c.getContext("2d"); x.setTransform(d, 0, 0, d, 0, 0);
  return [x, r.width, h];
}
function emptyMsg(x, msg) { x.fillStyle = "#5e4d5c"; x.font = "10px monospace"; x.fillText(msg, 8, 18); }
function curve(c, vals, color, empty) {
  const [x, w, h] = fit(c); x.clearRect(0, 0, w, h);
  if (!vals || vals.length < 2) return emptyMsg(x, empty || "waiting for data");
  const mn = Math.min(0, ...vals), mx = Math.max(...vals), px = i => 4 + i * (w - 8) / (vals.length - 1), py = v => h - 6 - (mx === mn ? .5 : (v - mn) / (mx - mn)) * (h - 14);
  const g = x.createLinearGradient(0, 0, 0, h); g.addColorStop(0, color + "55"); g.addColorStop(1, color + "00");
  x.beginPath(); vals.forEach((v, i) => i ? x.lineTo(px(i), py(v)) : x.moveTo(px(i), py(v))); x.lineTo(px(vals.length - 1), h); x.lineTo(px(0), h); x.closePath(); x.fillStyle = g; x.fill();
  x.beginPath(); vals.forEach((v, i) => i ? x.lineTo(px(i), py(v)) : x.moveTo(px(i), py(v))); x.strokeStyle = color; x.lineWidth = 2; x.shadowColor = color; x.shadowBlur = 10; x.stroke(); x.shadowBlur = 0;
  if (mn < 0) { x.strokeStyle = "#3a1633"; x.setLineDash([3, 4]); x.beginPath(); x.moveTo(0, py(0)); x.lineTo(w, py(0)); x.stroke(); x.setLineDash([]); }
}
function minibars(c, vals, color, empty) {
  const [x, w, h] = fit(c); x.clearRect(0, 0, w, h);
  if (!vals.length || !vals.some(v => v)) return emptyMsg(x, empty || "–");
  const mx = Math.max(...vals.map(Math.abs)) || 1, bw = w / vals.length; x.fillStyle = color; x.shadowColor = color; x.shadowBlur = 6;
  vals.forEach((v, i) => { const bh = Math.max(1, Math.abs(v) / mx * (h - 4)); x.globalAlpha = .55 + .45 * (i / vals.length); x.fillRect(i * bw + .5, h - bh, Math.max(1, bw - 1.5), bh); });
  x.globalAlpha = 1; x.shadowBlur = 0;
}
function candles(c, d) {
  const [x, w, h] = fit(c); x.clearRect(0, 0, w, h); x.font = "10px monospace";
  const n = Math.min(90, (d.c || []).length);
  if (n < 2) return emptyMsg(x, ST.running ? "waiting for price data" : "the bots are stopped: start them in Settings");
  const o = d.o.slice(-n), hi = d.h.slice(-n), lo = d.l.slice(-n), cl = d.c.slice(-n), mn = Math.min(...lo), mx = Math.max(...hi), last = cl[n - 1], tag = pxf(last);
  x.font = "bold 11px monospace"; const tw = x.measureText(tag).width + 12;
  const pl = 4, pr = tw + 6, pt = 10, pb = 18, cw = (w - pl - pr) / n, py = v => pt + (mx - v) / (mx - mn || 1) * (h - pt - pb);
  x.strokeStyle = "#1d0f1b"; x.lineWidth = 1;
  for (let k = 1; k < 5; k++) { const y = pt + k * (h - pt - pb) / 5; x.beginPath(); x.moveTo(0, y); x.lineTo(w - pr, y); x.stroke(); }
  const ref = cl[0]; x.strokeStyle = "rgba(255,110,196,.35)"; x.setLineDash([2, 4]); x.beginPath(); x.moveTo(0, py(ref)); x.lineTo(w - pr, py(ref)); x.stroke(); x.setLineDash([]);
  for (let i = 0; i < n; i++) {
    const up = cl[i] >= o[i], col = up ? "#2ee6a6" : "#ff3d63", X = pl + i * cw + cw / 2; x.strokeStyle = col; x.fillStyle = col; x.lineWidth = 1;
    x.beginPath(); x.moveTo(X, py(hi[i])); x.lineTo(X, py(lo[i])); x.stroke();
    const y1 = py(Math.max(o[i], cl[i])), y2 = py(Math.min(o[i], cl[i])); x.globalAlpha = .9; x.fillRect(X - Math.max(1, cw * .32), y1, Math.max(2, cw * .64), Math.max(1, y2 - y1)); x.globalAlpha = 1;
  }
  const y = py(last); x.strokeStyle = "rgba(255,45,149,.6)"; x.beginPath(); x.moveTo(pl + (n - 1) * cw + cw / 2, y); x.lineTo(w - pr, y); x.stroke();
  x.fillStyle = "#ff2d95"; x.shadowColor = "#ff2d95"; x.shadowBlur = 14; x.fillRect(w - tw - 2, y - 10, tw, 20); x.shadowBlur = 0; x.fillStyle = "#16020d"; x.fillText(tag, w - tw + 4, y + 4);
  x.font = "9.5px monospace"; x.fillStyle = "#5e4d5c"; x.fillText(new Date(d.t[d.t.length - n]).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", hour12: false}), 4, h - 4);
  x.textAlign = "right"; x.fillText(LIVE && LIVE.armed ? "PAPER + LIVE (ARMED)" : "PAPER · SIMULATED FILLS", w - pr - 4, h - 4); x.textAlign = "start"; x.fillText(pxf(mx), 4, pt + 8);
}

/* ---------------------------------------------------------------- hive mind swarm */
const FAM = {trend_following: "TREND", opening_range: "ORB", gaps: "GAP", reference_levels: "LEVEL", vwap: "VWAP", market_profile: "PROFILE", momentum: "MOM", mean_reversion: "REVERT",
  volatility: "VOL", candlestick: "CANDLE", market_structure: "STRUCT", volume: "VOLUME", time_of_day: "CLOCK", scheduled_events: "EVENT", cross_asset: "CROSS", crypto_structure: "FUNDING",
  order_flow: "FLOW", statistical: "STAT", machine_learning: "ML", market_making_arbitrage: "ARB", named_systems: "SYSTEM", memecoin: "MEME", equity_events: "EARN", equity_breadth: "BREADTH"};
const NET = {nodes: [], clusters: {}, pulses: [], stars: [], rot: 0, hover: null, byId: {}, flash: {}};
function hash(s) { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return (h >>> 0) / 4294967296; }
function layout() {
  if (NET.nodes.length === BOTS.length && BOTS.length) return;
  NET.nodes = []; NET.byId = {}; NET.clusters = {};
  const insts = [...new Set(BOTS.map(b => b.instrument))], g = Math.PI * (3 - Math.sqrt(5));
  insts.forEach((s, i) => { const y = insts.length > 1 ? 1 - (i / (insts.length - 1)) * 2 : 0, r = Math.sqrt(1 - y * y), th = g * i + hash(s) * .6; NET.clusters[s] = {x: Math.cos(th) * r * .95, y: y * .55, z: Math.sin(th) * r * .95, name: s, n: 0}; });
  BOTS.forEach(b => {
    const c = NET.clusters[b.instrument]; c.n++;
    const a = hash(b.bot_id) * 6.283, e = hash(b.bot_id + "e") * 3.14 - 1.57, d = .1 + hash(b.bot_id + "d") * .22;
    const node = {id: b.bot_id, cx: c.x, cy: c.y, cz: c.z, ox: Math.cos(a) * Math.cos(e) * d, oy: Math.sin(e) * d * .8, oz: Math.sin(a) * Math.cos(e) * d, ph: hash(b.bot_id + "p") * 6.28, b};
    NET.nodes.push(node); NET.byId[b.bot_id] = node;
  });
  if (!NET.stars.length) for (let i = 0; i < 220; i++) NET.stars.push({x: Math.random() * 2 - 1, y: Math.random() * 1.4 - .7, z: Math.random() * 2 - 1, s: Math.random()});
}
function stance(b) { const p = b.position || ""; if (p.startsWith("long")) return 1; if (p.startsWith("short")) return -1; return (BRAIN.stances || {})[b.bot_id] || 0; }
function drawNet(ts) {
  requestAnimationFrame(drawNet);
  if (PAGE !== "command" || document.hidden) return;
  const c = $("net"), [x, w, h] = fit(c); x.clearRect(0, 0, w, h); if (!RM) NET.rot += .0012;
  const cx = w / 2, cy = h / 2 + 10, R = Math.min(w * .42, h * .95), F = 2.6, tilt = .22 + .05 * Math.sin(ts / 9000), ca = Math.cos(NET.rot), sa = Math.sin(NET.rot), ct = Math.cos(tilt), st = Math.sin(tilt);
  const P = (X0, Y0, Z0) => { let X = X0 * ca - Z0 * sa, Z = X0 * sa + Z0 * ca, Y = Y0 * ct - Z * st; Z = Y0 * st + Z * ct; const k = F / (F + Z); return {x: cx + X * R * k, y: cy + Y * R * k, k, z: Z}; };
  NET.stars.forEach(s => { const p = P(s.x * 1.6, s.y * 1.3, s.z * 1.6); x.globalAlpha = Math.max(0, .12 + .25 * s.s * (p.k - .4)); x.fillStyle = s.s > .85 ? "#ff6ec4" : "#8d7a8a"; x.fillRect(p.x, p.y, 1.2, 1.2); }); x.globalAlpha = 1;
  if (!NET.nodes.length) { x.fillStyle = "#5e4d5c"; x.font = "11px monospace"; x.textAlign = "center"; x.fillText("waiting for the bots", cx, cy); x.textAlign = "start"; return; }
  const wob = RM ? 0 : ts / 1600; NET.nodes.forEach(n => { const j = .012 * Math.sin(wob + n.ph); n.p = P(n.cx + n.ox + j, n.cy + n.oy + .6 * j, n.cz + n.oz - j); });
  const CL = Object.values(NET.clusters); CL.forEach(cl => cl.p = P(cl.x, cl.y, cl.z)); const core = P(0, 0, 0);
  NET.nodes.forEach(n => { const cl = NET.clusters[n.b.instrument]; if (!cl) return; const a = Math.max(.02, .12 * (n.p.k - .5)); x.strokeStyle = `rgba(255,110,196,${a})`; x.lineWidth = .5; x.beginPath(); x.moveTo(n.p.x, n.p.y); x.lineTo(cl.p.x, cl.p.y); x.stroke(); });
  CL.forEach(cl => { x.strokeStyle = `rgba(255,45,149,${Math.max(.03, .1 * (cl.p.k - .5))})`; x.lineWidth = .6; x.beginPath(); x.moveTo(cl.p.x, cl.p.y); x.lineTo(core.x, core.y); x.stroke(); });
  const pu = 1 + .1 * Math.sin(ts / 500), gr = x.createRadialGradient(core.x, core.y, 1, core.x, core.y, 34 * pu);
  gr.addColorStop(0, "rgba(255,227,243,.95)"); gr.addColorStop(.3, "rgba(255,45,149,.55)"); gr.addColorStop(1, "rgba(255,45,149,0)");
  x.fillStyle = gr; x.beginPath(); x.arc(core.x, core.y, 34 * pu, 0, 7); x.fill(); x.fillStyle = "#16020d"; x.font = "bold 9px monospace"; x.textAlign = "center"; x.fillText("BRAIN", core.x, core.y + 3); x.textAlign = "start";
  NET.pulses = NET.pulses.filter(p => p.t < 1);
  NET.pulses.forEach(p => { p.t += RM ? 1 : .016; const n = NET.byId[p.id]; if (!n || !n.p) return; const a = p.dir > 0 ? n.p : core, b = p.dir > 0 ? core : n.p;
    for (let k = 0; k < 5; k++) { const tt = Math.max(0, p.t - k * .02), X = a.x + (b.x - a.x) * tt, Y = a.y + (b.y - a.y) * tt; x.globalAlpha = (1 - k / 5) * .9; x.fillStyle = p.c; x.beginPath(); x.arc(X, Y, Math.max(.5, 2.4 - k * .35), 0, 7); x.fill(); } x.globalAlpha = 1; });
  const now = Date.now(), items = [...NET.nodes.map(n => ({z: n.p.z, n})), ...CL.map(cl => ({z: cl.p.z, cl}))].sort((a, b) => b.z - a.z);
  items.forEach(it => {
    if (it.cl) { const p = it.cl.p, r = 2.2 + 3.2 * p.k * p.k; x.globalAlpha = Math.max(.1, Math.min(1, .4 + .8 * (p.k - .5))); x.fillStyle = "#f4ecf3"; x.shadowColor = "#fff"; x.shadowBlur = 10; x.beginPath(); x.arc(p.x, p.y, r, 0, 7); x.fill(); x.shadowBlur = 0;
      x.fillStyle = "#cdbfcb"; x.font = "9px monospace"; x.fillText(it.cl.name, p.x + r + 3, p.y + 3); x.globalAlpha = 1; return; }
    const n = it.n, b = n.b, s = stance(b), pos = !!b.position, p = n.p, k2 = p.k * p.k; x.globalAlpha = Math.max(.08, Math.min(1, .3 + .9 * (p.k - .5)));
    let col = s > 0 ? "#2ee6a6" : s < 0 ? "#ff3d63" : "#9a8797", r = s ? 1.8 + 2.6 * k2 : 1.5 + 1.8 * k2;
    if (pos) { const glow = s > 0 ? "#2ee6a6" : "#ff3d63"; r = 3 + 5 * k2; const g2 = x.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 2.4); g2.addColorStop(0, "#ffd9a0"); g2.addColorStop(.35, "#e0a45a"); g2.addColorStop(1, "rgba(224,164,90,0)");
      x.fillStyle = g2; x.beginPath(); x.arc(p.x, p.y, r * 2.4, 0, 7); x.fill(); x.strokeStyle = glow; x.lineWidth = 1.2; x.beginPath(); x.arc(p.x, p.y, r * 1.1, 0, 7); x.stroke(); col = "#e0a45a"; }
    x.fillStyle = col; if (s) { x.shadowColor = col; x.shadowBlur = 8; }
    if (s < 0 && !pos) x.fillRect(p.x - r, p.y - r, 2 * r, 2 * r); else { x.beginPath(); x.arc(p.x, p.y, r, 0, 7); x.fill(); } x.shadowBlur = 0;
    const fl = NET.flash[b.bot_id]; let label = null, lc = "#cdbfcb";
    if (fl && now - fl.t < 25000) { label = fl.text; lc = fl.c; } else if (pos) { label = (s > 0 ? "LONG " : "SHORT ") + (FAM[b.family] || ""); lc = s > 0 ? "#2ee6a6" : "#ff3d63"; } else if (s && p.k > .95) { label = FAM[b.family] || ""; lc = s > 0 ? "#2ee6a6" : "#ff3d63"; }
    if (label) { x.font = "9px monospace"; x.fillStyle = lc; x.globalAlpha *= .9; x.fillText(label, p.x + r + 3, p.y + 3); } x.globalAlpha = 1;
  });
  if (NET.hover && NET.hover.p) { const p = NET.hover.p; x.strokeStyle = "#fff"; x.lineWidth = 1; x.beginPath(); x.arc(p.x, p.y, 9, 0, 7); x.stroke(); }
}
$("net").addEventListener("mousemove", e => {
  const r = e.target.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top; let best = null, bd = 144;
  NET.nodes.forEach(n => { if (!n.p) return; const d = (n.p.x - mx) ** 2 + (n.p.y - my) ** 2; if (d < bd) { bd = d; best = n; } }); NET.hover = best;
  const tp = $("tip");
  if (best) { const b = best.b, s = stance(b); tp.style.display = "block"; tp.style.left = (e.clientX + 14) + "px"; tp.style.top = (e.clientY + 10) + "px";
    tp.innerHTML = `<b>${esc(b.bot_id)}</b> · ${esc(b.strategy_id)} <span class="muted">${esc(FAMNAME(b.family))}</span><br>${esc(b.venue)} ${esc(b.instrument)} ${esc(b.tf)} · <span class="${s > 0 ? "up" : s < 0 ? "dn" : "muted"}">${s > 0 ? "bull" : s < 0 ? "bear" : "waiting"}</span><br><span class="s-${esc(b.state)}">${esc(b.state)}</span> ${esc(b.position || "")}<br><span class="muted">${esc(b.last_decision || "")}</span>`;
  } else tp.style.display = "none";
});
$("net").addEventListener("mouseleave", () => { $("tip").style.display = "none"; NET.hover = null; });
$("net").addEventListener("click", () => { if (NET.hover) openBot(NET.hover.id); });
function spawnPulses() {
  const rec = BRAIN.recent || [];
  rec.forEach(r => {
    if (r.time <= seenRecent || !r.bot_id) return;
    if (r.kind === "decision") { NET.pulses.push({id: r.bot_id, t: 0, dir: 1, c: r.action === "veto" ? "#ff3d63" : "#ffe3f3"}); NET.flash[r.bot_id] = {t: Date.now(), text: r.action === "veto" ? (r.benched ? "BENCHED" : "REJECT") : (r.side > 0 ? "BUY" : "SELL"), c: r.action === "veto" ? "#ff3d63" : "#ffe3f3"}; }
    else if (r.kind === "lesson" || r.kind === "shadow") { NET.pulses.push({id: r.bot_id, t: 0, dir: -1, c: r.r > 0 ? "#2ee6a6" : "#ff3d63"}); NET.flash[r.bot_id] = {t: Date.now(), text: (r.kind === "shadow" ? "SHADOW " : "") + (r.r > 0 ? "WIN" : "LOSS"), c: r.r > 0 ? "#2ee6a6" : "#ff3d63"}; }
  });
  if (rec.length) seenRecent = Math.max(seenRecent, ...rec.map(r => r.time));
  if (!RM && NET.nodes.length) { const act = NET.nodes.filter(n => stance(n.b)); for (let k = 0; k < Math.min(3, act.length); k++) { const n = act[(Math.random() * act.length) | 0]; NET.pulses.push({id: n.id, t: 0, dir: 1, c: "#ff6ec4"}); } }
}

/* ---------------------------------------------------------------- shared chrome */
function renderChrome() {
  const armed = !!(ST.live_armed || (LIVE && LIVE.armed));
  const tk = TICK.find(k => /BTC|XBT/.test(k.symbol)) || TICK[0], te = TICK.find(k => /ETH/.test(k.symbol)) || TICK[1];
  if (tk) { $("h1l").textContent = tk.symbol.replace(/-USDT?$/, ""); $("h1").textContent = money(tk.last, 2); }
  if (te) { $("h2l").textContent = te.symbol.replace(/-USDT?$/, ""); $("h2").textContent = money(te.last, 2); }
  const n = TR.length, w = TR.filter(x => x.pnl > 0).length; $("hT").textContent = `${w}/${n}`; $("hW").textContent = n ? (100 * w / n).toFixed(1) + "%" : "–";
  const enabled = S.enabled ?? BOTS.length;
  $("hSub").textContent = `${fmt(enabled, 0)} agents · brain ${String(BRAIN.mode || "–").split(" ")[0]} · ${ST.running ? "autopilot" : "stopped"}`;
  $("navBots").textContent = fmt(enabled, 0);
  const chip = $("modeChip"); chip.className = "mode " + (armed ? "live" : "paper"); chip.textContent = armed ? "REAL MONEY ARMED" : "PAPER MONEY";
  const nl = $("navLive"); nl.textContent = armed ? "ARMED" : "OFF"; nl.className = armed ? "armed" : "";
  const running = !!ST.running, ap = (ST.autopilot || {}).enabled;
  $("fDot").className = "dot " + (DOWN ? "off" : running ? "on" : ap ? "warn" : "off");
  $("fText").textContent = DOWN ? "Jarvus is not responding" : running ? `bots running · autopilot ${ap ? "on" : "off"}` : ap ? "bots starting…" : "bots stopped (Settings → Start)";
  let b = "";
  if (armed) b += `<div class="banner live">REAL MONEY ARMED${LIVE && LIVE.config ? ` on ${esc(LIVE.config.broker)} · max ${fmt(LIVE.config.max_per_trade, 0)} per trade, ${fmt(LIVE.config.max_total, 0)} total` : ""} · <a href="#live" style="color:#fff">manage</a></div>`;
  if (S.emergency || ST.emergency) { const e = S.emergency || ST.emergency; b += `<div class="banner" style="margin-top:6px">Emergency stop active: ${esc(e.reason)} (${t(e.time)}). New trades are blocked until cleared in Settings.</div>`; }
  else if (S.paused || ST.paused) b += `<div class="banner warn" style="margin-top:6px">Paused: no new entries. Open positions keep their stops and exits.</div>`;
  if (!running && !DOWN && ap === false) b += `<div class="banner warn" style="margin-top:6px">The bots are stopped. Start them in <a href="#settings" style="color:#ffe7c4">Settings</a>.</div>`;
  $("banner").innerHTML = b;
  renderTape();
}
function renderTape() {
  const a = S.account || ST.account || {}, b = BRAIN || {}, n = TR.length, pnl = TR.reduce((s, x) => s + (x.pnl || 0), 0), w = TR.filter(x => x.pnl > 0).length, sig = Object.values(b.stances || {}).filter(v => v).length;
  const it = [["LIVE TAPE", `<span class="${pnl >= 0 ? "up" : "dn"}">${sgn(pnl)}</span>`], ["WIN RATE", n ? (100 * w / n).toFixed(1) + "%" : "–"], ["EQUITY", money(a.equity)], ["OPEN", fmt(a.open_positions, 0)],
    ["EXPOSURE", a.gross_exposure_pct != null ? fmt(a.gross_exposure_pct, 1) + "%" : "–"], ["SIGNALS", fmt(sig, 0)], ["SCORED", fmt(b.scored, 0)], ["VETOED", fmt(b.vetoed, 0)], ["BENCHED", fmt(b.benched_now, 0)],
    ["SHADOW R", b.shadow_avg_r != null ? `<span class="${b.shadow_avg_r < 0 ? "up" : "dn"}">${fmt(b.shadow_avg_r, 2)}</span>` : "–"], ["LEARNED", fmt(b.trades_learned, 0)], ["BRIER", b.brier != null ? fmt(b.brier, 3) : "–"],
    ["LATENCY", S.latency_ms_p95 != null ? fmt(S.latency_ms_p95 / 1000, 1) + "s" : "–"], ["MONEY", ST.live_armed ? '<span class="dn">REAL ARMED</span>' : '<span class="up">PAPER</span>']];
  const h = it.map(([k, v]) => `<span class="i"><em>${k}</em>${v}</span>`).join(""); $("tape").innerHTML = h + h;
}

/* ---------------------------------------------------------------- command */
function renderWallet() {
  const a = S.account || ST.account || {}, n = TR.length, w = TR.filter(x => x.pnl > 0).length;
  $("eqBig").textContent = money(a.equity);
  $("wMode").textContent = `paper account · ${a.currency || "USD"} · fees: ${FEENAME[ST.fee_profile || "venue"] || ST.fee_profile} · ${ST.live_armed ? "real money armed separately" : "no real money"}`;
  $("eqSub").innerHTML = a.twr != null ? `<span class="${a.twr >= 0 ? "up" : "dn"}">${a.twr >= 0 ? "▲" : "▼"} ${fmt(100 * a.twr, 3)}%</span> <span class="dim">· ${n} trades · time-weighted</span>` : "";
  $("w1").textContent = fmt(n, 0); $("w2").textContent = n ? (100 * w / n).toFixed(1) + "%" : "–"; $("w3").textContent = n ? fmt(TR.reduce((s, x) => s + (x.r || 0), 0) / n, 2) : "–";
  $("acct").innerHTML = kv([["free cash", money(a.cash)], ["open positions", fmt(a.open_positions, 0)], ["exposure", money(a.gross_exposure)], ["realized", sgn(a.realized_pnl)], ["fees paid", money(a.fees)]]);
  const halt = S.emergency || ST.emergency, paused = S.paused || ST.paused;
  $("liveTag").textContent = halt ? "HALT" : paused ? "PAUSED" : ST.running ? "LIVE" : "STOPPED";
  $("wState").textContent = halt ? "HALTED" : paused ? "PAUSED" : ST.running ? "ACTIVE" : "STOPPED";
}
function renderPick() {
  $("chartPick").innerHTML = TICK.slice(0, 6).map(k => `<button class="sm" data-key="${esc(k.key)}" style="${k.key === CHART.key ? "border-color:var(--hot);color:var(--hot)" : ""}">${esc(k.symbol.replace(/-USDT?$/, ""))}</button>`).join("");
  for (const el of $("chartPick").children) el.onclick = () => { CHART.key = el.dataset.key; BOOK = null; loadChart(); };
}
async function loadChart() {
  if (PAGE !== "command") return;
  if (!CHART.key && TICK.length) CHART.key = TICK[0].key;
  if (!CHART.key) { candles($("chart"), {}); renderBook(); renderPick(); return; }
  try {
    const [d, bk] = await Promise.all([getF("chart?key=" + encodeURIComponent(CHART.key)), getF("book?key=" + encodeURIComponent(CHART.key.split("/").slice(0, 2).join("/")))]);
    CHART.data = d; BOOK = bk;
    const k = CHART.key.split("/"), n = (d.c || []).length; $("chartTitle").textContent = `${k[1]} · ${(k[2] || "").toUpperCase()}`;
    if (n) { const l = d.c[n - 1], f = d.c[Math.max(0, n - 90)], ch = l / f - 1; $("chartPx").textContent = money(l, l >= 100 ? 2 : 4); $("chartChg").innerHTML = `<span class="${ch >= 0 ? "up" : "dn"}">${ch >= 0 ? "+" : ""}${(100 * ch).toFixed(2)}%</span>`; }
    candles($("chart"), d);
  } catch (e) { candles($("chart"), {}); }
  renderBook(); renderPick();
}
function renderBook() {
  const b = BOOK || {}, el = $("book");
  if (!b.asks || !b.asks.length || !b.bids || !b.bids.length) { el.innerHTML = `<div class="muted small" style="padding:8px 4px">${esc(b.note || (ST.running ? "loading order book…" : "the bots are stopped"))}</div>`; return; }
  const asks = b.asks.slice(0, 7).reverse(), bids = b.bids.slice(0, 7), mx = Math.max(...asks.map(a => a[1]), ...bids.map(a => a[1])) || 1, mid = (b.asks[0][0] + b.bids[0][0]) / 2;
  const row = (r, c) => `<div class="rw"><i style="width:${Math.max(4, 100 * r[1] / mx)}%;background:${c}"></i><span>${money(r[0], r[0] >= 100 ? 2 : 4)}</span><span class="muted">${fmt(r[1], r[1] < 10 ? 3 : 0)}</span></div>`;
  el.innerHTML = asks.map(r => row(r, "#ff3d63")).join("") + `<div class="mid">${money(mid, mid >= 100 ? 2 : 4)} <span class="tiny dim">spread ${fmt(10000 * (b.asks[0][0] - b.bids[0][0]) / mid, 1)} bps</span></div>` + bids.map(r => row(r, "#2ee6a6")).join("");
}
function renderTrader() {
  const p = BRAIN.top_picks || [];
  $("picks").innerHTML = p.map(x => `<div><span class="hotc">${esc(x.bot_id)}</span> ${sid(x.strategy_id)} <span class="dim">${esc(x.instrument)}</span></div><div class="${x.edge_r >= 0 ? "up" : "dn"}">${rr(x.edge_r)}</div>`).join("") || '<div class="muted">appears when the brain is running</div><div></div>';
  const by = {}; TR.slice().reverse().forEach(x => { (by[x.bot_id] = by[x.bot_id] || []).push(x); }); let best = null;
  Object.entries(by).forEach(([id, l]) => { const pnl = l.reduce((a, x) => a + x.pnl, 0); let st = 0; for (let i = l.length - 1; i >= 0 && l[i].pnl > 0; i--) st++; if (!best || pnl > best.pnl) best = {id, pnl, st, l}; });
  if (!best) { $("stN").textContent = "0"; $("stR").textContent = ""; minibars($("stSpark"), [], "#ff2d95", ""); for (const k of ["stA", "stB", "stBot", "stW", "stM"]) $(k).textContent = "–";
    $("stSub").textContent = "No closed trades yet. The #1 bot appears after the first closed trades; the brain's current ranking (expected R per trade after costs) is below."; return; }
  const R = best.l.reduce((a, x) => a + (x.r || 0), 0); $("stN").textContent = best.st; $("stR").textContent = rr(R, 1); $("stR").className = R >= 0 ? "up" : "dn";
  let acc = 0; const cum = best.l.map(x => acc += x.pnl); minibars($("stSpark"), cum.map(v => Math.max(0, v)), "#ff2d95", "");
  $("stA").textContent = sgn(best.l[0].pnl); $("stB").textContent = sgn(best.pnl); $("stB").className = best.pnl >= 0 ? "up" : "dn";
  $("stBot").textContent = best.id; $("stW").textContent = (100 * best.l.filter(x => x.pnl > 0).length / best.l.length).toFixed(0) + "%"; $("stM").textContent = best.l[0].instrument;
  const b = BOTS.find(x => x.bot_id === best.id); $("stSub").textContent = b ? `${b.strategy_id} · ${FAMNAME(b.family)} · ${best.l.length} trades` : "";
}
function renderPnl() {
  const tr = TR.slice().reverse(); let acc = 0; const cum = [0, ...tr.map(x => acc += x.pnl || 0)], n = TR.length, w = TR.filter(x => x.pnl > 0).length;
  $("pnlT").innerHTML = `<span class="${acc >= 0 ? "up" : "dn"}">${sgn(acc)}</span>`; $("pnlR").textContent = `T ${n} · W ${n ? (100 * w / n).toFixed(1) : "–"}%`;
  curve($("pnl"), cum, acc >= 0 ? "#2ee6a6" : "#ff3d63", "the P&L curve starts with the first closed trade");
}
function lessonP(x) { const l = (BRAIN.recent || []).filter(r => r.kind === "lesson" && r.bot_id === x.bot_id && r.p_win != null); let best = null, bd = 9e9; l.forEach(r => { const d = Math.abs(r.time - x.exit_time); if (d < bd) { bd = d; best = r; } }); return best && bd < 120000 ? best.p_win : null; }
function renderRecent() {
  const w = TR.filter(x => x.pnl > 0).length; $("recR").textContent = `${w}/${TR.length}`;
  $("trades").innerHTML = TR.slice(0, 60).map(x => { const p = lessonP(x), why = (x.exit_reason || "").split(/[ :(]/)[0].toUpperCase().slice(0, 6), live = /^\[LIVE\]/.test(x.entry_reason || "");
    return `<tr data-id="${esc(x.bot_id)}"><td class="dim">#${x.id}</td><td><span class="pill ${x.side > 0 ? "pu" : "pd"}">${x.side > 0 ? "UP" : "DN"}</span>${live ? ' <span class="pill pd">LIVE</span>' : ""}</td><td>${money(x.exit_price, x.exit_price >= 100 ? 0 : 4)}</td><td class="muted">${p != null ? (100 * p).toFixed(1) + "%" : fmt(x.r, 2) + "R"}</td><td class="${x.pnl >= 0 ? "up" : "dn"}">${sgn(x.pnl)}</td><td class="dim">${esc(why)}</td><td class="dim">${esc(x.bot_id)}</td></tr>`; }).join("")
    || '<tr><td class="w muted">No closed trades yet: the bots trade by themselves when their rules fire and the brain agrees. At retail fees the brain refuses most signals (see Brain).</td></tr>';
  for (const tr of $("trades").children) if (tr.dataset.id) tr.onclick = () => openBot(tr.dataset.id);
}
function renderAnalytics() {
  const now = Date.now(), hours = new Array(24).fill(0); TR.forEach(x => { const k = 23 - Math.floor((now - x.exit_time) / 3600000); if (k >= 0 && k < 24) hours[k]++; });
  minibars($("a1"), hours, "#ff6ec4", "no trades in 24 h"); $("a1v").textContent = fmt(TR.length, 0);
  const last = TR.slice(0, 40).reverse(), vol = last.map(x => Math.abs((x.qty || 0) * (x.exit_price || 0))); minibars($("a2"), vol, "#ff4fd8", "no volume yet"); $("a2v").textContent = big(TR.reduce((s, x) => s + Math.abs((x.qty || 0) * (x.exit_price || 0)), 0));
  minibars($("a3"), last.map(x => x.pnl > 0 ? x.pnl : 0), "#2ee6a6", "no wins yet"); minibars($("a4"), last.map(x => x.pnl < 0 ? -x.pnl : 0), "#ff3d63", "no losses yet");
  $("a3v").textContent = sgn0(TR.filter(x => x.pnl > 0).reduce((s, x) => s + x.pnl, 0)); $("a4v").textContent = sgn0(TR.filter(x => x.pnl < 0).reduce((s, x) => s + x.pnl, 0));
}
function renderLog() {
  const L = [], tag = (g, c) => `<span class="g" style="color:${c}">${g}</span>`;
  (BRAIN.recent || []).forEach(r => {
    if (r.kind === "decision") { const g = r.action === "veto" ? (r.benched ? "BENCH" : "VETO") : r.action === "resize" ? "SIZE" : "IN", c = r.action === "veto" ? "var(--bad)" : "var(--hot2)";
      L.push({time: r.time, h: tag(g, c) + `${esc(r.bot_id)} ${r.side > 0 ? "UP" : "DN"} · ${esc(r.instrument)} · win ${(100 * r.p_win).toFixed(0)}% · edge ${rr(r.edge)} · size ${fmt(r.size, 2)}x${r.veto_kind ? " · " + esc(r.veto_kind) : ""} · ${esc((r.regime || "").replace("-", " / "))}`}); }
    else if (r.kind === "lesson") L.push({time: r.time, h: tag(r.r > 0 ? "WIN" : "LOSS", r.r > 0 ? "var(--good)" : "var(--bad)") + `${esc(r.bot_id)} · ${esc(r.instrument)} · ${rr(r.r)} · brain learned (${sid(r.strategy_id)})`});
    else if (r.kind === "shadow") L.push({time: r.time, h: tag("SHADOW", r.r > 0 ? "var(--warn)" : "var(--mute)") + `${esc(r.bot_id)} · refused trade would have made ${rr(r.r)} (${esc(r.exit)}) · learned at half weight`});
    else if (r.kind === "insight") L.push({time: r.time, h: tag("LEARN", "var(--gold)") + esc(r.text)});
  });
  TR.slice(0, 40).forEach(x => L.push({time: x.exit_time, h: tag("CLOSE", x.pnl >= 0 ? "var(--good)" : "var(--bad)") + `#${x.id} ${esc(x.bot_id)} ${x.side > 0 ? "UP" : "DN"} · ${esc(x.instrument)} · ${sgn(x.pnl)} · ${fmt(x.r, 2)}R · ${esc(x.exit_reason)}`}));
  (EV || []).slice(0, 40).filter(e => e.kind !== "brain_insight").forEach(e => { const bad = e.level === "critical" || e.level === "error"; L.push({time: e.time, h: tag(bad ? "ALERT" : e.level === "warning" ? "WARN" : "INFO", bad ? "var(--bad)" : e.level === "warning" ? "var(--warn)" : "var(--dim)") + esc(e.message)}); });
  L.sort((a, b) => b.time - a.time);
  $("log").innerHTML = L.slice(0, 160).map(l => `<div><span class="t">${hm(l.time)}</span>${l.h}</div>`).join("") || '<span class="muted">waiting for activity</span>';
  $("logR").textContent = `evals ${fmt(S.completed_evaluations, 0)} · latency ${S.latency_ms_p95 != null ? fmt(S.latency_ms_p95 / 1000, 1) : "–"}s · refresh 5s`;
}
function renderSwarmOverlay() {
  const b = BRAIN || {}, pnl = TR.reduce((s, x) => s + (x.pnl || 0), 0), n = TR.length, avgR = n ? TR.reduce((s, x) => s + (x.r || 0), 0) / n : null, sig = Object.values(b.stances || {}).filter(v => v).length;
  $("ovCount").textContent = fmt(NET.nodes.length, 0);
  $("ovStats").innerHTML = `<b class="${pnl >= 0 ? "up" : "dn"}">${sgn(pnl)}</b><b class="muted">${avgR != null ? rr(avgR) : "±0.00R"}</b><b class="hotc">#${sig}</b>`;
  $("ovSide").innerHTML = `approved<b>${b.scored ? (100 * b.approved / b.scored).toFixed(1) + "%" : "–"}</b><br>scored<b>${fmt(b.scored, 0)}</b><br>learned<b>${fmt(b.trades_learned, 0)}</b><br>vetoed<b>${fmt(b.vetoed, 0)}</b><br>shadows<b>${fmt(b.shadow_trades, 0)}</b><br>benched<b>${fmt(b.benched_now, 0)}</b>`;
}
function renderCommand() { renderWallet(); renderTrader(); renderPnl(); renderRecent(); renderAnalytics(); renderLog(); renderSwarmOverlay(); }

/* money and safety buttons (Command and Settings) */
function amountFrom(id) { const v = parseFloat($(id).value); if (!(v > 0)) { toast("Type an amount first, for example 25000", "err"); return null; } return v; }
for (const b of document.querySelectorAll("[data-money]")) b.onclick = () => { const v = amountFrom("amt"); if (v) command(b.dataset.money, {amount: v}); };
for (const b of document.querySelectorAll("[data-money2]")) b.onclick = () => { const v = amountFrom("amt2"); if (v) command(b.dataset.money2, {amount: v}); };
for (const b of document.querySelectorAll("[data-cmd]")) b.onclick = () => {
  const c = b.dataset.cmd;
  if (c === "emergency_stop" && !confirm("Emergency stop: close every paper position now, block new trades and disarm real money until cleared?")) return;
  command(c, c === "emergency_stop" ? {reason: "owner"} : {});
};
$("bStart").onclick = async () => { const j = await post("/api/fleet/start", {}); toast(j.error || (j.already_running ? "The bots are already running." : "Starting the bots…"), j.error ? "err" : "ok"); setTimeout(refresh, 1500); };
$("bStopFleet").onclick = async () => { if (!confirm("Stop all bots? Autopilot stays off until you press Start. Open paper positions are kept.")) return; const j = await post("/api/fleet/stop", {}); toast(j.error || "Bots stopped.", j.error ? "err" : "ok"); refresh(); };

/* ---------------------------------------------------------------- bots */
const STATES = ["running", "warming", "idle_no_signal", "data_unavailable", "degraded", "stopped", "disabled", "paused"];
function renderTiles() {
  const c = {}; BOTS.forEach(b => c[b.state] = (c[b.state] || 0) + 1);
  let h = `<div class="tile ${!stateFilter ? "sel" : ""}" data-s=""><b>${fmt(BOTS.length, 0)}</b><span>all bots</span></div>`;
  for (const k of STATES) if (c[k] || ["running", "idle_no_signal", "warming"].includes(k)) h += `<div class="tile ${stateFilter === k ? "sel" : ""}" data-s="${k}"><b class="s-${k}">${fmt(c[k] || 0, 0)}</b><span>${k.replace(/_/g, " ")}</span></div>`;
  $("tiles").innerHTML = h; for (const el of $("tiles").children) el.onclick = () => { stateFilter = el.dataset.s || null; renderTiles(); renderBots(); };
}
function renderBots() {
  const q = $("q").value.toLowerCase(), rows = BOTS.filter(b => (!stateFilter || b.state === stateFilter) && (!q || JSON.stringify(b).toLowerCase().includes(q)));
  $("count").textContent = `${rows.length} of ${BOTS.length}`;
  $("bots").innerHTML = rows.map(b => `<tr data-id="${esc(b.bot_id)}"><td>${esc(b.bot_id)}</td><td>${esc(b.strategy_id || "")} <span class="muted">${esc(FAMNAME(b.family))}</span></td><td>${esc(b.venue || "")} ${esc(b.instrument || "")} ${esc(b.tf || "")}</td><td><span class="s-${esc(b.state)}">${esc((b.state || "").replace(/_/g, " "))}</span></td><td>${esc(b.position || "")}</td><td class="w">${esc(b.last_decision || b.message || "")}</td></tr>`).join("")
    || '<tr><td colspan="6" class="empty">no bots match</td></tr>';
  for (const tr of $("bots").children) if (tr.dataset.id) tr.onclick = () => openBot(tr.dataset.id);
}
$("q").oninput = renderBots;
async function openBot(id) {
  const d = await getF("bot/" + encodeURIComponent(id)), s = d.last_signal || (d.recent_signals || [])[0] || {};
  const info = BOTS.find(b => b.bot_id === id) || {};
  const rules = (s.rules || []).map(r => `<tr><td class="${r.passed === true ? "pass" : r.passed === false ? "fail" : "unk"}">${r.passed === true ? "pass" : r.passed === false ? "fail" : "unknown"}</td><td class="w">${esc(r.rule)}</td><td class="w">${esc(r.detail)}</td><td>${esc(r.group || "")}</td></tr>`).join("");
  const feats = Object.entries(s.features || {}).map(([k, v]) => `<tr><td class="w">${esc(k)}</td><td>${esc(fmt(v, 6))}</td></tr>`).join("");
  const tr = (d.trades_list || []).map(x => `<tr><td>${t(x.exit_time)}</td><td>${x.side > 0 ? "long" : "short"}</td><td>${fmt(x.entry_price, 6)}</td><td>${fmt(x.exit_price, 6)}</td><td class="${x.pnl >= 0 ? "up" : "dn"}">${fmt(x.pnl)}</td><td>${fmt(x.r)}</td><td class="w">${esc(x.exit_reason)}</td></tr>`).join("");
  const risk = (d.risk || []).map(r => `<tr><td>${t(r.time)}</td><td>${r.approved ? "approved" : "blocked"}</td><td class="w">${(r.checks || []).filter(c => !c.passed).map(c => esc(c.check + (c.detail ? ": " + c.detail : ""))).join("; ") || "all checks passed"}</td></tr>`).join("");
  const sig = (d.recent_signals || []).map(x => `<tr><td>${t(x.bar_time)}</td><td>${esc(x.action)}</td><td class="w">${esc(x.reason)}</td></tr>`).join("");
  const enabled = d.enabled !== false;
  $("drawer").innerHTML = `<div class="between"><h1>${esc(id)}</h1><div class="flex"><button class="sm" id="dToggle">${enabled ? "Disable" : "Enable"}</button><button class="sm" id="dClose">Close</button></div></div>
   <p>${esc(d.strategy_name || info.name || "")} <span class="pill ph">${esc(d.strategy_id || info.strategy_id || "")}</span> on ${esc(d.venue || info.venue || "")} ${esc(d.instrument || info.instrument || "")} ${esc(d.timeframe || info.tf || "")}</p>
   <div class="flex"><span class="s-${esc(d.state || info.state)}">${esc(d.state || info.state || "")}</span><span class="muted">${esc(d.message || info.message || "")}</span></div>
   <h2>Latest decision</h2><p><b>${esc(s.action || "none yet")}</b> ${esc(s.reason || "")} <span class="muted">${t(s.bar_time)}</span></p>
   <table><thead><tr><th>outcome</th><th>rule</th><th>values</th><th>part</th></tr></thead><tbody>${rules || '<tr><td colspan=4 class="muted">rule detail is recorded for entries, exits and skipped signals</td></tr>'}</tbody></table>
   <h2>Indicator values</h2><table><tbody>${feats || '<tr><td class="muted">none recorded yet</td></tr>'}</tbody></table>
   <h2>Position</h2><pre>${esc(JSON.stringify(d.position, null, 1) || "flat")}</pre>
   <h2>Rules</h2><pre>${esc(JSON.stringify(d.rules, null, 1) || "open the strategy in Strategies to see its rules")}</pre>
   <h2>Recent decisions</h2><table><tbody>${sig || '<tr><td class="muted">none yet</td></tr>'}</tbody></table>
   <h2>Risk and brain checks</h2><table><tbody>${risk || '<tr><td class="muted">none</td></tr>'}</tbody></table>
   <h2>Trades</h2><table><thead><tr><th>exit</th><th>side</th><th>entry</th><th>exit</th><th>p&amp;l</th><th>R</th><th>why</th></tr></thead><tbody>${tr || '<tr><td colspan=7 class="muted">no trades yet</td></tr>'}</tbody></table>`;
  $("drawer").classList.add("open");
  $("dClose").onclick = () => $("drawer").classList.remove("open");
  $("dToggle").onclick = async () => { await command(enabled ? "disable_bot" : "enable_bot", {bot_id: id}); openBot(id); };
}
document.addEventListener("keydown", e => { if (e.key === "Escape") $("drawer").classList.remove("open"); });

/* ---------------------------------------------------------------- brain */
function renderBrain() {
  const b = BRAIN || {}, sk = b.shadow_by_kind || {}, G = b.gates || {}, M = b.markets || {};
  const sh = k => sk[k] && sk[k].trades ? `${fmt(sk[k].trades, 0)} · <span class="${cls(-(sk[k].avg_r || 0))}">${rr(sk[k].avg_r)}</span>` : "–";
  const loud = Object.values(G).filter(g => g.state === "LOUD").length, quiet = Object.values(G).filter(g => g.state === "QUIET").length;
  $("g1").innerHTML = kv([["crypto fees", `<a href="#settings">${esc(FEENAME[ST.fee_profile || "venue"] || "")}</a>`], ["refuse above", "0.33R"], ["half size above", "0.20R"], ["refused (followed)", sh("cost")]]);
  $("g2").innerHTML = kv([["markets LOUD now", `<span class="hotc">${loud}</span>`], ["markets QUIET now", `<span class="cyanc">${quiet}</span>`], ["refused (followed)", sh("quiet")]]);
  $("g3").innerHTML = kv([["entries scored", fmt(b.scored, 0)], ["approved", b.scored ? `${fmt(b.approved, 0)} (${pct(b.approved / b.scored)})` : "–"], ["refused (followed)", sh("learned")]]);
  $("g4").innerHTML = kv([["benched now", fmt(b.benched_now, 0)], ["resized", fmt(b.resized, 0)], ["refused (followed)", sh("benched")]]);
  const keys = [...new Set([...Object.keys(G), ...Object.keys(M)])].sort();
  $("gateR").textContent = keys.length ? `${keys.length} markets` : "";
  $("gates").innerHTML = keys.map(k => { const g = G[k] || {}, m = M[k] || {}; return `<tr><td>${esc(k)} <span class="dim">${esc(g.venue || "")}</span></td><td><span class="gstate g-${esc(g.state || "UNKNOWN")}">${esc(g.state || "–")}</span></td><td class="r">${g.p_loud != null ? pct(g.p_loud, 0) : "–"}</td><td class="r">${g.p_quiet != null ? pct(g.p_quiet, 0) : "–"}</td><td class="${m.trend === "up" ? "up" : m.trend === "down" ? "dn" : "muted"}">${esc(m.trend || "–")}</td><td class="${m.vol === "volatile" ? "hotc" : "muted"}">${esc(m.vol || "–")}</td></tr>`; }).join("")
    || `<tr><td colspan="6" class="empty">${ST.running ? "Readings appear within a minute or two of the bots starting (each market needs 200 hourly bars)." : "Start the bots to see live gate readings."}</td></tr>`;
  $("shadows").innerHTML = Object.entries(sk).map(([k, v]) => `<tr><td>${esc({cost: "cost too high", quiet: "quiet market", learned: "negative learned edge", benched: "bot benched"}[k] || k)}</td><td class="r">${fmt(v.trades, 0)}</td><td class="r ${cls(-(v.avg_r || 0))}">${rr(v.avg_r)}</td></tr>`).join("")
    || '<tr><td colspan="3" class="empty">No refused trade has reached its exit yet.</td></tr>';
  $("brainMode").textContent = `${String(b.mode || "–").split(" (")[0]} · ${fmt(b.connected_bots, 0)} connected`;
  $("brainKv").innerHTML = kv([["trades learned", fmt(b.trades_learned, 0)], ["learned win rate", b.win_rate != null ? pct(b.win_rate) : "–"], ["avg R learned", fmt(b.avg_r, 3)],
    ["high-score trades", b.high_score_trades ? `${b.high_score_trades} · ${fmt(b.high_score_avg_r, 3)}R` : "–"], ["low-score trades", b.low_score_trades ? `${b.low_score_trades} · ${fmt(b.low_score_avg_r, 3)}R` : "–"],
    ["refused trades (shadow)", b.shadow_trades ? `${b.shadow_trades} · ${fmt(b.shadow_avg_r, 3)}R` : "–"], ["prediction error (Brier)", fmt(b.brier, 3)], ["starting knowledge", `${fmt(b.prior_strategies, 0)} tested strategies`]]);
  const tr = b.trust || {};
  $("trust").innerHTML = kv([["tested history", tr.history != null ? fmt(tr.history, 2) + "x" : "–"], ["context model", tr.context != null ? fmt(tr.context, 2) + "x" : "–"], ["baseline", tr.base != null ? rr(tr.base, 3) : "–"]]);
  const ins = b.insights || [];
  $("insights").innerHTML = ins.length ? ins.map(i => `<div><span class="dim">${hm(i.time)}</span> ${esc(i.text)}</div>`).join("") : '<div class="muted">Insights appear when a pattern is statistically clear (at least 10 trades, |t| ≥ 2). The brain writes them itself.</div>';
  const cal = b.calibration || []; minibars($("calib"), cal.map(c => c.trades ? c.actual * 100 : 0), "#56d8ff", "calibration appears after closed trades");
  $("bestL").innerHTML = (b.best_learned || []).map(x => `<tr><td>${sid(x.strategy_id)} <span class="muted">${esc(x.name)}</span></td><td class="r">${fmt(x.trades, 0)}</td><td class="r ${cls(x.prior_r)}">${rr(x.prior_r)}</td><td class="r ${cls(x.estimate_r)}">${rr(x.estimate_r)}</td></tr>`).join("")
    || '<tr><td colspan="4" class="empty">Appears after the first closed paper trades.</td></tr>';
  $("regL").innerHTML = (b.regime_lessons || []).map(x => `<tr><td>${esc(FAMNAME(x.family))}</td><td class="w">${esc(x.text)}</td><td class="r">${fmt(x.trades, 0)}</td><td class="r ${cls(x.mean_r)}">${rr(x.mean_r)}</td></tr>`).join("")
    || '<tr><td colspan="4" class="empty">Appears after at least 3 trades in a regime.</td></tr>';
}

/* ---------------------------------------------------------------- strategies */
let libUI = false;
async function loadLibrary() {
  if (!LIB) { try { LIB = await get("/api/library"); } catch (e) { $("lib").innerHTML = `<tr><td class="empty">library unavailable: ${esc(e)}</td></tr>`; return; } }
  if (libUI) return renderLibrary();
  libUI = true;
  const fams = [...new Set(LIB.strategies.map(s => s.family))].sort();
  $("lfam").innerHTML = '<option value="">every family</option>' + fams.map(f => `<option value="${esc(f)}">${esc(FAMNAME(f))} (${LIB.strategies.filter(s => s.family === f).length})</option>`).join("");
  $("navStrat").textContent = fmt(LIB.counts.counted_strategies, 0);
  const c = LIB.counts;
  $("libHero").innerHTML = [["Strategies", c.counted_strategies, `${c.variants_not_counted} variants not counted`], ["Bots can run", c.implemented, "exact rules, backtested"], ["Research only", c.blocked, "need data this build lacks, or not testable yet"],
    ["Sources", c.sources, "papers, books, exchange docs"], ["Out-of-sample tested", (c.evaluation_status || {})["out-of-sample tested"], "positive on train and validation"]]
    .map(([k, v, s]) => `<section class="p"><div class="lbl">${k}</div><b class="v glitch">${fmt(v, 0)}</b><div class="tiny muted">${s}</div></section>`).join("");
  renderLibrary();
}
function renderLibrary() {
  if (!LIB) return;
  const q = $("lq").value.toLowerCase(), f = $("lfam").value, st = $("lstat").value, mk = $("lmkt").value, so = $("lsort").value;
  let rows = LIB.strategies.filter(s => (!f || s.family === f) && (!st || s.impl === st) && (!mk || (s.markets || []).includes(mk)) && (!q || `${s.id} ${s.name} ${s.family}`.toLowerCase().includes(q)));
  if (so === "best") rows = rows.slice().sort((a, b) => (b.best_r ?? -1e9) - (a.best_r ?? -1e9));
  if (so === "name") rows = rows.slice().sort((a, b) => a.name.localeCompare(b.name));
  $("libCount").textContent = `${rows.length} of ${LIB.strategies.length}`;
  $("lib").innerHTML = rows.map(s => `<tr data-id="${esc(s.id)}"><td class="dim">${esc(s.id)}</td><td class="w">${esc(s.name)}</td><td>${esc(FAMNAME(s.family))}</td><td>${esc((s.markets || []).join(", "))}</td><td>${esc(s.tf || "")}</td>
    <td><span class="pill ${s.impl === "implemented" ? "pu" : "pn"}">${s.impl === "implemented" ? "BOTS" : "RESEARCH"}</span></td><td class="r ${cls(s.best_r)}">${s.best_r != null ? rr(s.best_r) : "–"}</td><td class="r ${cls(s.gross_r)}">${s.gross_r != null ? rr(s.gross_r) : "–"}</td><td class="r">${s.trades ?? "–"}</td></tr>`).join("")
    || '<tr><td colspan="9" class="empty">no strategy matches</td></tr>';
  for (const tr of $("lib").children) if (tr.dataset.id) tr.onclick = () => openStrategy(tr.dataset.id);
}
for (const id of ["lq", "lfam", "lstat", "lmkt", "lsort"]) $(id).addEventListener(id === "lq" ? "input" : "change", renderLibrary);
async function openStrategy(id) {
  const s = await get("/api/library/" + encodeURIComponent(id));
  if (s.error) return toast(s.error, "err");
  const ev = s.evaluation || {}, best = ev.best_realistic || {};
  const src = (s.sources || []).map(x => `<tr><td class="dim">${esc(x.id)}</td><td class="w">${esc(x.title || x.name || "")} ${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">link</a>` : ""}<div class="muted">${esc(x.relation)}: ${esc(x.note)}</div></td></tr>`).join("");
  const res = (ev.results || []).filter(r => ["retail_kraken", "base"].includes(r.cost_mult)).map(r => `<tr><td>${esc(r.period)}</td><td>${esc(r.instrument)}</td><td class="r">${r.metrics.trades}</td><td class="r ${cls(r.metrics.expectancy_r)}">${rr(r.metrics.expectancy_r)}</td><td class="r">${pct(r.metrics.win_rate, 0)}</td><td class="r">${spct(r.metrics.net_return)}</td></tr>`).join("");
  const pk = (s.pack_refs || []).map(p => `<div><span class="pill pc">${esc(p.pack_id)}</span> ${esc(p.relation)} · ${esc(p.name)} <span class="muted">${esc(p.note || "")}</span></div>`).join("");
  $("drawer").innerHTML = `<div class="between"><h1>${esc(s.name)}</h1><button class="sm" id="dClose">Close</button></div>
    <p><span class="pill ph">${esc(s.id)}</span> ${esc(FAMNAME(s.family))}${s.subfamily ? " · " + esc(s.subfamily) : ""} · ${esc((s.markets || []).join(", "))} · ${esc(s.timeframe || "")}
    · <span class="pill ${s.implementation_status === "implemented" ? "pu" : "pn"}">${esc(s.implementation_status)}</span> <span class="pill pw">${esc(s.research_status)}</span> <span class="pill pn">${esc(s.evaluation_status)}</span></p>
    ${s.hypothesis ? `<h2>The idea</h2><p>${esc(s.hypothesis)}</p>` : ""}${s.mechanism ? `<p class="muted">Mechanism: ${esc(s.mechanism)}</p>` : ""}
    ${s.blocked ? `<div class="note warn">Research only: ${esc(typeof s.blocked === "string" ? s.blocked : JSON.stringify(s.blocked))}</div>` : ""}
    <h2>Measured (best run at realistic costs)</h2>${best.instrument ? `<div class="kv" style="max-width:420px">${kv([["market", esc(best.instrument)], ["trades", best.trades], ["R per trade after costs", `<span class="${cls(best.expectancy_r)}">${rr(best.expectancy_r)}</span>`], ["before costs", `<span class="${cls(best.gross_expectancy_r)}">${rr(best.gross_expectancy_r)}</span>`], ["untouched test segment", `<span class="${cls(best.test_expectancy_r)}">${rr(best.test_expectancy_r)}</span>`]])}</div>` : '<p class="muted">Not tested yet.</p>'}
    ${res ? `<h2>Every split at realistic costs</h2><div class="scroll"><table><thead><tr><th>split</th><th>market</th><th class="r">trades</th><th class="r">R/trade</th><th class="r">win</th><th class="r">return</th></tr></thead><tbody>${res}</tbody></table></div>` : ""}
    ${s.definition ? `<h2>Exact rules</h2><pre>${esc(JSON.stringify(s.definition, null, 1))}</pre>` : ""}
    ${(s.failure_modes || []).length ? `<h2>How it fails</h2><p>${s.failure_modes.map(esc).join("<br>")}</p>` : ""}
    ${pk ? `<h2>Knowledge pack</h2>${pk}` : ""}
    <h2>Sources</h2><table><tbody>${src || '<tr><td class="muted">none recorded</td></tr>'}</tbody></table>
    ${s.notes ? `<h2>Notes</h2><p class="muted">${esc(s.notes)}</p>` : ""}`;
  $("drawer").classList.add("open"); $("dClose").onclick = () => $("drawer").classList.remove("open");
}

/* ---------------------------------------------------------------- results */
async function loadResults() {
  if (!RES) { try { RES = await get("/api/results"); } catch (e) { toast("results unavailable: " + e, "err"); return; } }
  renderResults();
}
const ARMCOL = {none: "#8d7a8a", gates: "#56d8ff", brain: "#ff2d95"}, ARMNAME = {none: "no brain (every signal)", gates: "cost + volatility gates", brain: "full brain"};
function renderResults() {
  if (!RES) return;
  const sy = RES.system, stt = RES.strategies, vg = RES.volgate;
  const hero = [];
  if (sy) hero.push(["Whole-system simulations", fmt(sy.simulations, 0), `${fmt(sy.runs, 0)} runs × 3 arms, ${sy.bots_per_run} bots, ${sy.window_days}-day windows`],
    ["Brain: mean per window", spct(sy.arms.brain.return.mean, 3), `vs ${spct(sy.arms.none.return.mean, 2)} trading every signal · ${pct(sy.arms.brain.return.share_positive, 0)} of windows positive`]);
  if (stt) hero.push(["Strategy backtests", fmt(stt.backtests, 0), `${stt.strategies} strategies on ${stt.pairs} strategy-market pairs`], ["Significant after correction", fmt(stt.holm, 0), `of ${fmt(stt.tests, 0)} hypothesis tests (Holm)`]);
  if (vg && vg.crypto) hero.push(["LOUD forecast right", pct(vg.crypto.loud.precision, 0), `crypto, when flagged (base rate ${pct(vg.crypto.loud.base_rate, 0)})`]);
  $("resHero").innerHTML = hero.map(([k, v, s]) => `<section class="p"><div class="lbl">${k}</div><b class="v glitch">${v}</b><div class="tiny muted">${esc(s)}</div></section>`).join("");
  if (sy) {
    $("sysR").textContent = `${sy.period[0]} → ${sy.period[1]}`;
    $("sysSub").innerHTML = `Each run replays ${sy.bots_per_run} random bots over a random ${sy.window_days}-day window (${fmt(sy.candidates, 0)} candidate trades from ${sy.bots_with_candidates} bots) with real fees, slippage, account sizing and a 3% daily loss halt. The brain starts only with what it learned from the period before these windows.`;
    $("arms").innerHTML = ["none", "gates", "brain"].map(a => { const r = sy.arms[a]; return `<tr><td><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${ARMCOL[a]};margin-right:6px"></i>${a}</td><td class="muted">${ARMNAME[a]}</td><td class="r ${cls(r.return.mean)}">${spct(r.return.mean, 3)}</td><td class="r">${pct(r.return.share_positive, 0)}</td><td class="r">${pct(r.max_dd.mean, 2)}</td><td class="r">${fmt(r.trades.mean, 0)}</td><td class="r ${cls(r.avg_r && r.avg_r.mean)}">${r.avg_r ? rr(r.avg_r.mean, 3) : "–"}</td></tr>`; }).join("");
    const P = sy.paired, names = [["gates_vs_none", "gates vs no brain"], ["brain_vs_none", "brain vs no brain"], ["brain_vs_gates", "brain vs gates only"]];
    $("paired").innerHTML = names.map(([k, n]) => { const p = P[k]; return `<tr><td>${n}</td><td class="r ${cls(p.mean_diff)}">${spct(p.mean_diff, 3)}</td><td class="r muted">${spct(p.ci95[0], 3)} to ${spct(p.ci95[1], 3)}</td><td class="r">${pct(p.share_better, 0)}</td></tr>`; }).join("")
      + (P.brain_vs_none_drawdown ? `<tr><td>drawdown saved by the brain</td><td class="r ${cls(P.brain_vs_none_drawdown.mean_diff)}">${spct(P.brain_vs_none_drawdown.mean_diff, 3)}</td><td class="r muted">${spct(P.brain_vs_none_drawdown.ci95[0], 3)} to ${spct(P.brain_vs_none_drawdown.ci95[1], 3)}</td><td class="r">${pct(P.brain_vs_none_drawdown.share_better, 0)}</td></tr>` : "");
    const ha = (sy.histogram && sy.histogram.arms) || ["none", "gates", "brain"];
    $("histLeg").innerHTML = ha.map(a => `<span><i style="background:${ARMCOL[a]}"></i>${ARMNAME[a]}</span>`).join("")
      + (ha.includes("none") ? "" : `<span class="dim">no-brain arm: mean ${spct(sy.arms.none.return.mean, 1)}, off this scale (see table)</span>`);
    drawHist();
  } else {
    $("sysSub").textContent = "The full-system backtest is not included in this build."; $("arms").innerHTML = ""; $("paired").innerHTML = "";
  }
  if (stt) $("stratKv").innerHTML = kv([["strategies tested", `${stt.strategies} on ${stt.pairs} strategy-market pairs`], ["backtests run", fmt(stt.backtests, 0)], ["hypothesis tests", fmt(stt.tests, 0)],
    ["significant after Holm correction", `<b>${fmt(stt.holm, 0)}</b>`], ["deflated Sharpe of the best", fmt(stt.dsr, 3)],
    ["crypto profitable at Kraken retail fees", `${stt.crypto_retail[0]} of ${stt.crypto_retail[1]}`], ["crypto profitable at a low-fee venue", `${stt.crypto_low_fee[0]} of ${stt.crypto_low_fee[1]}`],
    ["stocks profitable (20+ trades)", `${stt.stocks[0]} of ${stt.stocks[1]}`], ["positive before costs", fmt(stt.gross_positive, 0)],
    ["candidates (train + validation positive)", `${stt.candidates} from ${stt.candidate_strategies} strategies`], ["still positive on the untouched test", `${stt.candidates_test_positive} of ${stt.candidates}`],
    ["candidates: full period vs test", `${rr(stt.candidates_avg_full, 3)} vs ${rr(stt.candidates_avg_test, 3)}`]]);
  if (vg) $("vg").innerHTML = ["crypto", "stock"].filter(a => vg[a]).flatMap(a => ["loud", "quiet"].map(k => { const m = vg[a][k]; return `<tr><td>${a} <span class="dim">${vg[a].horizon_hours}h</span></td><td><span class="gstate g-${k.toUpperCase()}">${k.toUpperCase()}</span></td><td class="r">${fmt(m.auc, 3)}</td><td class="r">${pct(m.flagged_share)}</td><td class="r"><b>${pct(m.precision)}</b></td><td class="r muted">${pct(m.base_rate)}</td></tr>`; })).join("");
  renderFeeRows(); renderLab();
  if (stt) $("top").innerHTML = stt.top.map(x => `<tr><td class="w">${esc(x.id)} <span class="muted">${esc(x.name)}</span></td><td>${esc(x.instrument)}</td><td class="r">${x.trades}</td><td class="r ${cls(x.expectancy_r)}">${rr(x.expectancy_r, 3)}</td><td class="r ${cls(x.gross_expectancy_r)}">${rr(x.gross_expectancy_r, 3)}</td><td class="r">${pct(x.win_rate, 0)}</td><td class="r ${cls(x.test_expectancy_r)}">${rr(x.test_expectancy_r, 3)} (${x.test_trades ?? "–"})</td><td>${x.holm_significant ? "yes" : "no"}</td></tr>`).join("");
}
const SCEN = [["coinbase_retail", "Coinbase 1.20%"], ["kraken_retail", "Kraken 0.80%"], ["ndax", "NDAX 0.20%"], ["low_fee", "Low-fee 0.10%"]];
function renderFeeRows() {
  const fp = (RES && RES.fee_profiles) || [];
  $("feeRows").innerHTML = fp.map(r => `<tr><td class="w">${esc(r.label)}</td><td class="r">${fmt(r.runs, 0)}</td><td class="r ${cls(r.none)}">${spct(r.none, 2)}</td><td class="r ${cls(r.gates)}">${spct(r.gates, 3)}</td><td class="r ${cls(r.brain)}"><b>${spct(r.brain, 3)}</b></td><td class="r">${pct(r.brain_positive, 0)}</td><td class="r">${fmt(r.brain_trades, 0)}</td><td class="r ${cls(r.brain_avg_r)}">${r.brain_avg_r != null ? rr(r.brain_avg_r, 3) : "–"}</td></tr>`).join("")
    || '<tr><td colspan="8" class="empty">not included in this build</td></tr>';
}
function renderLab() {
  const L = RES && RES.swing_lab;
  if (!L) { $("labSub").textContent = "The swing lab is not included in this build."; return; }
  $("labR").textContent = `test period: crypto from ${L.cuts.crypto[1]}, stocks from ${L.cuts.stock[1]}`;
  $("labSub").innerHTML = `8 hourly setups, each tried with ${L.configs_per_setup} exit structures and entry types on 5.5 years of crypto and 3 years of stock data. The structure is chosen on the oldest data, must stay positive on the middle part, and is judged once on the most recent, untouched part. The train data picked the same shape almost everywhere: a <b>4×ATR stop, 2–3R target, up to 96 hours, limit (maker) entry</b>.`;
  const cell = r => r ? `<td class="r ${cls(r.test)}">${r.survivor ? "★ " : ""}${rr(r.test, 3)} <span class="dim">(${r.test_n})</span></td>` : '<td class="r dim">–</td>';
  $("labHead").innerHTML = `<tr><th>setup</th><th>market</th>${SCEN.map(([, n]) => `<th class="r">${n}</th>`).join("")}<th class="r">stocks (no commission)</th></tr>`;
  const setups = [...new Set(L.rows.map(r => r.setup))], rows = [];
  for (const g of ["majors", "memes", "stocks"]) for (const s of setups) {
    const pick = sc => L.rows.find(r => r.group === g && r.setup === s && r.scenario === sc);
    if (g === "stocks") { const r = pick("stock_commission_free"); if (!r) continue; rows.push(`<tr><td>${esc(s.replace(/_/g, " "))}</td><td>stocks</td>${SCEN.map(() => '<td class="r dim">–</td>').join("")}${cell(r)}</tr>`); }
    else rows.push(`<tr><td>${esc(s.replace(/_/g, " "))}</td><td>${g === "majors" ? "BTC · ETH · SOL" : "memecoins"}</td>${SCEN.map(([sc]) => cell(pick(sc))).join("")}<td class="r dim">–</td></tr>`);
  }
  $("labRows").innerHTML = rows.join("");
}
let FEES = null;
async function loadFees() {
  try { FEES = await get("/api/fees"); } catch (e) { return; }
  if (!RES) { try { RES = await get("/api/results"); } catch (e) { /* the list still works without results */ } }
  renderFees();
}
function renderFees() {
  if (!FEES) return;
  const box = $("feeList"); if (box.contains(document.activeElement)) return;
  const bt = {}; ((RES && RES.fee_profiles) || []).forEach(r => bt[r.profile] = r);
  $("feeCur").textContent = "now: " + ((FEES.profiles.find(p => p.name === FEES.current) || {}).label || FEES.current);
  box.innerHTML = FEES.profiles.map(p => { const r = bt[p.name];
    return `<label class="chk"><input type="radio" name="fee" value="${esc(p.name)}" ${p.name === FEES.current ? "checked" : ""}><span><b>${esc(p.label)}</b>${r ? ` <span class="muted">· backtest with the brain: <span class="${cls(r.brain)}">${spct(r.brain, 3)}</span> per window, ${pct(r.brain_positive, 0)} of windows positive, ${fmt(r.brain_trades, 0)} trades</span>` : ""}</span></label>`; }).join("");
}
$("feeSave").onclick = async () => {
  const v = (document.querySelector('input[name="fee"]:checked') || {}).value;
  if (!v) return;
  const j = await command("set_fee_profile", {profile: v}, true);
  if (!j.error) toast(`Crypto fees now: ${((j.result || {}).label) || v}`, "ok");
  document.activeElement && document.activeElement.blur();
  loadFees();
};

function drawHist() {
  const sy = RES && RES.system; if (!sy || !sy.histogram || PAGE !== "results") return;
  const H = sy.histogram, c = $("hist"), [x, w, h] = fit(c); x.clearRect(0, 0, w, h);
  const arms = H.arms || ["none", "gates", "brain"], nb = H.bins, mx = Math.max(1, ...arms.flatMap(a => H.counts[a]));
  const pl = 34, pr = 8, pt = 8, pb = 22, gw = (w - pl - pr) / nb, bw = Math.max(1, (gw - 4) / arms.length), py = v => pt + (1 - v / mx) * (h - pt - pb);
  x.font = "9.5px monospace"; x.fillStyle = "#5e4d5c"; x.strokeStyle = "#1d0f1b";
  for (let k = 0; k <= 4; k++) { const v = mx * k / 4, y = py(v); x.beginPath(); x.moveTo(pl, y); x.lineTo(w - pr, y); x.stroke(); x.fillText(fmt(v, 0), 2, y + 3); }
  arms.forEach((a, j) => { x.fillStyle = ARMCOL[a]; H.counts[a].forEach((v, i) => { if (!v) return; const X = pl + i * gw + 2 + j * bw, Y = py(v); x.fillRect(X, Y, Math.max(1, bw - 1), h - pb - Y); }); });
  const zx = pl + (0 - H.lo) / (H.hi - H.lo) * (w - pl - pr);
  if (zx > pl && zx < w - pr) { x.strokeStyle = "#f4ecf3"; x.setLineDash([3, 3]); x.beginPath(); x.moveTo(zx, pt); x.lineTo(zx, h - pb); x.stroke(); x.setLineDash([]); }
  x.fillStyle = "#8d7a8a"; x.textAlign = "left"; x.fillText(spct(H.lo, 1), pl, h - 6); x.textAlign = "right"; x.fillText(spct(H.hi, 1), w - pr, h - 6); x.textAlign = "center"; x.fillText("0", zx, h - 6); x.textAlign = "start";
  c.onmousemove = e => { const r = c.getBoundingClientRect(), i = Math.floor((e.clientX - r.left - pl) / gw), tp = $("tip");
    if (i < 0 || i >= nb) { tp.style.display = "none"; return; }
    const lo = H.lo + i * (H.hi - H.lo) / nb, hi = lo + (H.hi - H.lo) / nb;
    tp.style.display = "block"; tp.style.left = (e.clientX + 14) + "px"; tp.style.top = (e.clientY + 10) + "px";
    tp.innerHTML = `<b>${spct(lo, 2)} to ${spct(hi, 2)}</b><br>` + arms.map(a => `<span style="color:${ARMCOL[a]}">■</span> ${a}: ${H.counts[a][i]} runs`).join("<br>"); };
  c.onmouseleave = () => { $("tip").style.display = "none"; };
}

/* ---------------------------------------------------------------- live money */
async function loadLive(withElig) {
  try { [BROKERS, LIVE] = await Promise.all([get("/api/brokers"), get("/api/live")]); } catch (e) { return; }
  if (ST.running && (withElig || Date.now() - eligAt > 30000)) {
    eligAt = Date.now();
    const j = await post("/api/command", {command: "live_eligibility", args: {}});
    ELIG = Array.isArray(j.result) ? j.result : null;
  }
  renderLive();
}
function brokerQuote(name) { const b = (BROKERS && BROKERS.brokers[name]) || {}, o = b.saved_options || {}; return o.quote || (b.asset_class === "stock" ? "USD" : "CAD"); }
function renderLive() {
  if (!BROKERS || !LIVE) return;
  const cfg = LIVE.config || {}, armed = !!LIVE.armed, pos = LIVE.positions || [], trades = (LIVE.recent_trades || []).slice().reverse();
  const q = cfg.broker ? brokerQuote(cfg.broker) : "";
  $("liveHead").className = "p " + (armed ? "redglow" : "goodglow");
  $("liveHead").innerHTML = `<div class="livehead"><div><div class="lbl">Real money</div><div class="state ${armed ? "dn" : "up"}">${armed ? "ARMED" : "OFF"}</div></div>
    <div style="flex:1;min-width:240px">${armed ? `Trading real money on <b>${esc(cfg.broker)}</b> for ${cfg.eligible_only === false ? "every listed bot" : "listed bots that have earned it"} (${(cfg.bots || []).length} listed). Limits: <b>${fmt(cfg.max_per_trade, 2)} ${q}</b> per trade, <b>${fmt(cfg.max_total, 2)} ${q}</b> in total, stops for the day after a <b>${fmt(cfg.daily_loss_limit, 2)} ${q}</b> loss. Armed ${t(cfg.armed_at)}.`
      : `Every bot trades paper money. Nothing reaches a real exchange until you connect a broker, set your limits and type the acknowledgement below.${cfg.disarmed_reason ? `<div class="small warnc" style="margin-top:6px">Last disarmed: ${esc(cfg.disarmed_reason)}</div>` : ""}`}</div>
    <div class="kv" style="min-width:220px">${kv([["open live positions", fmt(pos.length, 0)], ["open exposure", `${fmt(LIVE.open_notional, 2)} ${q}`], ["today's live P&L", `<span class="${cls(LIVE.today_pnl)}">${fmt(LIVE.today_pnl, 2)} ${q}</span>`]])}</div>
    <div class="flex">${armed ? '<button class="danger" id="bDisarm">Disarm now</button>' : ""}${pos.length ? '<button class="bad" id="bCloseAll">Sell all live positions</button>' : ""}</div></div>
    ${pos.length ? `<div class="lbl" style="margin:12px 0 4px">Open live positions (exchange stops resting)</div><table><thead><tr><th>bot</th><th>market</th><th class="r">qty</th><th class="r">entry</th><th class="r">exchange stop</th><th>since</th></tr></thead><tbody>${pos.map(p => `<tr><td>${esc(p.bot_id)}</td><td>${esc(p.instrument)}</td><td class="r">${fmt(p.qty, 8)}</td><td class="r">${fmt(p.entry, 4)}</td><td class="r">${fmt(p.stop, 4)}${p.stop_order ? "" : ' <span class="dn">none</span>'}</td><td>${t(p.time)}</td></tr>`).join("")}</tbody></table>` : ""}
    ${trades.length ? `<div class="lbl" style="margin:12px 0 4px">Recent live trades</div><div class="scroll"><table><thead><tr><th>time</th><th>bot</th><th>market</th><th class="r">entry</th><th class="r">exit</th><th class="r">P&amp;L</th><th>why</th></tr></thead><tbody>${trades.map(x => `<tr><td>${t(x.time)}</td><td>${esc(x.bot_id)}</td><td>${esc(x.instrument)}</td><td class="r">${fmt(x.entry, 4)}</td><td class="r">${fmt(x.exit, 4)}</td><td class="r ${cls(x.pnl)}">${fmt(x.pnl, 2)}</td><td class="w">${esc(x.reason)}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
  if ($("bDisarm")) $("bDisarm").onclick = async () => { const j = await post("/api/command", {command: "live_disarm", args: {reason: "owner"}}); toast(j.error || "Real money disarmed. Open positions keep their exchange stops.", j.error ? "err" : "ok"); loadLive(); refresh(); };
  if ($("bCloseAll")) $("bCloseAll").onclick = async () => { if (!confirm("Sell every live position at market now and disarm?")) return; const j = await post("/api/command", {command: "live_close_all", args: {}}); toast(j.error || `Sold ${((j.result || {}).closed) ?? 0} positions; disarmed.`, j.error ? "err" : "ok"); loadLive(); };
  renderBrokers(); renderArm(); renderElig();
}
function renderBrokers() {
  const box = $("brokers"); if (box.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;   // never wipe what is being typed
  box.innerHTML = Object.entries(BROKERS.brokers).map(([name, b]) => {
    const lt = b.last_test, opts = Object.entries(b.options || {}).map(([k, vals]) => `<label class="f">${esc(k)}<select data-opt="${esc(k)}">${vals.map(v => `<option ${((b.saved_options || {})[k] === v) ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>`).join("");
    const extra = (b.extra || []).map(k => `<label class="f">${esc(k.replace(/_/g, " "))}<input data-extra="${esc(k)}" autocomplete="off" spellcheck="false" value="${esc((b.saved_options || {})[k] || "")}"></label>`).join("");
    return `<section class="p bk" data-broker="${esc(name)}"><div class="between"><h3>${esc(b.label)}</h3><span class="pill ${b.asset_class === "stock" ? "pc" : "ph"}">${esc(b.asset_class)}</span></div>
      <div class="small" style="margin-top:6px">${b.configured ? `<span class="up">● connected</span>${lt ? ` · last test ${t(lt.time)}: <span class="${lt.ok ? "up" : "dn"}">${esc(lt.ok ? "ok" : "failed")}</span> <span class="muted">${esc(lt.summary || "")}</span>` : ' · <span class="warnc">not tested yet</span>'}` : '<span class="muted">○ not connected</span>'}</div>
      <div class="help">${esc(b.help)}</div>
      <div class="form"><label class="f">API key<input type="password" data-k="key" autocomplete="off" spellcheck="false" placeholder="${b.configured ? "saved (type to replace)" : "paste the API key"}"></label>
      <label class="f">API secret<input type="password" data-k="secret" autocomplete="off" spellcheck="false" placeholder="${b.configured ? "saved (type to replace)" : "paste the API secret"}"></label>
      <div class="form2">${opts}${extra}</div>
      <div class="flex"><button class="hot" data-act="save">Save &amp; test</button>${b.configured ? '<button data-act="test">Test again</button><button class="bad" data-act="remove">Remove</button>' : ""}</div></div></section>`;
  }).join("");
  for (const card of box.querySelectorAll("[data-broker]")) for (const btn of card.querySelectorAll("[data-act]")) btn.onclick = () => brokerAction(card, btn.dataset.act);
}
async function brokerAction(card, act) {
  const name = card.dataset.broker;
  if (act === "save") {
    const key = card.querySelector('[data-k="key"]'), secret = card.querySelector('[data-k="secret"]'), options = {};
    for (const s of card.querySelectorAll("[data-opt]")) options[s.dataset.opt] = s.value;
    for (const s of card.querySelectorAll("[data-extra]")) options[s.dataset.extra] = s.value.trim();
    if (!key.value.trim() || !secret.value.trim()) return toast("Paste both the API key and the API secret.", "err");
    const j = await post("/api/broker/save", {name, key: key.value, secret: secret.value, options});
    key.value = ""; secret.value = "";                                       // gone from the page as soon as they are sent
    if (j.error) return toast(j.error, "err");
    toast("Saved to the encrypted store. Testing the connection…", "ok");
    act = "test";
  }
  if (act === "test") {
    const j = await post("/api/broker/test", {name});
    if (j.error || !j.ok) toast(`Connection test failed: ${j.error || "unknown error"}`, "err");
    else toast(`Connected to ${j.broker}: cash ${fmt(j.cash, 2)} ${j.quote || ""}${j.real_money === false ? " (paper endpoint)" : ""}`, "ok");
  }
  if (act === "remove") {
    if (!confirm(`Remove the saved ${name} keys from this computer?`)) return;
    const j = await post("/api/broker/remove", {name}); toast(j.error || "Removed.", j.error ? "err" : "ok");
  }
  document.activeElement && document.activeElement.blur();
  loadLive();
}
let ARM = {broker: null, mode: "earned", picked: new Set()};
function renderArm() {
  const body = $("armBody");
  if (body.contains(document.activeElement) && ["INPUT", "SELECT"].includes(document.activeElement.tagName)) return;
  if (LIVE.armed) { body.innerHTML = '<div class="note bad">Real money is armed. Disarm above to change brokers, limits or bots.</div>'; return; }
  const ok = Object.entries(BROKERS.brokers).filter(([, b]) => b.configured && b.last_test && b.last_test.ok);
  if (!ST.running) { body.innerHTML = '<div class="note warn">Start the bots first (Settings): live trading runs inside the bot fleet.</div>'; return; }
  if (!ok.length) { body.innerHTML = '<div class="note">Connect a broker and pass its connection test (step 1) to arm real money.</div>'; return; }
  if (!ARM.broker || !ok.find(([n]) => n === ARM.broker)) ARM.broker = ok[0][0];
  const b = BROKERS.brokers[ARM.broker], qc = brokerQuote(ARM.broker), cfg = LIVE.config || {};
  const cands = (ELIG || []).filter(e => e.asset === b.asset_class), earned = cands.filter(e => e.eligible);
  body.innerHTML = `<div class="form2">
      <label class="f">Broker<select id="aBroker">${ok.map(([n, x]) => `<option value="${esc(n)}" ${n === ARM.broker ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</select></label>
      <label class="f">Max per trade (${qc})<input id="aPer" type="number" min="1" step="any" value="${esc(cfg.max_per_trade || 25)}"></label>
      <label class="f">Max total at once (${qc})<input id="aTot" type="number" min="1" step="any" value="${esc(cfg.max_total || 100)}"></label>
      <label class="f">Stop for the day after losing (${qc})<input id="aLoss" type="number" min="1" step="any" value="${esc(cfg.daily_loss_limit || 25)}"></label></div>
    <div class="gap10" style="margin-top:12px">
      <label class="chk"><input type="radio" name="aMode" value="earned" ${ARM.mode === "earned" ? "checked" : ""}><span><b>Let the bots decide (recommended).</b> Every ${esc(b.asset_class)} bot may trade real money the moment it has earned it; ${earned.length} of ${cands.length} have today.</span></label>
      <label class="chk"><input type="radio" name="aMode" value="picked" ${ARM.mode === "picked" ? "checked" : ""}><span><b>Only the bots I tick</b> in the table below (${ARM.picked.size} ticked). They still have to have earned it.</span></label>
      <label class="chk"><input type="checkbox" id="aAny"><span class="warnc">Advanced: also allow bots with no track record (not recommended: no strategy here passed the correction for testing many ideas).</span></label>
      <div class="note bad">Real orders, real money, real losses. Spot only, long only, no leverage. Each entry gets a protective stop resting on the exchange. To arm, type exactly: <span class="ack">${esc(LIVE.ack_text)}</span></div>
      <div class="flex"><input id="aAck" style="flex:1;min-width:260px" placeholder="type the sentence above" autocomplete="off" spellcheck="false"><button class="danger" id="aGo">Arm real money</button></div></div>`;
  $("aBroker").onchange = e => { ARM.broker = e.target.value; renderArm(); renderElig(); };
  for (const r of document.querySelectorAll('input[name="aMode"]')) r.onchange = e => { ARM.mode = e.target.value; renderElig(); };
  $("aGo").onclick = armNow;
}
async function armNow() {
  const b = BROKERS.brokers[ARM.broker], cands = (ELIG || []).filter(e => e.asset === b.asset_class);
  const bots = ARM.mode === "picked" ? [...ARM.picked] : cands.map(e => e.bot_id);
  if (!bots.length) return toast(ARM.mode === "picked" ? "Tick at least one bot in the table below." : "No bots available for this broker yet.", "err");
  const limits = {max_per_trade: parseFloat($("aPer").value), max_total: parseFloat($("aTot").value), daily_loss_limit: parseFloat($("aLoss").value), eligible_only: !$("aAny").checked};
  if (!(limits.max_per_trade > 0 && limits.max_total > 0 && limits.daily_loss_limit > 0)) return toast("Set all three limits (more than 0).", "err");
  if (!confirm(`Arm REAL MONEY on ${b.label}: at most ${limits.max_per_trade} per trade, ${limits.max_total} in total, stop after losing ${limits.daily_loss_limit} in a day?`)) return;
  const j = await post("/api/command", {command: "live_arm", args: {broker: ARM.broker, ack: $("aAck").value, limits, bots, overrides: []}});
  if (j.error) toast(j.error.replace(/^ValueError: /, ""), "err"); else toast("Real money armed.", "ok");
  $("aAck").value = ""; loadLive(); refresh();
}
function renderElig() {
  const rows = ELIG, b = ARM.broker && BROKERS ? BROKERS.brokers[ARM.broker] : null;
  if (!rows) { $("elig").innerHTML = `<tr><td colspan="5" class="empty">${ST.running ? "loading…" : "Start the bots to check which bots have earned real money."}</td></tr>`; $("eligR").textContent = ""; return; }
  const list = b ? rows.filter(e => e.asset === b.asset_class) : rows, n = list.filter(e => e.eligible).length, pick = ARM.mode === "picked" && !(LIVE && LIVE.armed);
  $("eligR").textContent = `${n} of ${list.length} have earned it`;
  const sorted = list.slice().sort((a, c) => (c.eligible - a.eligible) || a.bot_id.localeCompare(c.bot_id));
  $("elig").innerHTML = sorted.map(e => `<tr><td>${pick ? `<input type="checkbox" data-pick="${esc(e.bot_id)}" ${ARM.picked.has(e.bot_id) ? "checked" : ""}> ` : ""}${esc(e.bot_id)}</td><td>${esc(e.strategy_id)} <span class="muted">${esc(e.name || "")}</span></td><td>${esc(e.venue)} ${esc(e.instrument)}</td><td>${e.eligible ? '<span class="pill pu">YES</span>' : '<span class="pill pn">NOT YET</span>'}</td><td class="w muted">${esc(e.why)}</td></tr>`).join("");
  for (const c of document.querySelectorAll("[data-pick]")) c.onchange = e => { e.target.checked ? ARM.picked.add(e.target.dataset.pick) : ARM.picked.delete(e.target.dataset.pick); };
}

/* ---------------------------------------------------------------- settings */
function renderSettings() {
  const a = S.account || ST.account || {}, ap = ST.autopilot || {};
  $("setEq").textContent = money(a.equity);
  $("setEqSub").textContent = `${a.currency || "USD"} · free cash ${money(a.cash)} · ${fmt(a.open_positions, 0)} open positions`;
  $("apState").innerHTML = ST.running ? '<span class="up">RUNNING</span>' : ap.enabled ? '<span class="warnc">STARTING</span>' : '<span class="dn">STOPPED</span>';
  $("apAuto").innerHTML = ap.enabled ? '<span class="up">ON</span>' : '<span class="muted">OFF</span>';
  $("sys").innerHTML = kv([["uptime", S.uptime_s != null ? fmt(S.uptime_s / 60, 1) + " min" : "–"], ["decisions", `${fmt(S.completed_evaluations, 0)} / ${fmt(S.scheduled_evaluations, 0)}`], ["decision time p95", S.eval_ms_p95 != null ? fmt(S.eval_ms_p95, 1) + " ms" : "–"],
    ["bar close → decision", S.latency_ms_p95 != null ? fmt(S.latency_ms_p95 / 1000, 1) + " s" : "–"], ["data requests", S.requests != null ? `${fmt(S.requests, 0)} (${fmt(100 * (S.rate_429 || 0), 2)}% rate-limited)` : "–"],
    ["memory", S.rss_mb != null ? fmt(S.rss_mb, 0) + " MB" : "–"], ["database", S.db_bytes != null ? fmt(S.db_bytes / 1048576, 1) + " MB" : "–"], ["storage", S.storage_ok === false ? '<span class="dn">FAILING</span>' : "ok"]]);
  $("series").innerHTML = (SER.series || []).map(x => `<tr><td>${esc(x.key)}</td><td class="${x.status === "ok" ? "up" : "warnc"}">${esc(x.status)}</td><td>${x.bars}/${x.need}</td><td>${x.subscribers}</td></tr>`).join("") || `<tr><td class="empty">${esc(SER.note || (ST.running ? "loading…" : "the bots are stopped"))}</td></tr>`;
  $("events").innerHTML = (EV || []).slice(0, 80).map(e => `<tr><td class="muted">${hm(e.time)}</td><td class="w ${e.level === "critical" || e.level === "error" ? "dn" : e.level === "warning" ? "warnc" : ""}">${esc(e.message)}</td></tr>`).join("") || '<tr><td class="empty">no alerts</td></tr>';
  $("about").innerHTML = kv([["money", ST.live_armed ? '<span class="dn">real money armed (Live money page)</span>' : '<span class="up">paper only</span>'], ["bots", `${fmt(BOTS.length, 0)} configured`],
    ["data folder", esc(ST.home || "–")], ["broker keys", BROKERS ? esc(BROKERS.secret_store) : "encrypted secret store"], ["what it is", "An educational research and paper-trading tool. Not financial advice. Measured results are on the Results page; none is a promise."]]);
}

/* ---------------------------------------------------------------- refresh loop */
function renderPage() {
  renderChrome();
  if (PAGE === "command") renderCommand();
  if (PAGE === "bots") { renderTiles(); renderBots(); }
  if (PAGE === "brain") renderBrain();
  if (PAGE === "settings") renderSettings();
  if (PAGE === "results") drawHist();
}
async function refresh() {
  try {
    const wantSeries = PAGE === "settings";
    const [st, s, b, br, tr, tk, ev, ser] = await Promise.all([get("/api/status"), getF("summary"), getF("bots"), getF("brain"), getF("trades?limit=400"), getF("tickers"), getF("events"),
      wantSeries ? getF("series") : Promise.resolve(SER)]);
    ST = st; S = s || {}; BOTS = Array.isArray(b) ? b : []; BRAIN = br || {}; TR = Array.isArray(tr) ? tr : []; TICK = Array.isArray(tk) ? tk : []; EV = Array.isArray(ev) ? ev : []; SER = ser || {};
    DOWN = 0;
    layout(); NET.nodes.forEach(n => { const x = BOTS.find(y => y.bot_id === n.id); if (x) n.b = x; }); spawnPulses();
    renderPage();
    if (PAGE === "command") loadChart();
    if (PAGE === "live") loadLive(false);
  } catch (e) {
    DOWN++; renderChrome();
    $("eqSub") && ($("eqSub").textContent = "Jarvus is not responding: is its window still open?");
  }
}
(async function loop() { await refresh(); setTimeout(loop, DOWN ? 10000 : 5000); })();
requestAnimationFrame(drawNet);
get("/api/library").then(l => { if (!LIB) LIB = l; $("navStrat").textContent = fmt(l.counts.counted_strategies, 0); }).catch(() => {});
window.addEventListener("resize", () => { for (const c of document.querySelectorAll("canvas")) c.width = 0; renderPage(); if (PAGE === "command") { candles($("chart"), CHART.data || {}); } });
show(location.hash.slice(1) || "command");
