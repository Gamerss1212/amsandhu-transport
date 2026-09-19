/* Jarvus Terminal front end.
   No libraries: every chart is inline SVG built here, which keeps the app's
   no-install promise intact all the way to the browser. */
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const state = { scan: null, detail: null, settings: {}, sort: { key: 'heat', dir: -1 }, health: null };

/* ---------------- settings ---------------- */
const DEFAULTS = {
  theme: 'auto', accent: 'blue', density: 'normal', fontSize: 14,
  panels: { tiles: true, explainer: true, howto: true },
  sparklines: true,
  columns: ['market', 'heat', 'state', 'price', 'chg24', 'agree', 'consensus',
            'trend', 'atr', 'plan', 'cost', 'liquidity', 'news'],
  indicators: ['ema:21', 'ema:200'],
  stopAtr: 4, targetR: 2,
  views: {},
  filters: { search: '', minHeat: 0, state: '', verdict: '', minVol: 0 },
};

function applySettings() {
  const s = state.settings;
  const root = document.documentElement;
  root.dataset.theme = s.theme === 'auto' ? '' : s.theme;
  if (s.theme === 'auto') root.removeAttribute('data-theme');
  root.dataset.accent = s.accent || 'blue';
  root.dataset.density = s.density || 'normal';
  root.style.setProperty('--fs-base', (s.fontSize || 14) + 'px');
  for (const [k, on] of Object.entries(s.panels || {})) {
    $$(`[data-panel="${k}"]`).forEach(el => { el.style.display = on ? '' : 'none'; });
  }
}

async function saveSettings(patch) {
  Object.assign(state.settings, patch || {});
  applySettings();
  try { localStorage.setItem('jarvus-settings', JSON.stringify(state.settings)); } catch {}
  try {
    await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state.settings) });
  } catch {}
}

/* ---------------- formatting ---------------- */
const fmtPrice = v => {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (a >= 1) return v.toFixed(2);
  if (a >= 0.01) return v.toFixed(4);
  return v.toPrecision(3);
};
const fmtQty = v => {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (a >= 1) return v.toLocaleString(undefined, { maximumFractionDigits: 3 });
  return Number(v.toPrecision(4)).toString();
};
const pct = (v, d = 1) => v == null || !isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`;
const usd = v => v == null ? '—' : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B`
  : v >= 1e6 ? `$${(v / 1e6).toFixed(0)}M` : `$${(v / 1e3).toFixed(0)}K`;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
/* Direction always carries a glyph and a sign, so colour reinforces and never carries. */
const dirCls = v => v > 0 ? 'up' : v < 0 ? 'down' : 'muted';
const dirGlyph = v => v > 0 ? '▲' : v < 0 ? '▼' : '•';

/* ---------------- tooltip ---------------- */
const tip = $('#tip');
function showTip(html, ev) {
  tip.innerHTML = html; tip.classList.add('on');
  const pad = 14, r = tip.getBoundingClientRect();
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
  tip.style.left = Math.max(8, x) + 'px'; tip.style.top = Math.max(8, y) + 'px';
}
const hideTip = () => tip.classList.remove('on');
document.addEventListener('scroll', hideTip, true);

/* ---------------- svg helpers ---------------- */
const SVG = 'http://www.w3.org/2000/svg';
const el = (n, a = {}) => { const e = document.createElementNS(SVG, n);
  for (const k in a) e.setAttribute(k, a[k]); return e; };

function sparkline(values, w = 74, h = 22) {
  const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, class: 'spark', 'aria-hidden': 'true' });
  const v = (values || []).filter(x => isFinite(x));
  if (v.length < 2) return svg;
  const lo = Math.min(...v), hi = Math.max(...v), span = (hi - lo) || 1;
  const X = i => (i / (v.length - 1)) * (w - 2) + 1;
  const Y = k => h - 2 - ((k - lo) / span) * (h - 4);
  svg.appendChild(el('path', {
    d: v.map((k, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(k).toFixed(1)}`).join(' '),
    fill: 'none', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
    stroke: v[v.length - 1] >= v[0] ? 'var(--up)' : 'var(--down)' }));
  return svg;
}

/**
 * Price with optional indicator overlays.
 * Price and volume are two stacked plots rather than one plot with two y-scales: a
 * dual axis lets two unrelated scales be slid against each other until they look
 * correlated, inventing a relationship the data does not contain.
 */
function priceChart(candles, overlays = [], height = 230) {
  const wrap = document.createElement('figure');
  if (!candles || candles.length < 3) { wrap.innerHTML = '<p class="muted small">No candles.</p>'; return wrap; }
  const W = 900, H = height, m = { t: 10, r: 56, b: 18, l: 8 };
  let lo = Math.min(...candles.map(c => c.l)), hi = Math.max(...candles.map(c => c.h));
  overlays.forEach(o => (o.values || []).forEach(v => {
    if (v != null && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  const span = (hi - lo) || 1;
  const X = i => m.l + (i / (candles.length - 1)) * (W - m.l - m.r);
  const Y = v => m.t + (1 - (v - lo) / span) * (H - m.t - m.b);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `Price over the last ${candles.length} hours` });

  const g = el('g', { class: 'axis' });
  for (let i = 0; i <= 4; i++) {
    const v = lo + (span * i) / 4, y = Y(v);
    g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grid-line' }));
    const t = el('text', { x: W - m.r + 6, y: y + 3 }); t.textContent = fmtPrice(v); g.appendChild(t);
  }
  svg.appendChild(g);

  const defs = el('defs');
  const grad = el('linearGradient', { id: 'pg', x1: '0', y1: '0', x2: '0', y2: '1' });
  grad.appendChild(el('stop', { offset: '0%', 'stop-color': 'var(--accent)', 'stop-opacity': '.18' }));
  grad.appendChild(el('stop', { offset: '100%', 'stop-color': 'var(--accent)', 'stop-opacity': '0' }));
  defs.appendChild(grad); svg.appendChild(defs);
  svg.appendChild(el('path', {
    d: candles.map((c, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(c.c).toFixed(1)}`).join(' ')
      + ` L${X(candles.length - 1).toFixed(1)},${Y(lo)} L${X(0).toFixed(1)},${Y(lo)} Z`,
    fill: 'url(#pg)' }));
  svg.appendChild(el('path', {
    d: candles.map((c, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(c.c).toFixed(1)}`).join(' '),
    fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2,
    'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));

  overlays.forEach(o => {
    const pts = [];
    (o.values || []).forEach((v, i) => {
      if (v == null || !isFinite(v)) { pts.push(null); return; }
      pts.push(`${X(i).toFixed(1)},${Y(v).toFixed(1)}`);
    });
    let d = '', pen = false;
    pts.forEach(p => { if (p == null) { pen = false; return; } d += (pen ? 'L' : 'M') + p + ' '; pen = true; });
    if (d) svg.appendChild(el('path', { d, fill: 'none', stroke: o.color || 'var(--hot)',
      'stroke-width': 1.5, opacity: .9, 'stroke-linejoin': 'round' }));
  });

  const cross = el('line', { y1: m.t, y2: H - m.b, stroke: 'var(--text-muted)', 'stroke-width': 1, opacity: 0 });
  const dot = el('circle', { r: 4, fill: 'var(--accent)', stroke: 'var(--surface-1)', 'stroke-width': 2, opacity: 0 });
  svg.appendChild(cross); svg.appendChild(dot);
  const hit = el('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b,
    fill: 'transparent', style: 'cursor:crosshair' });
  svg.appendChild(hit);
  hit.addEventListener('mousemove', ev => {
    const bb = svg.getBoundingClientRect();
    const rel = (ev.clientX - bb.left) / bb.width * W;
    let i = Math.round(((rel - m.l) / (W - m.l - m.r)) * (candles.length - 1));
    i = Math.max(0, Math.min(candles.length - 1, i));
    const c = candles[i];
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('opacity', .55);
    dot.setAttribute('cx', X(i)); dot.setAttribute('cy', Y(c.c)); dot.setAttribute('opacity', 1);
    const ov = overlays.map(o => {
      const v = (o.values || [])[i];
      return v == null || !isFinite(v) ? '' :
        `<div class="r"><span>${esc(o.label)}</span><span>${fmtPrice(v)}</span></div>`;
    }).join('');
    showTip(`<div class="t">${esc(c.t)}</div>
      <div class="r"><span>open</span><span>${fmtPrice(c.o)}</span></div>
      <div class="r"><span>high</span><span>${fmtPrice(c.h)}</span></div>
      <div class="r"><span>low</span><span>${fmtPrice(c.l)}</span></div>
      <div class="r"><span>close</span><span>${fmtPrice(c.c)}</span></div>${ov}`, ev);
  });
  hit.addEventListener('mouseleave', () => { hideTip(); cross.setAttribute('opacity', 0); dot.setAttribute('opacity', 0); });

  wrap.appendChild(svg);
  if (overlays.length) {
    const lg = document.createElement('div');
    lg.className = 'legend';
    lg.innerHTML = `<span class="item"><span class="sw" style="background:var(--accent)"></span>Close</span>`
      + overlays.map(o => `<span class="item"><span class="sw" style="background:${o.color}"></span>${esc(o.label)}</span>`).join('');
    wrap.insertBefore(lg, svg);
  }
  const cap = document.createElement('figcaption');
  cap.textContent = `Last ${candles.length} hourly bars. Only closed bars are drawn.`;
  wrap.appendChild(cap);
  return wrap;
}

function volumeChart(candles, height = 62) {
  const wrap = document.createElement('figure');
  if (!candles || !candles.length) return wrap;
  const W = 900, H = height, m = { t: 6, r: 56, b: 12, l: 8 };
  const hi = Math.max(...candles.map(c => c.v)) || 1;
  const bw = Math.max(1, (W - m.l - m.r) / candles.length - 1);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Volume per hour' });
  candles.forEach((c, i) => {
    const x = m.l + (i / (candles.length - 1)) * (W - m.l - m.r - bw);
    const h = Math.max(1, (c.v / hi) * (H - m.t - m.b));
    const r = el('rect', { x, y: H - m.b - h, width: bw, height: h, rx: Math.min(2, bw / 2),
      fill: 'var(--text-muted)', opacity: .5 });
    r.addEventListener('mousemove', ev => showTip(
      `<div class="t">${esc(c.t)}</div><div class="r"><span>volume</span><span>${c.v.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span></div>`, ev));
    r.addEventListener('mouseleave', hideTip);
    svg.appendChild(r);
  });
  wrap.appendChild(svg);
  const cap = document.createElement('figcaption'); cap.textContent = 'Volume, same hours.';
  wrap.appendChild(cap);
  return wrap;
}

function calibrationChart(buckets) {
  const wrap = document.createElement('figure');
  const pts = (buckets || []).filter(b => b.n > 0 && b.big_move_rate != null);
  if (pts.length < 2) {
    wrap.innerHTML = '<p class="muted small">Not enough graded predictions yet to draw a reliability curve.</p>';
    return wrap;
  }
  const W = 560, H = 300, m = { t: 14, r: 16, b: 38, l: 46 };
  const X = v => m.l + v * (W - m.l - m.r);
  const Y = v => m.t + (1 - v) * (H - m.t - m.b);
  const lg = document.createElement('div');
  lg.className = 'legend';
  lg.innerHTML = `<span class="item"><span class="sw" style="background:var(--accent)"></span>Measured on your data</span>
    <span class="item"><span class="sw" style="background:var(--text-muted)"></span>Perfect calibration</span>`;
  wrap.appendChild(lg);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': 'Predicted heat against measured big-move rate' });
  const g = el('g', { class: 'axis' });
  for (let i = 0; i <= 4; i++) {
    const f = i / 4, y = Y(f), x = X(f);
    g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grid-line' }));
    const ty = el('text', { x: m.l - 8, y: y + 3, 'text-anchor': 'end' });
    ty.textContent = `${(f * 100).toFixed(0)}%`; g.appendChild(ty);
    const tx = el('text', { x, y: H - m.b + 15, 'text-anchor': 'middle' });
    tx.textContent = f.toFixed(2); g.appendChild(tx);
  }
  svg.appendChild(g);
  svg.appendChild(el('line', { x1: X(0), y1: Y(0), x2: X(1), y2: Y(1),
    stroke: 'var(--text-muted)', 'stroke-width': 2, opacity: .45 }));
  svg.appendChild(el('path', {
    d: pts.map((b, i) => `${i ? 'L' : 'M'}${X(b.mean_score)},${Y(b.big_move_rate / 100)}`).join(' '),
    fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2, 'stroke-linejoin': 'round' }));
  pts.forEach(b => {
    const c = el('circle', { cx: X(b.mean_score), cy: Y(b.big_move_rate / 100), r: 5,
      fill: 'var(--accent)', stroke: 'var(--surface-1)', 'stroke-width': 2 });
    c.addEventListener('mousemove', ev => showTip(
      `<div class="t">Heat ${esc(b.range)}</div>
       <div class="r"><span>said</span><span>${b.mean_score.toFixed(2)}</span></div>
       <div class="r"><span>big move followed</span><span>${b.big_move_rate}%</span></div>
       <div class="r"><span>sample</span><span>${b.n}</span></div>`, ev));
    c.addEventListener('mouseleave', hideTip);
    svg.appendChild(c);
  });
  const xl = el('text', { x: (m.l + W - m.r) / 2, y: H - 4, 'text-anchor': 'middle',
    fill: 'var(--text-muted)', 'font-size': '11' });
  xl.textContent = 'heat score the app gave'; svg.appendChild(xl);
  wrap.appendChild(svg);
  const cap = document.createElement('figcaption');
  cap.textContent = 'Points above the line mean the app understates; below means it overstates.';
  wrap.appendChild(cap);
  return wrap;
}

function equityChart(curve, startCash) {
  const wrap = document.createElement('figure');
  if (!curve || curve.length < 2) {
    wrap.innerHTML = '<p class="muted small">Close a few trades and the equity curve appears here.</p>';
    return wrap;
  }
  const W = 820, H = 180, m = { t: 10, r: 56, b: 16, l: 8 };
  const vals = curve.map(p => p.equity);
  const lo = Math.min(startCash, ...vals), hi = Math.max(startCash, ...vals);
  const span = (hi - lo) || 1;
  const X = i => m.l + (i / (curve.length - 1)) * (W - m.l - m.r);
  const Y = v => m.t + (1 - (v - lo) / span) * (H - m.t - m.b);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Equity over closed trades' });
  const g = el('g', { class: 'axis' });
  for (let i = 0; i <= 3; i++) {
    const v = lo + span * i / 3, y = Y(v);
    g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grid-line' }));
    const t = el('text', { x: W - m.r + 6, y: y + 3 }); t.textContent = fmtPrice(v); g.appendChild(t);
  }
  svg.appendChild(g);
  svg.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: Y(startCash), y2: Y(startCash),
    stroke: 'var(--text-muted)', 'stroke-width': 1.5, opacity: .6 }));
  svg.appendChild(el('path', {
    d: curve.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(p.equity).toFixed(1)}`).join(' '),
    fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2, 'stroke-linejoin': 'round' }));
  wrap.appendChild(svg);
  const lg = document.createElement('div');
  lg.className = 'legend';
  lg.innerHTML = `<span class="item"><span class="sw" style="background:var(--accent)"></span>Equity</span>
    <span class="item"><span class="sw" style="background:var(--text-muted)"></span>Starting cash</span>`;
  wrap.insertBefore(lg, svg);
  const cap = document.createElement('figcaption'); cap.textContent = 'Equity after each closed trade.';
  wrap.appendChild(cap);
  return wrap;
}

function termBars(terms, colorVar) {
  const box = document.createElement('div');
  const entries = Object.entries(terms || {}).sort((a, b) => b[1] - a[1]);
  if (!entries.length) { box.innerHTML = '<p class="muted small">No contributing terms.</p>'; return box; }
  entries.forEach(([k, v]) => {
    const row = document.createElement('div');
    row.className = 'term';
    row.innerHTML = `<span class="sec">${esc(k.replace(/_/g, ' '))}</span>
      <span class="tr"><span class="tf" style="width:${(v * 100).toFixed(0)}%;background:${colorVar}"></span></span>
      <span class="mono tiny sec" style="text-align:right">${v.toFixed(2)}</span>`;
    box.appendChild(row);
  });
  return box;
}

/* ---------------- chips ---------------- */
const gateChip = g => {
  if (!g || !g.label) return '<span class="chip">no data</span>';
  const cls = g.label === 'LOUD' ? 'loud' : g.label === 'COILED' ? 'coiled' : '';
  return `<span class="chip ${cls}"><span class="sw"></span>${esc(g.label)}</span>`;
};
const verdictChip = v => `<span class="chip ${v === 'BUY' ? 'buy' : ''}"><span class="sw"></span>${esc(v || '—')}</span>`;

/* ---------------- api ---------------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}
const post = (path, body) => api(path, { method: 'POST',
  headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });

/* ---------------- columns ---------------- */
const COLUMNS = {
  market:    { label: 'Market', sort: m => m.base,
               cell: m => `<strong>${esc(m.base)}</strong><span class="muted tiny">/${esc(m.quote)}</span>
                 <div class="tiny muted">${esc(m.venue)} · ${esc(m.kind)}</div>` },
  heat:      { label: 'Heat', sort: m => m.gate?.blow_score ?? -1,
               cell: (m, ctx) => `<div class="heat"><span class="track"><span class="fill"
                 style="width:${((m.gate?.blow_score || 0) / ctx.maxHeat * 100).toFixed(0)}%"></span></span>
                 <span class="val">${(m.gate?.blow_score ?? 0).toFixed(2)}</span></div>` },
  spark:     { label: 'Trend', sort: m => m.change_24h_pct, cell: () => '' },
  state:     { label: 'State', sort: m => m.gate?.label || '', cell: m => gateChip(m.gate) },
  price:     { label: 'Price', num: true, sort: m => m.price, cell: m => fmtPrice(m.price) },
  chg24:     { label: '24h', num: true, sort: m => m.change_24h_pct,
               cell: m => `<span class="${dirCls(m.change_24h_pct)}">${dirGlyph(m.change_24h_pct)} ${pct(m.change_24h_pct)}</span>` },
  agree:     { label: 'Agree', num: true, sort: m => m.swarm?.families_agreeing ?? -1,
               cell: m => m.swarm ? `${m.swarm.families_agreeing}<span class="muted tiny">/${m.swarm.agents_fired}</span>` : '—' },
  consensus: { label: 'Consensus', num: true, sort: m => m.swarm?.consensus ?? -1,
               cell: m => m.swarm ? m.swarm.consensus.toFixed(3) : '—' },
  trend:     { label: 'Structure', sort: m => m.structure?.trend || '',
               cell: m => `<span class="tiny sec">${esc(m.structure?.trend || '—')}</span>
                 <div class="tiny muted">${esc(m.structure?.ema_stack || '')}</div>` },
  atr:       { label: 'Move/bar', num: true, sort: m => m.structure?.atr_pct ?? -1,
               cell: m => m.structure?.atr_pct != null ? m.structure.atr_pct.toFixed(2) + '%' : '—' },
  bigmove:   { label: 'Big move is', num: true, sort: m => m.big_move_threshold_pct ?? -1,
               cell: m => m.big_move_threshold_pct != null ? '≥' + m.big_move_threshold_pct + '%' : '—' },
  plan:      { label: 'Plan', sort: m => m.signal?.verdict || '',
               cell: m => verdictChip(m.signal?.verdict) + (m.signal?.confluence
                 ? `<div class="tiny muted">${m.signal.confluence.score}/${m.signal.confluence.max} ${esc(m.signal.confluence.grade)}</div>` : '') },
  cost:      { label: 'Cost', num: true, sort: m => m.signal?.confluence?.cost_r ?? 9,
               cell: m => m.signal?.confluence ? (m.signal.confluence.cost_r * 100).toFixed(0) + '%' : '—' },
  rsi:       { label: 'RSI', num: true, sort: m => m.structure?.rsi14 ?? -1,
               cell: m => m.structure?.rsi14 ?? '—' },
  rvol:      { label: 'RVOL', num: true, sort: m => m.structure?.rvol ?? -1,
               cell: m => m.structure?.rvol ?? '—' },
  liquidity: { label: 'Liquidity', num: true, sort: m => m.usd_volume_24h,
               cell: m => `<span class="muted">${usd(m.usd_volume_24h)}</span>` },
  news:      { label: 'News', sort: m => (m.news || []).length,
               cell: m => (m.news || []).length ? `<span class="hot">${m.news.length}</span>` : '<span class="muted">—</span>' },
};

/* ---------------- markets ---------------- */
function renderTiles(s) {
  const u = s.universe;
  const buys = s.markets.filter(m => m.signal?.verdict === 'BUY').length;
  const louds = s.markets.filter(m => m.gate?.label === 'LOUD').length;
  const sw = s.swarm || {};
  const tiles = [
    ['Markets scanned', u.discovered.toLocaleString(), `${u.liquid} cleared the liquidity floor`],
    ['Assets analysed', u.analysed, `deduplicated from ${u.assets_after_dedupe}`],
    ['Evaluations', (sw.total_evaluations || 0).toLocaleString(),
      `${sw.strategies_loaded || 0} strategies × ${u.analysed} markets`],
    ['Moving now', louds, 'gate reads LOUD'],
    ['Plans that passed', buys, 'structure and cost gates clear'],
    ['Scan time', s.elapsed_s + 's', `fee tier: ${s.fee_tier}`],
  ];
  $('#tiles').innerHTML = tiles.map(([k, v, sub]) =>
    `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${esc(String(v))}</div>
     <div class="s">${esc(sub)}</div></div>`).join('');
}

function filteredRows() {
  const f = state.settings.filters || {};
  let rows = (state.scan?.markets || []).filter(m => !m.error);
  if (f.search) {
    const q = f.search.toLowerCase();
    rows = rows.filter(m => (m.base + m.symbol).toLowerCase().includes(q));
  }
  if (f.minHeat) rows = rows.filter(m => (m.gate?.blow_score || 0) >= f.minHeat);
  if (f.state) rows = rows.filter(m => m.gate?.label === f.state);
  if (f.verdict) rows = rows.filter(m => m.signal?.verdict === f.verdict);
  if (f.minVol) rows = rows.filter(m => (m.usd_volume_24h || 0) >= f.minVol);
  const col = COLUMNS[state.sort.key];
  if (col) {
    rows.sort((a, b) => {
      const x = col.sort(a), y = col.sort(b);
      if (typeof x === 'string') return state.sort.dir * x.localeCompare(y);
      return state.sort.dir * ((x ?? -1) - (y ?? -1));
    });
  }
  return rows;
}

function renderMarkets() {
  const wrap = $('#marketsWrap');
  const all = (state.scan?.markets || []).filter(m => !m.error);
  const rows = filteredRows();
  $('#rowCount').textContent = `${rows.length} of ${all.length} shown`;
  if (!all.length) { wrap.innerHTML = '<p class="muted">No markets returned candles. Rescan.</p>'; return; }

  const cols = (state.settings.columns || DEFAULTS.columns).filter(c => COLUMNS[c]);
  const maxHeat = Math.max(...all.map(m => m.gate?.blow_score || 0), 0.01);
  const ctx = { maxHeat };

  const head = cols.map(k => {
    const c = COLUMNS[k];
    const active = state.sort.key === k;
    const arrow = active ? `<span class="arrow">${state.sort.dir < 0 ? '▼' : '▲'}</span>` : '';
    return `<th class="sortable ${c.num ? 'n' : ''}" data-col="${k}">${esc(c.label)}${arrow}</th>`;
  }).join('');

  wrap.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody></tbody></table>`;
  const tb = $('tbody', wrap);
  const showSpark = state.settings.sparklines !== false;

  rows.forEach(m => {
    const tr = document.createElement('tr');
    tr.className = 'row'; tr.tabIndex = 0;
    tr.innerHTML = cols.map(k => {
      const c = COLUMNS[k];
      return `<td class="${c.num ? 'n' : ''}" data-cell="${k}">${k === 'spark' ? '' : c.cell(m, ctx)}</td>`;
    }).join('');
    if (cols.includes('spark') && showSpark) {
      const td = $(`[data-cell="spark"]`, tr);
      if (td) td.appendChild(sparkline((m.sparkline || [])));
    }
    tr.addEventListener('mousemove', ev => showTip(
      `<div class="t">${esc(m.symbol)}</div><div>${esc(m.gate?.explain || '')}</div>`
      + (m.swarm?.top_reasons?.length ? `<div class="r" style="margin-top:4px"><span>${esc(m.swarm.top_reasons[0])}</span></div>` : ''), ev));
    tr.addEventListener('mouseleave', hideTip);
    const open = () => openDetail(m.symbol, m.venue);
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    tb.appendChild(tr);
  });

  $$('th.sortable', wrap).forEach(th => th.addEventListener('click', () => {
    const k = th.dataset.col;
    state.sort = state.sort.key === k ? { key: k, dir: -state.sort.dir } : { key: k, dir: -1 };
    renderMarkets();
  }));
}

async function loadScan(force) {
  $('#marketsWrap').innerHTML = '<div class="load"><span class="spin"></span>scanning every liquid market…</div>';
  const q = new URLSearchParams({ n: $('#deepN').value, fee_tier: $('#feeTier').value,
    account: $('#account').value, force: force ? '1' : '0' });
  try {
    const s = await api('/api/scan?' + q);
    state.scan = s;
    renderTiles(s); renderMarkets(); renderSwarm();
    const sw = s.swarm || {};
    $('#subtitle').textContent =
      `${s.universe.discovered.toLocaleString()} markets · ${s.universe.analysed} analysed · `
      + `${(sw.total_evaluations || 0).toLocaleString()} evaluations · ${s.elapsed_s}s`;
    loadAlerts(true);
  } catch (e) {
    $('#marketsWrap').innerHTML = `<p class="down">Scan failed: ${esc(e.message)}</p>`;
  }
}

/* ---------------- detail ---------------- */
async function openDetail(symbol, venue) {
  showTab('detail');
  const box = $('#detail');
  box.innerHTML = `<div class="card"><div class="load"><span class="spin"></span>loading ${esc(symbol)}…</div></div>`;
  let d;
  try {
    d = await api('/api/market?' + new URLSearchParams({ symbol, venue: venue || 'okx',
      fee_tier: $('#feeTier').value, account: $('#account').value }));
  } catch (e) { box.innerHTML = `<div class="card down">Could not load ${esc(symbol)}: ${esc(e.message)}</div>`; return; }
  if (d.error) { box.innerHTML = `<div class="card down">${esc(d.error)}</div>`; return; }
  state.detail = d;

  const m = d.market, g = d.gate, sig = d.signal, st = d.structure, sw = d.swarm;
  box.innerHTML = `
    <div class="card">
      <div class="bar" style="margin-bottom:8px">
        <div class="brand" style="margin-right:auto">
          <h2>${esc(m.base)}/${esc(m.quote)}</h2>
          <span class="mono">${fmtPrice(m.price)}</span>
          <span class="${dirCls(m.change_24h_pct)}">${dirGlyph(m.change_24h_pct)} ${pct(m.change_24h_pct)}</span>
          ${gateChip(g)} ${verdictChip(sig?.verdict)}
        </div>
        <a href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(d.tradingview)}"
           target="_blank" rel="noopener"><button>Open in TradingView ↗</button></a>
      </div>
      <div id="tvHost"></div>
    </div>
    <div class="grid two">
      <div>
        <div class="card">
          <div class="bigrow" style="margin-bottom:6px"><h3>Price</h3>
            <span class="tiny muted" id="ovNote"></span></div>
          <div id="pxChart"></div><div id="volChart"></div>
        </div>
        <div class="card"><h3>Why the gate reads ${esc(g?.label || '')}</h3>
          <p class="small sec" style="margin:4px 0 10px">${esc(g?.explain || '')}</p>
          <div class="grid half" style="gap:18px">
            <div><h3>Already moving</h3><div id="expTerms"></div>
                 <div class="tiny muted" style="margin-top:4px">expansion ${(g?.expansion ?? 0).toFixed(2)}</div></div>
            <div><h3>Wound tight</h3><div id="cmpTerms"></div>
                 <div class="tiny muted" style="margin-top:4px">compression ${(g?.compression ?? 0).toFixed(2)}</div></div>
          </div>
          <div class="note" style="margin-top:12px">
            Heat <strong>${(g?.blow_score ?? 0).toFixed(2)}</strong> — absolute speed ${(g?.energy ?? 0).toFixed(2)},
            relative signal ${Math.max(g?.expansion ?? 0, g?.compression ?? 0).toFixed(2)}.
            ${d.calibrated
              ? `On this app's own record, readings in the ${esc(d.calibrated.bucket)} band were followed by a big move
                 <strong>${d.calibrated.probability_pct}%</strong> of the time (${d.calibrated.sample} graded).`
              : `Not enough graded predictions yet to say how often this score is followed by a big move.`}
          </div>
        </div>
        <div class="card"><h3>Structure</h3>
          <div class="kv" style="margin-top:6px">
            <span class="k">Trend</span><span class="v">${esc(st?.trend || '—')}</span>
            <span class="k">EMA stack</span><span class="v">${esc(st?.ema_stack || '—')}</span>
            <span class="k">vs 200 EMA</span><span class="v">${esc(st?.price_vs_ema200 || '—')}</span>
            <span class="k">From 21 EMA</span><span class="v">${st?.dist_ema21_atr ?? '—'} ATR</span>
            <span class="k">RSI(14)</span><span class="v">${st?.rsi14 ?? '—'}</span>
            <span class="k">RVOL</span><span class="v">${st?.rvol ?? '—'}</span>
          </div>
          <h3 style="margin-top:12px">Nearest levels</h3>
          <table><tbody>${(st?.levels || []).slice(0, 7).map(l => `
            <tr><td class="small">${esc(l.name)}</td><td class="n small">${fmtPrice(l.price)}</td>
                <td class="n tiny ${dirCls(l.distance_pct)}">${pct(l.distance_pct, 2)}</td></tr>`).join('')}</tbody></table>
        </div>
      </div>
      <div>
        <div class="card"><h3>The plan</h3>${planHtml(sig, m)}</div>
        <div class="card">
          <h3>Swarm ${sw ? `· ${sw.agents_fired} of ${sw.agents_run} fired` : ''}</h3>
          ${sw ? swarmDetailHtml(sw) : '<p class="muted small">No swarm reading.</p>'}
        </div>
        <div class="card"><h3>Confluence ${sig?.confluence ? sig.confluence.score + '/' + sig.confluence.max + ' · ' + esc(sig.confluence.grade) : ''}</h3>
          <table style="margin-top:6px"><tbody>${(sig?.confluence?.rows || []).map(r => `
            <tr><td style="width:18px">${r.point ? '✓' : '·'}</td>
                <td><strong class="small">${esc(r.factor)}</strong>
                    <div class="tiny muted">${esc(r.why)}</div></td></tr>`).join('')}</tbody></table>
        </div>
        <div class="card"><h3>News naming ${esc(m.base)}</h3>
          ${(d.news || []).length ? d.news.map(newsHtml).join('')
            : '<p class="muted small" style="margin-top:6px">Nothing in the current feeds names this asset.</p>'}
        </div>
      </div>
    </div>`;

  const overlays = await buildOverlays(symbol, m.venue, d.candles.length);
  $('#pxChart').appendChild(priceChart(d.candles, overlays));
  $('#volChart').appendChild(volumeChart(d.candles));
  $('#ovNote').textContent = overlays.length
    ? `${overlays.length} indicator${overlays.length > 1 ? 's' : ''} overlaid — change them in Settings`
    : 'no indicators overlaid — add them in Settings';
  $('#expTerms').appendChild(termBars(g?.expansion_terms, 'var(--hot)'));
  $('#cmpTerms').appendChild(termBars(g?.compression_terms, 'var(--accent)'));
  mountTradingView(d.tradingview);
  const jb = $('#detail [data-journal]');
  if (jb) jb.addEventListener('click', () => addToPortfolio(d));
}

const OVERLAY_COLORS = ['var(--hot)', 'var(--warn)', 'var(--up)', 'var(--down)'];

async function buildOverlays(symbol, venue, nCandles) {
  const picks = state.settings.indicators || [];
  const out = [];
  for (let i = 0; i < picks.length && i < 4; i++) {
    const [name, p] = picks[i].split(':');
    const q = new URLSearchParams({ symbol, venue: venue || 'okx', name });
    if (p) q.set(Object.keys(INDICATOR_PARAM[name] || { period: 1 })[0] || 'period', p);
    try {
      const r = await api('/api/indicator?' + q);
      if (r.error) continue;
      const series = r.series_0;
      if (!Array.isArray(series)) continue;
      out.push({ label: name + (p ? ` ${p}` : ''), values: series.slice(-nCandles),
                 color: OVERLAY_COLORS[i % OVERLAY_COLORS.length] });
    } catch {}
  }
  return out;
}
const INDICATOR_PARAM = {};

function swarmDetailHtml(sw) {
  const fams = Object.entries(sw.family_scores || {}).sort((a, b) => b[1] - a[1]);
  return `<p class="small sec" style="margin:4px 0 8px">
      ${sw.families_agreeing} independent famil${sw.families_agreeing === 1 ? 'y' : 'ies'} agree ·
      consensus ${sw.consensus.toFixed(3)} ·
      ${sw.weighted ? 'weighted by measured results' : '<strong>unweighted</strong> — run Research to weight these'}
    </p>
    ${fams.map(([f, v]) => `<div class="term"><span class="sec">${esc(f)}</span>
      <span class="tr"><span class="tf" style="width:${Math.min(100, v * 50).toFixed(0)}%;background:var(--accent)"></span></span>
      <span class="mono tiny sec" style="text-align:right">${v.toFixed(2)}</span></div>`).join('')}
    <table style="margin-top:10px"><tbody>${(sw.signals || []).map(s => `
      <tr><td><strong class="small">${esc(s.strategy)}</strong>
          <div class="tiny muted">${esc(s.reason)}</div></td>
        <td class="n tiny">${s.strength.toFixed(2)}</td>
        <td class="n tiny">${s.weight != null ? '×' + s.weight : '<span class="muted">—</span>'}</td></tr>`).join('')}</tbody></table>`;
}

function planHtml(sig, m) {
  if (!sig || sig.verdict !== 'BUY') {
    return `<p class="small sec" style="margin:6px 0 10px">No plan. What is blocking it:</p>
      ${(sig?.blockers || []).map(b => `<div class="note warn" style="margin-bottom:6px">${esc(b)}</div>`).join('')}
      <p class="tiny muted" style="margin-top:10px">${esc(sig?.direction_note || '')}</p>`;
  }
  return `<div class="kv" style="margin-top:6px">
      <span class="k">Entry</span><span class="v">${fmtPrice(sig.entry)}</span>
      <span class="k">Stop</span><span class="v">${fmtPrice(sig.stop)} <span class="muted">(${sig.stop_pct}%)</span></span>
      <span class="k">Take half at</span><span class="v">${fmtPrice(sig.tp1)}</span>
      <span class="k">Target</span><span class="v">${fmtPrice(sig.target)}</span>
      <span class="k">Net reward</span><span class="v">${sig.net_r_to_target}R</span>
      <span class="k">Risk</span><span class="v">${sig.risk_pct}% = $${sig.risk_amount}</span>
      <span class="k">Size</span><span class="v">${fmtQty(sig.units)} ${esc(m.base)} <span class="muted">($${sig.notional.toLocaleString()})</span></span>
      <span class="k">Cost</span><span class="v">${(sig.confluence.cost_r * 100).toFixed(0)}% of 1R</span>
    </div>
    <p class="tiny sec" style="margin-top:10px">${esc(sig.tp1_note)}.</p>
    <button data-journal class="primary" style="margin-top:10px">Take this in the paper book</button>
    <p class="tiny muted" style="margin-top:10px">${esc(sig.direction_note)}</p>`;
}

function mountTradingView(tvSymbol) {
  const host = $('#tvHost');
  if (!host) return;
  const dark = document.documentElement.dataset.theme === 'dark' ||
    (document.documentElement.dataset.theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
  const id = 'tv_' + Math.random().toString(36).slice(2);
  host.innerHTML = `<div id="${id}" class="tv"></div>
    <p class="tiny muted" id="${id}_cap" style="margin-top:6px">TradingView advanced chart widget, loading.
      The price chart below is computed locally and does not depend on it.</p>`;
  const s = document.createElement('script');
  s.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
  s.async = true;
  s.innerHTML = JSON.stringify({ autosize: true, symbol: tvSymbol, interval: '60',
    timezone: 'Etc/UTC', theme: dark ? 'dark' : 'light', style: '1', locale: 'en',
    hide_side_toolbar: false, allow_symbol_change: true, container_id: id });
  $('#' + id).appendChild(s);
  const collapse = () => {
    const box = $('#' + id);
    if (!box) return;
    const cap = document.getElementById(id + '_cap');
    if (box.querySelector('iframe')) { if (cap) cap.remove(); return; }
    box.classList.add('tv-failed'); box.style.height = 'auto';
    if (cap) cap.remove();
    box.innerHTML = `<div class="note warn">TradingView's widget did not load — this network blocks it.
      Everything below is computed locally from exchange candles and is unaffected.
      <a href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}"
         target="_blank" rel="noopener">Open ${esc(tvSymbol)} on TradingView ↗</a></div>`;
  };
  s.addEventListener('error', collapse);
  setTimeout(collapse, 4500);
}

/* ---------------- swarm tab ---------------- */
function renderSwarm() {
  const wrap = $('#swarmWrap');
  const s = state.scan;
  if (!s) { wrap.innerHTML = '<p class="muted small">Run a scan first.</p>'; return; }
  const sw = s.swarm || {};
  const rows = (s.markets || []).filter(m => m.swarm);
  rows.sort((a, b) => (b.swarm.families_agreeing - a.swarm.families_agreeing) || (b.swarm.consensus - a.swarm.consensus));
  wrap.innerHTML = `
    <div class="grid tiles" style="margin-bottom:12px">
      ${[['Strategies', sw.strategies_loaded || 0, 'loaded and enabled'],
         ['Evaluations', (sw.total_evaluations || 0).toLocaleString(), 'this scan'],
         ['Signals', sw.total_signals || 0, 'strategies that fired'],
         ['Swarm time', (sw.elapsed_s ?? 0) + 's', 'all of it, concurrently'],
         ['Weighting', sw.any_weighted ? 'measured' : 'none yet', sw.any_weighted ? 'from the last research run' : 'run Research to weight votes']]
        .map(([k, v, sub]) => `<div class="tile"><div class="k">${esc(k)}</div>
          <div class="v">${esc(String(v))}</div><div class="s">${esc(sub)}</div></div>`).join('')}
    </div>
    ${!sw.any_weighted ? `<div class="note warn" style="margin-bottom:12px">Votes are currently unweighted:
      no research run exists yet, so every strategy counts the same. Run one on the Research tab and the
      swarm starts giving more say to the strategies that actually held up out of sample.</div>` : ''}
    <div class="tablewrap"><table><thead><tr>
      <th>Market</th><th class="n">Families</th><th class="n">Fired</th><th class="n">Consensus</th>
      <th>Strongest voices</th></tr></thead><tbody>
      ${rows.map(m => `<tr class="row" data-sym="${esc(m.symbol)}" data-venue="${esc(m.venue)}">
        <td><strong>${esc(m.base)}</strong> ${gateChip(m.gate)}</td>
        <td class="n">${m.swarm.families_agreeing}</td>
        <td class="n">${m.swarm.agents_fired}</td>
        <td class="n">${m.swarm.consensus.toFixed(3)}</td>
        <td class="tiny sec">${(m.swarm.signals || []).slice(0, 3).map(x => esc(x.strategy)).join(', ')}</td>
      </tr>`).join('')}
    </tbody></table></div>`;
  $$('#swarmWrap tr.row').forEach(tr => tr.addEventListener('click',
    () => openDetail(tr.dataset.sym, tr.dataset.venue)));
}

async function loadStrategies() {
  try {
    const r = await api('/api/strategies');
    const groups = {};
    r.roster.forEach(s => (groups[s.group] = groups[s.group] || []).push(s));
    $('#stratCount').textContent = `${r.roster.filter(s => s.enabled).length} of ${r.roster.length} enabled`;
    $('#stratWrap').innerHTML = Object.entries(groups).map(([g, list]) => `
      <h3 style="margin-top:12px">${esc(g)} <span class="pill">${list.length}</span></h3>
      ${list.map(s => `<div class="stratrow">
        <input type="checkbox" data-strat="${esc(s.name)}" ${s.enabled ? 'checked' : ''}>
        <div><strong class="small">${esc(s.name)}</strong>
             <div class="tiny muted">${esc(s.description || '')}</div></div>
        <span class="pill">${esc(s.family)}</span>
        <span class="tiny muted">${esc(s.source)}</span>
      </div>`).join('')}`).join('');
    $$('#stratWrap [data-strat]').forEach(cb => cb.addEventListener('change', async () => {
      await post('/api/strategies/toggle', { set: { [cb.dataset.strat]: cb.checked } });
      loadStrategies();
    }));
  } catch (e) { $('#stratWrap').innerHTML = `<p class="down">${esc(e.message)}</p>`; }
}

/* ---------------- research ---------------- */
async function loadResearch() {
  const w = $('#researchWrap');
  try {
    const r = await api('/api/research');
    if (!r.has_run) { w.innerHTML = `<div class="note">${esc(r.note)}</div>`; return; }
    const run = r.run;
    const lb = r.leaderboard || [];
    const controls = lb.filter(e => e.is_control);
    const real = lb.filter(e => !e.is_control);
    w.innerHTML = `
      <div class="grid tiles" style="margin-bottom:12px">
        ${[['Combinations', (run.combinations || 0).toLocaleString(), `${run.strategies} strategies × ${run.markets} markets`],
           ['Trades simulated', (run.trades_simulated || 0).toLocaleString(), `${run.bars_per_market} bars each`],
           ['Beat the control', `${r.beating_control}/${r.judged}`, 'out of sample'],
           ['Run time', (run.elapsed_s || 0) + 's', new Date(run.finished_at).toLocaleString()]]
          .map(([k, v, s]) => `<div class="tile"><div class="k">${esc(k)}</div>
            <div class="v">${esc(String(v))}</div><div class="s">${esc(s)}</div></div>`).join('')}
      </div>
      <div class="note warn" style="margin-bottom:12px">
        The control earns <strong>${(r.control_expectancy ?? 0).toFixed(4)}R</strong> out of sample by buying
        with no analysis at all. Only <strong>${r.beating_control} of ${r.judged}</strong> strategies beat it.
        In a rising market everything long makes money, so the excess column is the one that means something.
      </div>
      <div class="tablewrap"><table><thead><tr>
        <th>Strategy</th><th>Family</th><th class="n">Markets</th><th class="n">Trades</th>
        <th class="n">OOS trades</th><th class="n">Win %</th><th class="n">OOS E</th>
        <th class="n">Excess</th><th class="n">Weighted in</th></tr></thead><tbody>
        ${controls.map(e => rowHtml(e, true)).join('')}
        ${real.map(e => rowHtml(e, false)).join('')}
      </tbody></table></div>`;
  } catch (e) { w.innerHTML = `<p class="down">${esc(e.message)}</p>`; }

  function rowHtml(e, isControl) {
    const x = e.excess_over_control;
    return `<tr${isControl ? ' style="background:var(--surface-2)"' : ''}>
      <td><strong class="small">${esc(e.strategy)}</strong>${isControl ? ' <span class="pill">control</span>' : ''}</td>
      <td class="tiny sec">${esc(e.group || '')}</td>
      <td class="n">${e.markets}</td><td class="n">${e.trades}</td><td class="n">${e.oos_trades}</td>
      <td class="n">${e.win_rate ?? '—'}</td>
      <td class="n">${e.oos_expectancy != null ? e.oos_expectancy.toFixed(4) : '—'}</td>
      <td class="n ${isControl ? 'muted' : x > 0 ? 'up' : x < 0 ? 'down' : ''}">${
        isControl ? 'baseline' : x != null ? (x > 0 ? '+' : '') + x.toFixed(4) : '—'}</td>
      <td class="n">${isControl ? '—' : e.markets_weighted}</td></tr>`;
  }
}

/* ---------------- portfolio ---------------- */
async function loadPortfolio() {
  const w = $('#pfWrap');
  try {
    const name = $('#pfSel').value || 'paper';
    const r = await api('/api/portfolio?name=' + encodeURIComponent(name));
    const sel = $('#pfSel');
    if (sel.options.length !== r.portfolios.length) {
      sel.innerHTML = r.portfolios.map(p =>
        `<option ${p.name === name ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
    }
    const p = r.performance, rd = r.readiness;
    w.innerHTML = `
      <div class="grid tiles" style="margin-bottom:12px">
        ${[['Equity', '$' + p.equity.toLocaleString(), `started at $${p.starting_cash.toLocaleString()}`],
           ['Return', pct(p.return_pct, 2), 'after fees'],
           ['Closed trades', p.closed_count, p.closed_count < 50 ? 'under 50: noise' : 'meaningful sample'],
           ['Expectancy', p.expectancy_r != null ? p.expectancy_r.toFixed(3) + 'R' : '—', 'per trade'],
           ['Max drawdown', pct(p.max_drawdown_pct, 1), 'peak to trough'],
           ['Fees paid', '$' + p.total_fees.toLocaleString(), 'the silent tax']]
          .map(([k, v, s]) => `<div class="tile"><div class="k">${esc(k)}</div>
            <div class="v">${esc(String(v))}</div><div class="s">${esc(s)}</div></div>`).join('')}
      </div>
      <div class="grid two">
        <div><div id="eqChart"></div></div>
        <div>
          <h3>Is this book ready for real money?</h3>
          <div class="note ${rd.ready ? 'good' : 'warn'}" style="margin:8px 0">${esc(rd.verdict)}</div>
          <table><tbody>${rd.checks.map(c => `<tr>
            <td style="width:18px">${c.passed ? '✓' : '✗'}</td>
            <td><strong class="small">${esc(c.check)}</strong>
                <div class="tiny muted">${esc(c.why)}</div></td></tr>`).join('')}</tbody></table>
        </div>
      </div>
      <h3 style="margin-top:14px">Open positions</h3>
      ${p.open_positions.length ? `<div class="tablewrap"><table><thead><tr>
          <th>Market</th><th class="n">Units</th><th class="n">Entry</th><th class="n">Stop</th>
          <th class="n">Target</th><th>Opened</th><th></th></tr></thead><tbody>
          ${p.open_positions.map(o => `<tr><td><strong>${esc(o.symbol)}</strong></td>
            <td class="n">${fmtQty(o.units)}</td><td class="n">${fmtPrice(o.entry)}</td>
            <td class="n">${fmtPrice(o.stop)}</td><td class="n">${fmtPrice(o.target)}</td>
            <td class="tiny muted">${esc((o.opened_at || '').replace('T', ' ').replace('Z', ''))}</td>
            <td><button class="sm" data-close="${o.id}">Close</button></td></tr>`).join('')}
        </tbody></table></div>` : '<p class="muted small">Nothing open.</p>'}
      <h3 style="margin-top:14px">Recent closed</h3>
      ${p.recent.length ? `<div class="tablewrap"><table><thead><tr>
          <th>Market</th><th class="n">Entry</th><th class="n">Exit</th><th>Why</th>
          <th class="n">R</th><th class="n">P&amp;L</th></tr></thead><tbody>
          ${p.recent.slice().reverse().map(t => `<tr><td><strong>${esc(t.symbol)}</strong></td>
            <td class="n">${fmtPrice(t.entry)}</td><td class="n">${fmtPrice(t.exit_price)}</td>
            <td class="tiny sec">${esc(t.exit_reason || '')}</td>
            <td class="n ${t.r_multiple > 0 ? 'up' : t.r_multiple < 0 ? 'down' : ''}">${t.r_multiple != null ? t.r_multiple.toFixed(2) + 'R' : '—'}</td>
            <td class="n ${t.pnl > 0 ? 'up' : t.pnl < 0 ? 'down' : ''}">${t.pnl != null ? '$' + t.pnl.toLocaleString() : '—'}</td></tr>`).join('')}
        </tbody></table></div>` : '<p class="muted small">Nothing closed yet.</p>'}`;
    const eq = $('#eqChart');
    if (eq) eq.appendChild(equityChart(p.equity_curve, p.starting_cash));
    $$('#pfWrap [data-close]').forEach(b => b.addEventListener('click', async () => {
      const px = prompt('Exit price?');
      if (!px) return;
      await post('/api/portfolio/close', { id: Number(b.dataset.close), price: Number(px) });
      loadPortfolio();
    }));
  } catch (e) { w.innerHTML = `<p class="down">${esc(e.message)}</p>`; }
}

async function addToPortfolio(d) {
  const s = d.signal;
  const r = await post('/api/portfolio/open', {
    portfolio: $('#pfSel').value || 'paper', symbol: d.market.symbol, price: s.entry,
    stop: s.stop, target: s.target, grade: s.confluence.grade, gate_label: d.gate.label,
    consensus: d.swarm?.consensus, strategy: (d.swarm?.signals || [])[0]?.strategy,
    notes: `heat ${d.gate.blow_score}` });
  if (r.error) { alert(r.error); return; }
  showTab('portfolio'); loadPortfolio();
}

/* ---------------- alerts ---------------- */
async function loadAlerts(quiet) {
  try {
    const r = await api('/api/alerts');
    const badge = $('#alertBadge');
    if (r.unseen > 0) { badge.hidden = false; badge.textContent = r.unseen; }
    else badge.hidden = true;
    if (quiet) return;
    const auto = await api('/api/automation');
    $('#autoToggle').textContent = auto.enabled ? 'Stop' : 'Start';
    $('#autoToggle').className = auto.enabled ? '' : 'primary';
    if (auto.enabled) {
      $('#autoStatus').innerHTML = `Running every ${Math.round(auto.interval_s / 60)} minutes ·
        ${auto.runs} cycles · ${auto.alerts_fired} alerts fired
        ${auto.last_run ? '· last ' + esc(auto.last_run.replace('T', ' ').replace('Z', '')) : ''}
        ${auto.last_error ? '<span class="down"> · last error: ' + esc(auto.last_error) + '</span>' : ''}`;
    }
    $('#alertsWrap').innerHTML = `
      <h3>Rules</h3>
      <div class="tablewrap"><table><thead><tr><th>On</th><th>Rule</th><th>Conditions</th>
        <th class="n">Cooldown</th><th></th></tr></thead><tbody>
        ${r.rules.map(x => `<tr>
          <td><input type="checkbox" data-rule="${x.id}" ${x.enabled ? 'checked' : ''}></td>
          <td><strong class="small">${esc(x.name)}</strong></td>
          <td class="tiny sec">${esc([x.symbol && 'symbol ' + x.symbol,
              x.min_heat != null && 'heat ≥ ' + x.min_heat,
              x.gate_label && 'state ' + x.gate_label,
              x.verdict && 'plan ' + x.verdict,
              x.min_consensus != null && 'consensus ≥ ' + x.min_consensus,
              x.min_families != null && '≥ ' + x.min_families + ' families',
              x.max_cost_r != null && 'cost ≤ ' + Math.round(x.max_cost_r * 100) + '%'
            ].filter(Boolean).join(' · '))}</td>
          <td class="n tiny">${x.cooldown_min}m</td>
          <td><button class="sm ghost" data-delrule="${x.id}">Delete</button></td></tr>`).join('')}
      </tbody></table></div>
      <div class="bigrow" style="margin:10px 0">
        <input id="newRuleName" type="text" placeholder="New rule name" style="width:180px">
        <div class="ctl"><label class="lbl">heat ≥</label>
          <input id="newRuleHeat" type="number" min="0" max="1" step="0.05" value="0.7" style="width:70px"></div>
        <div class="ctl"><label class="lbl">state</label>
          <select id="newRuleState"><option value="">any</option><option>LOUD</option>
            <option>COILED</option><option>QUIET</option></select></div>
        <div class="ctl"><label class="lbl">plan</label>
          <select id="newRuleVerdict"><option value="">any</option><option>BUY</option></select></div>
        <button id="addRule" class="sm primary">Add rule</button>
      </div>
      <h3 style="margin-top:14px">Recent alerts</h3>
      ${r.alerts.length ? r.alerts.map(a => `<div class="news-item">
          <strong class="small">${esc(a.symbol)}</strong> ${gateChip({ label: a.gate_label })}
          <span class="tiny muted">${esc(a.rule_name)} · ${esc((a.fired_at || '').replace('T', ' ').replace('Z', ''))}</span>
          <div class="tiny sec">${esc(a.detail || '')}</div>
        </div>`).join('') : '<p class="muted small">Nothing has fired yet.</p>'}`;
    $$('#alertsWrap [data-rule]').forEach(cb => cb.addEventListener('change',
      () => post('/api/alerts/rule', { id: Number(cb.dataset.rule), enabled: cb.checked })));
    $$('#alertsWrap [data-delrule]').forEach(b => b.addEventListener('click', async () => {
      await post('/api/alerts/rule', { delete_id: Number(b.dataset.delrule) }); loadAlerts();
    }));
    $('#addRule')?.addEventListener('click', async () => {
      const name = $('#newRuleName').value.trim();
      if (!name) return;
      await post('/api/alerts/rule', { name, min_heat: Number($('#newRuleHeat').value) || null,
        gate_label: $('#newRuleState').value || null, verdict: $('#newRuleVerdict').value || null,
        cooldown_min: 60 });
      loadAlerts();
    });
    post('/api/alerts/seen', {});
  } catch (e) { if (!quiet) $('#alertsWrap').innerHTML = `<p class="down">${esc(e.message)}</p>`; }
}

/* ---------------- news + learning ---------------- */
const newsHtml = n => `<div class="news-item">
  <a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>
  ${(n.hot || []).map(h => `<span class="hot">${esc(h.trim())}</span>`).join('')}
  <div class="tiny muted">${esc(n.source)}${n.age_minutes != null ? ` · ${n.age_minutes} min ago` : ''}</div></div>`;

async function loadNews() {
  const w = $('#newsWrap');
  try {
    const n = await api('/api/news');
    w.innerHTML = `<p class="tiny muted" style="margin-bottom:8px">Sources live: ${esc(n.sources_ok.join(', ') || 'none')}
      ${n.sources_dead.length ? ` · not responding: ${esc(n.sources_dead.join(', '))}` : ''}</p>`
      + n.items.map(newsHtml).join('');
  } catch (e) { w.innerHTML = `<p class="down">${esc(e.message)}</p>`; }
}

async function loadLearning() {
  const w = $('#learnWrap');
  try {
    const L = await api('/api/learning');
    const c = L.counts, cal = L.calibration;
    let html = `<div class="grid tiles" style="margin-bottom:14px">
      ${[['Predictions made', c.predictions_total, 'written before the outcome'],
         ['Graded', c.resolved, `after ${cal.horizon_hours || 12}h`],
         ['Awaiting horizon', c.pending, 'not yet gradeable'],
         ['Scans run', c.scans, '']]
        .map(([k, v, s]) => `<div class="tile"><div class="k">${esc(k)}</div>
          <div class="v">${esc(String(v))}</div><div class="s">${esc(s)}</div></div>`).join('')}</div>`;
    if (!cal.samples) { w.innerHTML = html + `<div class="note">${esc(cal.note)}</div>`; return; }
    html += `<div class="grid two"><div><h3>Is the heat score honest?</h3>
        <div id="calChart" style="margin-top:8px"></div></div>
      <div><h3>By state</h3>
        <table style="margin-top:8px"><thead><tr><th>State</th><th class="n">n</th>
          <th class="n">Big move followed</th><th class="n">Median range</th></tr></thead><tbody>
          ${Object.entries(cal.by_label).map(([k, v]) => `<tr><td>${gateChip({ label: k })}</td>
            <td class="n">${v.n}</td><td class="n">${v.big_move_rate}%</td>
            <td class="n">${v.median_realized_range_pct}%</td></tr>`).join('')}
        </tbody></table>
        <h3 style="margin-top:16px">The direction reality check</h3>
        <div class="kv" style="margin-top:6px">
          <span class="k">All predictions finished up</span><span class="v">${cal.direction_up_rate ?? '—'}%</span>
          <span class="k">BUY signals finished up</span><span class="v">${cal.buy_signal_up_rate ?? '—'}%</span></div>
        <div class="note warn" style="margin-top:10px">${esc(cal.direction_note)}</div>
      </div></div>`;
    if (!cal.ready) html += `<div class="note" style="margin-top:12px">Only ${cal.samples} graded so far;
      calibrated probabilities switch on at ${cal.min_samples}.</div>`;
    w.innerHTML = html;
    const host = $('#calChart');
    if (host) host.appendChild(calibrationChart(cal.buckets));
  } catch (e) { w.innerHTML = `<p class="down">${esc(e.message)}</p>`; }
}

/* ---------------- settings drawer ---------------- */
function buildSettingsUI(health) {
  const s = state.settings;
  $('#setTheme').value = s.theme || 'auto';
  $('#setDensity').value = s.density || 'normal';
  $('#setFont').value = s.fontSize || 14;
  $('#setFontVal').textContent = (s.fontSize || 14) + 'px';
  $('#setSpark').checked = s.sparklines !== false;
  $('#setStopAtr').value = s.stopAtr ?? 4;
  $('#setTargetR').value = s.targetR ?? 2;
  $$('[data-panel-toggle]').forEach(cb => { cb.checked = (s.panels || {})[cb.dataset.panelToggle] !== false; });

  $('#accentSwatches').innerHTML = ['blue', 'violet', 'aqua', 'magenta'].map(a =>
    `<button class="swatch" data-accent="${a}" aria-pressed="${(s.accent || 'blue') === a}"
       title="${a}" style="background:${{ blue: '#2a78d6', violet: '#4a3aa7', aqua: '#1baf7a', magenta: '#e87ba4' }[a]}"></button>`).join('');
  $$('#accentSwatches .swatch').forEach(b => b.addEventListener('click', () => {
    saveSettings({ accent: b.dataset.accent }); buildSettingsUI(health);
  }));

  const chosen = s.columns || DEFAULTS.columns;
  $('#colList').innerHTML = [...chosen, ...Object.keys(COLUMNS).filter(k => !chosen.includes(k))]
    .map((k, i) => `<label><input type="checkbox" data-col-pick="${k}" ${chosen.includes(k) ? 'checked' : ''}>
      <span style="flex:1">${esc(COLUMNS[k].label)}</span>
      <button class="sm ghost" data-col-up="${k}">↑</button>
      <button class="sm ghost" data-col-down="${k}">↓</button></label>`).join('');
  $$('#colList [data-col-pick]').forEach(cb => cb.addEventListener('change', () => {
    const k = cb.dataset.colPick;
    let cols = [...(state.settings.columns || DEFAULTS.columns)];
    if (cb.checked && !cols.includes(k)) cols.push(k);
    if (!cb.checked) cols = cols.filter(c => c !== k);
    saveSettings({ columns: cols }); renderMarkets(); buildSettingsUI(health);
  }));
  const move = (k, delta) => {
    const cols = [...(state.settings.columns || DEFAULTS.columns)];
    const i = cols.indexOf(k);
    if (i < 0) return;
    const j = i + delta;
    if (j < 0 || j >= cols.length) return;
    [cols[i], cols[j]] = [cols[j], cols[i]];
    saveSettings({ columns: cols }); renderMarkets(); buildSettingsUI(health);
  };
  $$('#colList [data-col-up]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); move(b.dataset.colUp, -1); }));
  $$('#colList [data-col-down]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); move(b.dataset.colDown, 1); }));

  api('/api/indicators').then(r => {
    const picked = state.settings.indicators || [];
    $('#indList').innerHTML = r.catalog.filter(i => !i.scalar).map(i => {
      const key = i.name + (i.params.period ? ':' + i.params.period : '');
      return `<label><input type="checkbox" data-ind="${esc(key)}" ${picked.includes(key) ? 'checked' : ''}>
        <span style="flex:1">${esc(i.name)}</span><span class="pill">${esc(i.group)}</span></label>`;
    }).join('');
    $$('#indList [data-ind]').forEach(cb => cb.addEventListener('change', () => {
      let picks = [...(state.settings.indicators || [])];
      const k = cb.dataset.ind;
      if (cb.checked && !picks.includes(k)) picks.push(k);
      if (!cb.checked) picks = picks.filter(p => p !== k);
      if (picks.length > 4) { picks = picks.slice(-4); }
      saveSettings({ indicators: picks });
      if (state.detail) openDetail(state.detail.market.symbol, state.detail.market.venue);
    }));
  }).catch(() => {});
}

function refreshViewSelect() {
  const views = state.settings.views || {};
  $('#viewSel').innerHTML = '<option value="">— saved views —</option>'
    + Object.keys(views).map(v => `<option>${esc(v)}</option>`).join('');
}

/* ---------------- tabs & boot ---------------- */
function showTab(name) {
  $$('nav button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  $$('.panel').forEach(p => p.classList.toggle('on', p.id === 'panel-' + name));
  if (name === 'news' && !$('#newsWrap').dataset.loaded) { $('#newsWrap').dataset.loaded = '1'; loadNews(); }
  if (name === 'learning') loadLearning();
  if (name === 'swarm') { renderSwarm(); loadStrategies(); }
  if (name === 'research') loadResearch();
  if (name === 'portfolio') loadPortfolio();
  if (name === 'alerts') loadAlerts(false);
}

function syncFilterUI() {
  const f = state.settings.filters || {};
  $('#search').value = f.search || '';
  $('#fHeat').value = f.minHeat || 0;
  $('#fHeatVal').textContent = (f.minHeat || 0).toFixed(2);
  $('#fState').value = f.state || '';
  $('#fVerdict').value = f.verdict || '';
  $('#fVol').value = String(f.minVol || 0);
}

async function boot() {
  try {
    const local = JSON.parse(localStorage.getItem('jarvus-settings') || '{}');
    state.settings = { ...DEFAULTS, ...local };
  } catch { state.settings = { ...DEFAULTS }; }
  try {
    const server = await api('/api/settings');
    if (server && Object.keys(server).length) state.settings = { ...state.settings, ...server };
  } catch {}
  applySettings();

  $$('nav button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  $('#refresh').addEventListener('click', () => loadScan(true));
  $('#openSettings').addEventListener('click', () => { $('#drawer').classList.add('on'); $('#scrim').classList.add('on'); });
  const closeDrawer = () => { $('#drawer').classList.remove('on'); $('#scrim').classList.remove('on'); };
  $('#closeSettings').addEventListener('click', closeDrawer);
  $('#scrim').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

  $('#setTheme').addEventListener('change', e => { saveSettings({ theme: e.target.value });
    if (state.detail) mountTradingView(state.detail.tradingview); });
  $('#setDensity').addEventListener('change', e => saveSettings({ density: e.target.value }));
  $('#setFont').addEventListener('input', e => {
    $('#setFontVal').textContent = e.target.value + 'px';
    saveSettings({ fontSize: Number(e.target.value) });
  });
  $('#setSpark').addEventListener('change', e => { saveSettings({ sparklines: e.target.checked }); renderMarkets(); });
  $$('[data-panel-toggle]').forEach(cb => cb.addEventListener('change', () => {
    const panels = { ...(state.settings.panels || {}) };
    panels[cb.dataset.panelToggle] = cb.checked;
    saveSettings({ panels });
  }));
  $('#setStopAtr').addEventListener('change', e => saveSettings({ stopAtr: Number(e.target.value) }));
  $('#setTargetR').addEventListener('change', e => saveSettings({ targetR: Number(e.target.value) }));
  $('#resetAll').addEventListener('click', async () => {
    state.settings = JSON.parse(JSON.stringify(DEFAULTS));
    await saveSettings({}); buildSettingsUI(state.health); syncFilterUI(); renderMarkets();
  });

  const setFilter = patch => {
    const filters = { ...(state.settings.filters || {}), ...patch };
    saveSettings({ filters }); renderMarkets();
  };
  $('#search').addEventListener('input', e => setFilter({ search: e.target.value }));
  $('#fHeat').addEventListener('input', e => {
    $('#fHeatVal').textContent = Number(e.target.value).toFixed(2);
    setFilter({ minHeat: Number(e.target.value) });
  });
  $('#fState').addEventListener('change', e => setFilter({ state: e.target.value }));
  $('#fVerdict').addEventListener('change', e => setFilter({ verdict: e.target.value }));
  $('#fVol').addEventListener('change', e => setFilter({ minVol: Number(e.target.value) }));
  $('#resetFilters').addEventListener('click', () => { setFilter(DEFAULTS.filters); syncFilterUI(); });

  $('#saveView').addEventListener('click', () => {
    const name = prompt('Name this view');
    if (!name) return;
    const views = { ...(state.settings.views || {}) };
    views[name] = { filters: state.settings.filters, columns: state.settings.columns, sort: state.sort };
    saveSettings({ views }); refreshViewSelect(); $('#viewSel').value = name;
  });
  $('#delView').addEventListener('click', () => {
    const name = $('#viewSel').value;
    if (!name) return;
    const views = { ...(state.settings.views || {}) };
    delete views[name];
    saveSettings({ views }); refreshViewSelect();
  });
  $('#viewSel').addEventListener('change', e => {
    const v = (state.settings.views || {})[e.target.value];
    if (!v) return;
    state.sort = v.sort || state.sort;
    saveSettings({ filters: v.filters, columns: v.columns });
    syncFilterUI(); renderMarkets(); buildSettingsUI(state.health);
  });

  $('#stratAll').addEventListener('click', async () => {
    const r = await api('/api/strategies');
    await post('/api/strategies/toggle', { set: Object.fromEntries(r.roster.map(s => [s.name, true])) });
    loadStrategies();
  });
  $('#stratNone').addEventListener('click', async () => {
    const r = await api('/api/strategies');
    await post('/api/strategies/toggle', { set: Object.fromEntries(r.roster.map(s => [s.name, false])) });
    loadStrategies();
  });

  $('#runResearch').addEventListener('click', async e => {
    e.target.disabled = true; e.target.textContent = 'running…';
    await post('/api/research/run', { bars: Number($('#rBars').value), markets: Number($('#rMarkets').value) });
    $('#researchWrap').innerHTML = `<div class="note">Research started. It backtests every strategy on
      every market over deep history, so it takes a few minutes. This tab updates when it lands —
      press Reload, or just come back.</div>
      <button id="reloadResearch" class="sm" style="margin-top:8px">Reload</button>`;
    $('#reloadResearch')?.addEventListener('click', loadResearch);
    setTimeout(() => { e.target.disabled = false; e.target.textContent = 'Run research'; }, 4000);
  });

  $('#autoToggle').addEventListener('click', async e => {
    const cur = await api('/api/automation');
    const r = await post('/api/automation', { enabled: !cur.enabled, interval_s: Number($('#autoInt').value) });
    e.target.textContent = r.enabled ? 'Stop' : 'Start';
    e.target.className = r.enabled ? '' : 'primary';
    loadAlerts(false);
  });
  $('#newPf').addEventListener('click', async () => {
    const name = prompt('Name the new book');
    if (!name) return;
    const cash = Number(prompt('Starting cash', '10000') || 10000);
    await post('/api/portfolio/create', { name, starting_cash: cash });
    loadPortfolio();
  });
  $('#pfSel').addEventListener('change', loadPortfolio);

  $('#resolveBtn').addEventListener('click', async e => {
    e.target.disabled = true; e.target.textContent = 'grading…';
    try { const r = await post('/api/resolve', { limit: 200 });
      e.target.textContent = `graded ${r.graded}, ${r.failed} unavailable`; } catch { e.target.textContent = 'failed'; }
    setTimeout(() => { e.target.disabled = false; e.target.textContent = 'Grade what is due'; loadLearning(); }, 900);
  });
  $('#reloadLearn').addEventListener('click', loadLearning);
  [$('#feeTier'), $('#deepN'), $('#account')].forEach(i => i.addEventListener('change', () => loadScan(true)));

  try {
    const h = await api('/api/health');
    state.health = h;
    $('#feeTier').innerHTML = h.fee_tiers.map(t =>
      `<option ${t === h.default_fee_tier ? 'selected' : ''}>${esc(t)}</option>`).join('');
    $('#deepN').value = String(h.deep_n);
  } catch { $('#feeTier').innerHTML = '<option>Kraken Pro taker</option>'; }

  buildSettingsUI(state.health);
  refreshViewSelect();
  syncFilterUI();
  loadScan(false);
  setInterval(() => loadAlerts(true), 60000);
}
boot();
