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
    await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Jarvus': '1' },
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

function sparkline(values, w = 74, h = 22, minHalfSpan = 0, center = null) {
  const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, class: 'spark', 'aria-hidden': 'true' });
  const v = (values || []).filter(x => isFinite(x));
  if (v.length < 2) return svg;
  let lo = Math.min(...v), hi = Math.max(...v);
  if (minHalfSpan && center != null) {
    lo = Math.min(lo, center - minHalfSpan); hi = Math.max(hi, center + minHalfSpan);
  }
  const span = (hi - lo) || 1;
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
  // hover: a crosshair that snaps to the nearest closed trade, so nobody has to aim at a 2px line
  const cross = el('line', { y1: m.t, y2: H - m.b, stroke: 'var(--text-muted)', 'stroke-width': 1, opacity: 0 });
  const dot = el('circle', { r: 4, fill: 'var(--accent)', stroke: 'var(--surface-1)', 'stroke-width': 2, opacity: 0 });
  const hit = el('rect', { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: 'transparent' });
  svg.append(cross, dot, hit);
  hit.addEventListener('mousemove', ev => {
    const box = svg.getBoundingClientRect();
    const fx = (ev.clientX - box.left) / box.width * W;
    const i = Math.max(0, Math.min(curve.length - 1, Math.round((fx - m.l) / (W - m.l - m.r) * (curve.length - 1))));
    const p = curve[i];
    cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('opacity', 1);
    dot.setAttribute('cx', X(i)); dot.setAttribute('cy', Y(p.equity)); dot.setAttribute('opacity', 1);
    const chg = p.equity - startCash;
    showTip(`<div class="t">$${esc(p.equity.toLocaleString(undefined, { maximumFractionDigits: 2 }))}</div>
      <div class="r"><span>vs start</span><span>${chg >= 0 ? '+' : '-'}$${esc(Math.abs(chg).toLocaleString(undefined, { maximumFractionDigits: 2 }))}</span></div>
      <div class="r"><span>after trade</span><span>${i + 1} of ${curve.length}</span></div>
      <div class="r"><span>closed</span><span>${esc((p.t || '').replace('T', ' ').replace('Z', ' UTC'))}</span></div>`, ev);
  });
  hit.addEventListener('mouseleave', () => { hideTip(); cross.setAttribute('opacity', 0); dot.setAttribute('opacity', 0); });
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
  headers: { 'Content-Type': 'application/json', 'X-Jarvus': '1' }, body: JSON.stringify(body || {}) });

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
    const r = await api('/api/research?asset=' + ($('#rAsset').value || 'crypto'));
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

/* ---------------- bots ---------------- */
const money = (v, d = 2) => v == null || !isFinite(v) ? '—'
  : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const signedMoney = v => v == null || !isFinite(v) ? '—' : `${v >= 0 ? '+' : '-'}$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const rFmt = v => v == null || !isFinite(v) ? '—' : Math.abs(v) < 0.005 ? '0.00R' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}R`;
const localTime = iso => { if (!iso) return ''; const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); };
const KIND_LABEL = { enter: 'bought', exit: 'sold', manage: 'managed', cycle: 'scan', learn: 'learned',
  research: 'research', system: 'system', error: 'problem' };

function botSpark(b) {
  const vals = [b.starting_cash, ...(b.equity_curve || []).map(p => p.equity)];
  if (b.open || vals.length < 2) vals.push(b.equity);
  // The scale never shrinks below +/-2% of the starting money, so a 0.1% wobble is drawn
  // as the wobble it is instead of a cliff.
  const svg = sparkline(vals, 280, 34, b.starting_cash * 0.02, b.starting_cash);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${b.name} equity, ${money(b.starting_cash, 0)} to ${money(b.equity, 0)}`);
  return svg;
}

async function loadBots() {
  try {
    const s = await api('/api/bots');
    if (s.error) { $('#botsState').textContent = s.error; return; }
    renderBots(s);
  } catch (e) { $('#botsState').textContent = 'Could not reach the app: ' + e.message; }
}

function renderBots(s) {
  state.bots = s;                           // every render is the latest truth, whoever fetched it
  const t = s.totals;
  $('#botsBadge').hidden = !s.running;
  $('#botsEquity').textContent = money(t.equity);
  const pnl = $('#botsPnl');
  pnl.className = 'small ' + (t.pnl > 0 ? 'up' : t.pnl < 0 ? 'down' : 'muted');
  pnl.textContent = `${signedMoney(t.pnl)} (${pct(t.return_pct, 2)}) since the start, from ${money(t.starting, 0)}`;

  const run = $('#runBots');
  run.disabled = false;
  run.textContent = s.running ? 'Stop bots' : 'Run bots';
  run.classList.toggle('stop', s.running);
  let st;
  if (!s.running) st = t.open_positions
    ? `Stopped. Not opening new trades; still managing ${t.open_positions} open trade${t.open_positions > 1 ? 's' : ''} to their exits.`
    : 'Stopped. Press Run bots and they take it from here.';
  else if (s.cycle_busy) st = 'Running. Scanning every market and backtesting setups now…';
  else if (s.next_cycle_in_s != null) st = `Running. Next scan in ${Math.floor(s.next_cycle_in_s / 60)}:${String(s.next_cycle_in_s % 60).padStart(2, '0')}.`
    + (s.last_cycle_at ? ` Last scan ${localTime(s.last_cycle_at)}.` : '');
  else st = 'Running.';
  if (s.last_error) st += ` Last problem: ${s.last_error}`;
  $('#botsState').textContent = st;

  $('#botsTiles').innerHTML = [
    ['Open trades', t.open_positions, `across ${s.bots.filter(b => b.enabled).length} bots`],
    ['Closed trades', t.closed_count, t.closed_count < 50 ? 'under 50: too few to judge' : 'enough to start judging'],
    ['Win rate', t.win_rate != null ? t.win_rate.toFixed(1) + '%' : '—', 'of closed trades'],
    ['Average trade', rFmt(t.expectancy_r), 'after fees, in R'],
    ['Fees paid', money(t.total_fees), 'the silent tax'],
    ['Backtests run', (s.verifier.backtests_run || 0).toLocaleString(), 'since the app started'],
  ].map(([k, v, sub]) => `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${esc(String(v))}</div>
      <div class="s">${esc(sub)}</div></div>`).join('');

  const eqKey = `${t.starting}|${(t.equity_curve || []).length}|${(t.equity_curve || []).slice(-1)[0]?.equity}`;
  if (state.botsEqKey !== eqKey) {          // redraw only when a trade closes, not under the pointer
    state.botsEqKey = eqKey;
    const eq = $('#botsEq'); eq.innerHTML = '';
    eq.appendChild(equityChart(t.equity_curve, t.starting));
  }
  $('#botsEqNote').textContent = t.max_drawdown_pct ? `worst drop so far ${t.max_drawdown_pct.toFixed(1)}%` : '';

  // bot cards
  const cards = $('#botCards'); cards.innerHTML = '';
  s.bots.forEach(b => {
    const d = document.createElement('div');
    d.className = 'bot' + (b.enabled ? '' : ' off');
    d.innerHTML = `
      <div class="top"><span class="name"></span>
        <span class="chip ${b.enabled && s.running ? 'buy' : ''}"><span class="sw"></span>${b.enabled ? (s.running ? 'running' : 'ready') : 'off'}</span>
        <label class="toggle"><input type="checkbox" ${b.enabled ? 'checked' : ''} data-bot="${esc(b.key)}"> on</label></div>
      <div class="doing"></div>
      <div class="nums">
        <div><div class="k">Money</div><div class="v">${esc(money(b.equity, 0))}</div></div>
        <div><div class="k">Return</div><div class="v ${b.return_pct > 0 ? 'up' : b.return_pct < 0 ? 'down' : ''}">${esc(pct(b.return_pct, 1))}</div></div>
        <div><div class="k">Open</div><div class="v">${b.open}</div></div>
        <div><div class="k">Trades</div><div class="v">${b.closed_count}</div></div>
        <div><div class="k">Win rate</div><div class="v">${b.win_rate != null ? b.win_rate.toFixed(0) + '%' : '—'}</div></div>
        <div><div class="k">Avg trade</div><div class="v">${esc(rFmt(b.expectancy_r))}</div></div>
      </div>
      <div class="sparkbox"></div>
      <div class="play"></div>`;
    $('.name', d).textContent = b.name;
    $('.doing', d).textContent = b.status + (b.risk_mult < 1 ? ` Risk cut to ${Math.round(b.risk_mult * 100)}% after recent losses.` : '');
    $('.play', d).textContent = b.playbook;
    $('.sparkbox', d).appendChild(botSpark(b));
    cards.appendChild(d);
  });
  $$('#botCards [data-bot]').forEach(cb => cb.addEventListener('change', async () => {
    renderBots(await post('/api/bots/bot', { key: cb.dataset.bot, enabled: cb.checked }));
  }));

  // open positions
  const pw = $('#botsPositions');
  if (!s.positions.length) {
    pw.innerHTML = `<p class="muted small">${s.running ? 'No open trades. The bots only buy when a setup passes its backtest, so quiet stretches are normal.' : 'No open trades.'}</p>`;
  } else {
    pw.innerHTML = `<div class="tablewrap"><table><thead><tr><th>Bot</th><th>Coin</th><th class="n">Bought</th>
      <th class="n">Now</th><th class="n">P&amp;L</th><th class="n">R</th><th class="n">Stop</th><th class="n">Target</th>
      <th class="n">Held</th></tr></thead><tbody>${s.positions.map(p => `<tr class="row" data-why="${p.id}">
        <td class="small">${esc(p.bot)}</td><td><strong>${esc(p.base)}</strong></td>
        <td class="n">${fmtPrice(p.entry)}</td><td class="n">${fmtPrice(p.last)}</td>
        <td class="n ${p.pnl > 0 ? 'up' : p.pnl < 0 ? 'down' : ''}">${esc(signedMoney(p.pnl))}</td>
        <td class="n">${esc(rFmt(p.r_now))}</td><td class="n">${fmtPrice(p.stop)}</td>
        <td class="n">${fmtPrice(p.target)}</td><td class="n">${p.age_h < 48 ? p.age_h.toFixed(0) + 'h' : (p.age_h / 24).toFixed(1) + 'd'}</td>
      </tr>`).join('')}</tbody></table></div>
      <p class="tiny muted" style="margin:6px 0 0">Hover a row for why the bot bought it. P&amp;L includes the fee already paid.</p>`;
    const byId = Object.fromEntries(s.positions.map(p => [String(p.id), p]));
    $$('#botsPositions tr[data-why]').forEach(tr => {
      const p = byId[tr.dataset.why];
      tr.addEventListener('mousemove', ev => showTip(`<div class="t">${esc(p.bot)} · ${esc(p.base)}</div>
        <div style="max-width:340px;white-space:normal">${esc(p.why || '')}</div>`, ev));
      tr.addEventListener('mouseleave', hideTip);
    });
  }

  renderFeed();

  // learning
  const L = s.learning;
  const lw = $('#botsLearn');
  if (!L.trades) {
    lw.innerHTML = `<p class="muted small">Nothing yet. After each closed trade the bots re-score every strategy and
      coin they have traded. A strategy that keeps losing for them is benched, a coin that keeps losing is avoided,
      and a bot on a losing streak cuts its own risk. Learning only ever makes them more careful.</p>`;
  } else {
    const list = (arr, empty) => arr.length ? arr.map(x => `<span class="pill">${esc(x)}</span>`).join(' ') : `<span class="muted small">${empty}</span>`;
    lw.innerHTML = `
      <div class="small" style="margin-bottom:6px">Learned from <strong>${L.trades}</strong> closed trade${L.trades > 1 ? 's' : ''}.</div>
      <div class="small" style="margin:4px 0">Benched strategies: ${list(L.benched, 'none')}</div>
      <div class="small" style="margin:4px 0">Coins avoided: ${list(L.avoid_coins, 'none')}</div>
      <div class="small" style="margin:4px 0 10px">Market states avoided: ${list(L.avoid_states, 'none')}</div>
      <div class="tablewrap"><table><thead><tr><th>Strategy</th><th class="n">Trades</th><th class="n">Win</th>
        <th class="n">Avg</th><th class="n">Trusted as</th></tr></thead><tbody>
        ${L.by_strategy.slice(0, 12).map(x => `<tr><td class="small">${esc(x.name)}</td><td class="n">${x.n}</td>
          <td class="n">${x.win.toFixed(0)}%</td><td class="n">${esc(rFmt(x.mean))}</td><td class="n">${esc(rFmt(x.shrunk))}</td></tr>`).join('')}
      </tbody></table></div>
      <p class="tiny muted" style="margin:6px 0 0">"Trusted as" shrinks each average toward zero by eight imaginary
        break-even trades, so a few lucky results cannot crown a strategy and a few unlucky ones cannot bench it.</p>`;
  }

  // recent closed
  const rw = $('#botsRecent');
  rw.innerHTML = s.recent.length ? `<div class="tablewrap"><table><thead><tr><th>Bot</th><th>Coin</th><th>Why</th>
      <th class="n">R</th><th class="n">P&amp;L</th></tr></thead><tbody>${s.recent.slice(0, 15).map(r => `<tr>
      <td class="small">${esc(r.bot)}</td><td><strong>${esc(r.base)}</strong></td>
      <td class="tiny sec">${esc(r.exit_reason)}</td>
      <td class="n ${r.r_multiple > 0 ? 'up' : r.r_multiple < 0 ? 'down' : ''}">${esc(rFmt(r.r_multiple))}</td>
      <td class="n ${r.pnl > 0 ? 'up' : r.pnl < 0 ? 'down' : ''}">${esc(signedMoney(r.pnl))}</td></tr>`).join('')}
    </tbody></table></div>` : '<p class="muted small">Nothing closed yet.</p>';

  // readiness
  $('#botsReady').innerHTML = `<div class="note ${s.readiness.passed === s.readiness.total ? 'good' : 'warn'}" style="margin-bottom:8px">
      ${s.readiness.passed} of ${s.readiness.total} checks pass.
      ${s.readiness.passed === s.readiness.total ? 'The practice record has met every bar.' : 'Not yet. Every practice trade costs nothing and buys evidence.'}</div>
    <table><tbody>${s.readiness.checks.map(c => `<tr><td style="width:18px">${c.passed ? '✓' : '✗'}</td>
      <td><strong class="small">${esc(c.check)}</strong><div class="tiny muted">${esc(c.why)}</div></td></tr>`).join('')}</tbody></table>`;

  if (!$('#botsSettings').dataset.built) buildBotSettings(s);
}

function renderFeed() {
  const s = state.bots; if (!s) return;
  const f = $('#feedKind').value;
  const rows = s.feed.filter(r => !f || (f === 'trades' ? ['enter', 'exit', 'manage'].includes(r.kind) : r.kind === f));
  const fw = $('#botsFeed');
  const keep = fw.scrollTop;
  fw.innerHTML = rows.length ? '' : '<p class="muted small">Nothing yet. Press Run bots.</p>';
  rows.slice(0, 120).forEach(r => {
    const d = document.createElement('div');
    d.className = 'item';
    d.innerHTML = `<span class="t"></span><span class="kind ${esc(r.kind)}"></span><span class="m"></span>`;
    $('.t', d).textContent = localTime(r.ts);
    $('.kind', d).textContent = KIND_LABEL[r.kind] || r.kind;
    $('.m', d).textContent = r.message;
    fw.appendChild(d);
  });
  fw.scrollTop = keep;
}

const BOT_FIELDS = [
  ['risk_pct', 'Risk per trade (% of that bot\'s money)', 0.05, 3, 0.05, 'What one losing trade costs. 1% means a bot with $1,429 loses about $14 if the stop is hit.'],
  ['max_positions', 'Most open trades per bot', 1, 8, 1, ''],
  ['max_hold_h', 'Longest a trade is held (hours)', 2, 720, 1, 'Measured: holds of 24h or less lost money after fees; 96h did best.'],
  ['stop_atr', 'Stop distance (× ATR)', 1, 10, 0.5, 'Wide stops survive fees. Tighter stops mean more of each trade goes to the exchange.'],
  ['target_r', 'Profit target (R)', 0.5, 10, 0.5, '2R means the target is twice as far as the stop.'],
  ['verify_min_edge', 'Backtest bar (R per trade)', -1, 2, 0.05, 'A setup must have made at least this much per trade on that market to be traded. Lower = more trades, less proof.'],
  ['daily_loss_limit_pct', 'Daily loss limit (%)', 0.5, 20, 0.5, 'A bot that loses this much in a day stops opening trades until 00:00 UTC.'],
  ['max_trades_per_day', 'Most new trades per bot per day', 1, 50, 1, ''],
];

function buildBotSettings(s) {
  const box = $('#botsSettings');
  box.dataset.built = '1';
  const shared = { ...s.defaults, ...(s.settings.shared || {}) };
  box.innerHTML = `<div class="setgrid">${BOT_FIELDS.map(([k, label, lo, hi, step, help]) => `
      <label><span>${esc(label)}</span>
        <input type="number" data-set="${k}" min="${lo}" max="${hi}" step="${step}" value="${shared[k]}">
        ${help ? `<span class="h">${esc(help)}</span>` : ''}</label>`).join('')}
      <label class="chk"><span><input type="checkbox" data-flag="trade_crypto" ${shared.trade_crypto !== false ? 'checked' : ''}> Trade crypto</span></label>
      <label class="chk"><span><input type="checkbox" data-flag="trade_stocks" ${shared.trade_stocks !== false ? 'checked' : ''}> Trade US stocks (market hours only)</span></label>
      <label class="chk"><span><input type="checkbox" data-flag="stocks_flat_at_close" ${shared.stocks_flat_at_close ? 'checked' : ''}> Stocks: out by the close (true day trade)</span>
        <span class="h">Measured break-even at best on 30 stocks; holding up to 4 days did better. Off by default.</span></label>
      <label><span>Scan every (minutes)</span>
        <input type="number" id="setScanMin" min="2" max="60" step="1" value="${Math.round(s.settings.scan_interval_s / 60)}">
        <span class="h">Setups are built on hourly candles, so faster than 5 minutes adds load, not trades.</span></label>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
      <button id="saveBotSet" class="primary">Save settings</button>
      <button id="defaultBotSet">Back to measured defaults</button>
      <span style="margin-left:auto"></span>
      <label class="small sec" style="display:flex;align-items:center;gap:6px">Practice money
        <input type="number" id="setPractice" min="100" step="100" value="${s.settings.practice_money}" style="width:110px"></label>
      <button id="resetBots" class="ghost">Reset practice account</button>
    </div>
    <p class="tiny muted" style="margin:8px 0 0">Every setting is clamped to a safe range, so a typo cannot bet the account.
      Changes apply to new trades; open trades keep the rules they were opened with.</p>`;
  $('#saveBotSet').addEventListener('click', async () => {
    const shared = {};
    $$('#botsSettings [data-set]').forEach(i => { if (i.value !== '') shared[i.dataset.set] = Number(i.value); });
    $$('#botsSettings [data-flag]').forEach(i => { shared[i.dataset.flag] = i.checked; });
    const r = await post('/api/bots/settings', { shared, scan_interval_s: Number($('#setScanMin').value) * 60 });
    box.dataset.built = ''; renderBots(r);
  });
  $('#defaultBotSet').addEventListener('click', async () => {
    const r = await post('/api/bots/settings', { shared: { ...s.defaults }, scan_interval_s: 300 });
    box.dataset.built = ''; renderBots(r);
  });
  $('#resetBots').addEventListener('click', async () => {
    const amt = Number($('#setPractice').value);
    if (!confirm(`Close every open trade and restart all seven bots with ${money(amt, 0)} of practice money? The trade history is wiped.`)) return;
    const r = await post('/api/bots/reset', { practice_money: amt });
    if (r.error) { alert(r.error); return; }
    box.dataset.built = ''; renderBots(r);
  });
}

/* ---------------- the Brain ---------------- */
const MODEL_TITLE = { crypto: 'Crypto', stock: 'Stocks, held up to 4 days', stock_dt: 'Stocks, day trade (out by the close)' };
const TEST_ROWS = [
  ['all_candidates', 'Every moment any strategy fired'],
  ['bots_rule', "The bots' backtest rule"],
  ['brain_positive', 'The Brain predicts a profit'],
  ['brain_top10pct', "The Brain's top 10% of picks"],
  ['rule_and_brain', 'Backtest rule and the Brain agree'],
  ['rule_minus_worst', "Backtest rule, minus the Brain's vetoes"],
];

function decileChart(vals) {
  const wrap = document.createElement('figure');
  const v = (vals || []).map(x => (x == null ? 0 : x));
  if (!v.length) { wrap.innerHTML = '<p class="muted small">Not trained yet.</p>'; return wrap; }
  const W = 460, H = 170, m = { t: 12, r: 8, b: 22, l: 40 };
  const hi = Math.max(0.05, ...v), lo = Math.min(-0.05, ...v);
  const Y = x => m.t + (hi - x) / (hi - lo) * (H - m.t - m.b);
  const bw = (W - m.l - m.r) / v.length;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Average result by prediction decile' });
  const g = el('g', { class: 'axis' });
  [hi, 0, lo].forEach(t => {
    g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: 'grid-line' }));
    const tx = el('text', { x: m.l - 6, y: Y(t) + 3, 'text-anchor': 'end' }); tx.textContent = (t >= 0 ? '+' : '') + t.toFixed(2);
    g.appendChild(tx);
  });
  svg.appendChild(g);
  v.forEach((x, i) => {
    const y0 = Y(0), y1 = Y(x);
    const r = el('rect', { x: m.l + i * bw + 2, width: bw - 4, y: Math.min(y0, y1), height: Math.max(1, Math.abs(y1 - y0)),
      rx: 3, fill: x >= 0 ? 'var(--up)' : 'var(--down)' });
    r.addEventListener('mousemove', ev => showTip(`<div class="t">${x >= 0 ? '+' : ''}${x.toFixed(3)}R per trade</div>
      <div class="r"><span>group</span><span>${i + 1} of 10 (${i === 0 ? 'most confident' : i === 9 ? 'least confident' : 'by prediction'})</span></div>`, ev));
    r.addEventListener('mouseleave', hideTip);
    svg.appendChild(r);
    const lab = el('text', { x: m.l + i * bw + bw / 2, y: H - 6, 'text-anchor': 'middle', class: 'axis' });
    lab.setAttribute('font-size', '10'); lab.setAttribute('fill', 'var(--text-muted)');
    lab.textContent = i === 0 ? 'best' : i === 9 ? 'worst' : String(i + 1);
    svg.appendChild(lab);
  });
  wrap.appendChild(svg);
  return wrap;
}

function trustBar(w, maxAbs) {
  if (w == null) return '<span class="muted">—</span>';
  const pctW = Math.min(50, Math.abs(w) / (maxAbs || 1) * 50);
  return `<span class="trust"><span class="axis0"></span><span class="fill" style="${w >= 0 ? 'left:50%' : `left:${50 - pctW}%`};width:${pctW}%;background:${w >= 0 ? 'var(--up)' : 'var(--down)'}"></span></span>
    <span class="mono tiny">${w >= 0 ? '+' : ''}${w.toFixed(3)}</span>`;
}

async function loadBrain() {
  let r;
  try { r = await api('/api/brain'); } catch (e) { $('#brainTest').innerHTML = `<p class="down">${esc(e.message)}</p>`; return; }
  state.brainData = r;
  const s = r.summary;
  $('#brainSub').textContent = s.trained
    ? `${s.agents} agents · ${r.vote_count || 0} votes this session · weights ${s.source}`
    : 'not trained yet';
  $('#agentCount').textContent = s.agents;
  $('#brainMode').value = r.mode || 'veto';

  const tw = $('#brainTest');
  const models = Object.entries(s.models || {});
  tw.innerHTML = models.length ? models.map(([k, mdl]) => {
    const t = mdl.test || {};
    return `<h3 style="margin:10px 0 4px">${esc(MODEL_TITLE[k] || k)}</h3>
      <div class="small muted" style="margin-bottom:6px">Trained on ${(mdl.trained_examples || 0).toLocaleString()} moments from
        ${mdl.markets} markets. Correlation between prediction and result on unseen data: <strong>${(t.test_ic >= 0 ? '+' : '') + (t.test_ic ?? 0).toFixed(3)}</strong>
        ${mdl.online_updates ? ` · ${mdl.online_updates} lessons from the bots' own trades since` : ''}</div>
      <div class="note ${mdl.skilled ? 'good' : 'warn'}" style="margin:0 0 8px">${mdl.skilled
        ? `It showed skill here, so it votes: in veto mode it blocks trades it predicts below ${rFmt(mdl.veto_below)}
           (its most pessimistic ${mdl.veto_q}%, a cut-off chosen on a validation period, then confirmed on the unseen test).`
        : 'It showed no reliable skill here on unseen data, so on these markets it abstains: it never blocks or reorders a trade.'}</div>
      <div class="tablewrap"><table><thead><tr><th>How trades were chosen</th><th class="n">Trades</th><th class="n">Win rate</th>
        <th class="n">Average</th></tr></thead><tbody>${TEST_ROWS.map(([key, lbl]) => {
          const x = key === 'rule_minus_worst' ? ((t.rule_minus_worst || {})[String(t.veto_q)] || {}) : (t[key] || {});
          if (key === 'rule_minus_worst' && !t.veto_q) return '';
          return `<tr><td>${esc(lbl)}</td><td class="n">${(x.n || 0).toLocaleString()}</td>
            <td class="n">${x.win != null ? x.win.toFixed(1) + '%' : '—'}</td>
            <td class="n ${x.exp > 0 ? 'up' : x.exp < 0 ? 'down' : ''}">${esc(rFmt(x.exp))}</td></tr>`;
        }).join('')}</tbody></table></div>`;
  }).join('') : '<p class="muted small">No trained model is installed.</p>';

  const dw = $('#brainDeciles'); dw.innerHTML = '';
  models.forEach(([k, mdl]) => {
    const h = document.createElement('div'); h.className = 'small'; h.style.margin = '6px 0 0';
    h.textContent = MODEL_TITLE[k] || k;
    dw.appendChild(h);
    dw.appendChild(decileChart((mdl.test || {}).deciles_best_to_worst));
  });

  const vw = $('#brainVotes');
  vw.innerHTML = (r.votes || []).length ? r.votes.slice(0, 25).map(v => `<div class="vote">
      <span class="chip ${v.vote === 'yes' ? 'buy' : ''}"><span class="sw"></span>${v.vote === 'yes' ? 'yes' : 'no'}</span>
      <strong>${esc(v.symbol)}</strong> <span class="small muted">for ${esc(v.bot)}</span>
      <span class="mono small ${v.pred > 0 ? 'up' : 'down'}">${esc(rFmt(v.pred))}</span>
      <div class="tiny muted">${(v.why || []).map(e => `${esc(e.agent)} ${e.effect >= 0 ? '+' : ''}${e.effect.toFixed(2)}`).join(' · ')}</div>
    </div>`).join('')
    : '<p class="muted small">No votes yet. The Brain votes on every setup that passes a bot\'s backtest, so votes appear once the bots are running and find something.</p>';
  renderAgents();
}

function renderAgents() {
  const r = state.brainData; if (!r) return;
  const q = ($('#agentSearch').value || '').toLowerCase(), kind = $('#agentKind').value;
  let rows = r.agents.filter(a => (!kind || a.kind === kind) && (!q || a.name.toLowerCase().includes(q) || (a.family || '').includes(q)));
  rows.sort((a, b) => Math.abs(b.crypto || 0) + Math.abs(b.stock || 0) - Math.abs(a.crypto || 0) - Math.abs(a.stock || 0));
  const maxAbs = Math.max(1e-6, ...r.agents.map(a => Math.max(Math.abs(a.crypto || 0), Math.abs(a.stock || 0))));
  const total = rows.length;
  const showAll = state.agentsAll || q || kind;
  rows = showAll ? rows : rows.slice(0, 25);
  $('#brainAgents').innerHTML = `<div class="tablewrap"><table><thead><tr><th>Agent</th><th>Kind</th>
      <th>Trust on crypto</th><th>Trust on stocks</th><th class="n">Active (crypto)</th><th class="n">Avg when active</th>
      </tr></thead><tbody>${rows.map(a => {
        const cs = a.crypto_stats || {};
        return `<tr><td><strong class="small">${esc(a.name)}</strong><div class="tiny muted">${esc(a.help || '')}</div></td>
          <td class="tiny sec">${esc(a.family)}</td><td>${trustBar(a.crypto, maxAbs)}</td><td>${trustBar(a.stock, maxAbs)}</td>
          <td class="n">${cs.n != null ? cs.n.toLocaleString() : '—'}</td>
          <td class="n ${cs.mean_r > 0 ? 'up' : cs.mean_r < 0 ? 'down' : ''}">${esc(rFmt(cs.mean_r))}</td></tr>`;
      }).join('')}</tbody></table></div>
      ${total > rows.length ? `<button id="agentsMore" class="sm" style="margin-top:8px">Show all ${total} agents</button>` : ''}`;
  $('#agentsMore')?.addEventListener('click', () => { state.agentsAll = true; renderAgents(); });
}

/* ---------------- learn trading ---------------- */
function pooled(cards, policy, filter) {
  let n = 0, s = 0, w = 0;
  for (const [name, c] of Object.entries(cards || {})) {
    if (name.startsWith('_') || (filter && !filter(name))) continue;
    const x = c[policy]; if (!x || !x.n) continue;
    n += x.n; s += x.exp * x.n; w += x.win * x.n;
  }
  return n ? { n, exp: s / n, win: w / n } : null;
}

function streakOdds(winRate, trades, streak) {
  // probability of at least `streak` losses in a row somewhere in `trades` trades
  const q = 1 - winRate;
  let dp = new Array(streak).fill(0); dp[0] = 1;
  let hit = 0;
  for (let t = 0; t < trades; t++) {
    const nx = new Array(streak).fill(0);
    for (let k = 0; k < streak; k++) {
      nx[0] += dp[k] * winRate;
      if (k + 1 === streak) hit += dp[k] * q; else nx[k + 1] += dp[k] * q;
    }
    dp = nx;
  }
  return hit;
}

function lesson(title, body, open) {
  return `<div class="card lesson"><details ${open ? 'open' : ''}><summary><h2 style="display:inline">${esc(title)}</h2></summary>
    <div class="lbody">${body}</div></details></div>`;
}

function statRow(label, x) {
  return `<tr><td>${esc(label)}</td><td class="n">${x && x.n != null ? x.n.toLocaleString() : '—'}</td>
    <td class="n">${x && x.win != null ? x.win.toFixed(1) + '%' : '—'}</td>
    <td class="n">${x && x.avg_win != null ? '+' + x.avg_win.toFixed(2) + 'R' : '—'}</td>
    <td class="n">${x && x.avg_loss != null ? x.avg_loss.toFixed(2) + 'R' : '—'}</td>
    <td class="n ${x && x.exp > 0 ? 'up' : x && x.exp < 0 ? 'down' : ''}">${x ? esc(rFmt(x.exp)) : '—'}</td></tr>`;
}

function buildLessons(b) {
  const C = (b.assets || {}).crypto || {}, K = (b.assets || {}).stock || {};
  const out = [];
  const wl = (A, t) => (A.win_rate_lesson || {})[t];

  // 1. expectancy
  const c05 = wl(C, '0.5'), c2 = wl(C, '2.0');
  out.push(lesson('1. The only formula that matters', `
    <p>Every trading result in the world comes down to one line:</p>
    <p class="formula">average result per trade = win rate × average win − loss rate × average loss</p>
    <p>Win rate alone tells you nothing. A 90% win rate that wins $1 and loses $20 goes broke; a 35% win rate that wins
      $3 and loses $1 makes money. Professionals talk about <strong>R</strong>: the amount you decided to risk on a trade.
      A trade that hits its stop is −1R; one that makes twice what it risked is +2R. Measuring in R lets you compare any
      strategy on any market, at any account size.</p>
    ${c05 && c2 ? `<p>Measured here on crypto, the same entries with a small target won <strong>${c05.win}%</strong> of the time but
      averaged <strong>${rFmt(c05.exp)}</strong> per trade. With a 2R target they won only ${c2.win}% and averaged ${rFmt(c2.exp)}.
      The entries were identical; only the exit changed the win rate.</p>` : ''}`, true));

  // 2. win rate is a dial
  const tbl = (A) => `<div class="tablewrap"><table><thead><tr><th>Target</th><th class="n">Trades</th><th class="n">Win rate</th>
      <th class="n">Avg win</th><th class="n">Avg loss</th><th class="n">Per trade</th></tr></thead><tbody>
      ${['0.5', '1.0', '2.0', '3.0'].map(t => statRow(`${t}R target, 4 ATR stop`, wl(A, t))).join('')}</tbody></table></div>`;
  out.push(lesson('2. Win rate is a dial you set with your exit, not a skill', `
    <p><strong>Can you have a high win rate and big profits at the same time?</strong> Only by having a real edge,
      and even then the two pull against each other: the exit that raises the win rate shrinks each win. Take every
      trade all 95 strategies found and change only the profit target. Watch the win rate move and the average result
      barely care:</p>
    <h3>Crypto</h3>${tbl(C)}<h3 style="margin-top:10px">US stocks</h3>${tbl(K)}
    <p>A closer target is hit more often, so the win rate climbs, but every win shrinks while every loss stays full size.
      This is why "95% win rate" systems are easy to build and usually lose money: they take tiny profits and hold the
      rare big loss. When someone sells you a win rate, ask for the average win and the average loss.</p>`));

  // 3. where 70% comes from
  const dc = b.daily_classics || {};
  const etf = dc['index ETFs'] || {}, big = dc['large stocks'] || {};
  const dnames = { ibs_reversion: 'IBS under 0.15', double_sevens: 'Double 7s', connors_rsi_dip: 'Connors RSI under 10',
    cumulative_rsi2: 'Cumulative RSI(2)', rsi2_reversion: 'RSI(2) washout', three_lower_lows: 'Three lower lows',
    _control_random_entry: 'Random entry (control)' };
  const dtab = (g) => `<div class="tablewrap"><table><thead><tr><th>Rule</th><th class="n">Trades</th><th class="n">Win rate</th>
      <th class="n">Avg per trade</th><th class="n">Avg win</th><th class="n">Avg loss</th><th class="n">Worst</th></tr></thead><tbody>
      ${Object.entries(g).map(([k, x]) => `<tr${k.startsWith('_') ? ' class="ctrl"' : ''}><td>${esc(dnames[k] || k)}</td>
        <td class="n">${x.n}</td><td class="n">${x.win}%</td><td class="n ${x.avg_pct > 0 ? 'up' : 'down'}">${x.avg_pct > 0 ? '+' : ''}${x.avg_pct.toFixed(2)}%</td>
        <td class="n">+${x.avg_win_pct}%</td><td class="n">${x.avg_loss_pct}%</td><td class="n down">${x.worst_pct}%</td></tr>`).join('')}
      </tbody></table></div>`;
  const rnd = etf._control_random_entry;
  out.push(lesson('3. Where the famous 70% win rates really come from', `
    <p>Larry Connors' short-term rules are the best-known high-win-rate strategies in stock trading: buy a sharp dip while
      the market is above its 200-day average, sell on the first up-close. Tested here on ten years of daily bars:</p>
    <h3>Index ETFs (SPY, QQQ, IWM, DIA)</h3>${dtab(etf)}
    ${rnd ? `<p><strong>Look at the last row.</strong> Buying on random days with the same exit won <strong>${rnd.win}%</strong> of the time.
      Most of the famous win rate comes from the exit ("sell on the first up day") and from stocks drifting up over time.
      The good rules still add something on top, and that extra is the real edge. It is smaller than the win rate suggests.</p>` : ''}
    <h3>Large individual stocks</h3>${dtab(big)}
    <p>On single stocks the win rates hold up, but look at the worst trade: with no stop, one bad company can take a
      third of the position. These rules were built for index funds for a reason.</p>`));

  // 4. most strategies are the weather
  const beat = (A, p) => Object.entries(A.cards || {}).filter(([n, c]) => !n.startsWith('_') && c[p] && c[p].n >= 30 && c[p].excess > 0).length;
  const judged = (A, p) => Object.entries(A.cards || {}).filter(([n, c]) => !n.startsWith('_') && c[p] && c[p].n >= 30).length;
  const ctlC = ((C.cards || {})._control_random_entry || {}).A, ctlK = ((K.cards || {})._control_random_entry || {}).A;
  out.push(lesson('4. Most strategies are measuring the weather', `
    <p>Every strategy is compared with a control that buys at random under the same rules. In a rising market the control
      makes money too, so a strategy has to beat it to prove it knows anything.</p>
    <ul>
      <li><strong>Crypto:</strong> random buying averaged ${rFmt(ctlC && ctlC.exp)} per trade; <strong>${beat(C, 'A')} of ${judged(C, 'A')}</strong> strategies beat it.</li>
      <li><strong>Stocks:</strong> random buying averaged ${rFmt(ctlK && ctlK.exp)} per trade; <strong>${beat(K, 'A')} of ${judged(K, 'A')}</strong> strategies beat it.</li>
    </ul>
    <p>That is why the bots never trust a strategy blindly. Before every trade they check whether the strategies that
      fired have actually worked on that exact market recently, and beaten random buying there.</p>`));

  // 5. day trading vs holding
  const kA = pooled(K.cards, 'A'), kD = pooled(K.cards, 'DT'), cA = pooled(C.cards, 'A'), cD = pooled(C.cards, 'DT');
  out.push(lesson('5. Day trading versus holding a few days', `
    <p>Same entries, two ways out: a true day trade that is closed by the end of the session, or a trade allowed up to four
      days to reach its stop or target. Averaged over every strategy:</p>
    <div class="tablewrap"><table><thead><tr><th>Market</th><th class="n">Day trade: win</th><th class="n">Day trade: per trade</th>
      <th class="n">Up to 4 days: win</th><th class="n">Up to 4 days: per trade</th></tr></thead><tbody>
      ${[['Crypto', cD, cA], ['US stocks', kD, kA]].map(([n, d, a]) => `<tr><td>${n}</td>
        <td class="n">${d ? d.win.toFixed(1) + '%' : '—'}</td><td class="n ${d && d.exp > 0 ? 'up' : 'down'}">${d ? rFmt(d.exp) : '—'}</td>
        <td class="n">${a ? a.win.toFixed(1) + '%' : '—'}</td><td class="n ${a && a.exp > 0 ? 'up' : 'down'}">${a ? rFmt(a.exp) : '—'}</td></tr>`).join('')}
      </tbody></table></div>
    <p>A day trade gives the idea only a few hours to work. With a stop wide enough to survive normal noise, most trades
      end at the bell somewhere in the middle, and the fees on every trade add up. That is the measured reason the bots
      hold up to four days by default. You can switch stocks to true day trading in Bot settings.</p>`));

  // 6. costs
  out.push(lesson('6. Fees decide more trades than strategies do', `
    <p>The cost of a trade, measured in R, is the round-trip fee divided by how far away your stop is:</p>
    <p class="formula">cost in R = 2 × (fee + slippage) ÷ stop distance</p>
    <ul><li>Crypto at a 0.26% taker fee with a 1% stop: 2 × 0.28% ÷ 1% = <strong>0.56R</strong>. More than half the risk is gone before the trade starts.</li>
      <li>The same trade with a 4% stop: <strong>0.14R</strong>. Wide stops, sized smaller, are how retail traders survive fees.</li>
      <li>US stocks at a commission-free broker: about <strong>0.01R</strong>. Stocks are far cheaper to day trade than crypto.</li></ul>
    <p>The bots refuse any trade where fees would take more than 20% of the risk. Choosing a cheaper exchange or maker
      orders improves results more reliably than any new indicator.</p>`));

  // 7. risk and survival
  const streaks = [0.4, 0.5, 0.6].map(w => `<tr><td>${Math.round(w * 100)}%</td>
    <td class="n">${Math.round(streakOdds(w, 100, 5) * 100)}%</td><td class="n">${Math.round(streakOdds(w, 100, 8) * 100)}%</td>
    <td class="n">${Math.round(streakOdds(w, 100, 10) * 100)}%</td></tr>`).join('');
  out.push(lesson('7. Risk: how not to blow up', `
    <p><strong>Risk 1% per trade or less.</strong> Losing streaks are not bad luck, they are guaranteed. Chance of a losing
      streak somewhere in your next 100 trades:</p>
    <div class="tablewrap"><table><thead><tr><th>Win rate</th><th class="n">5 in a row</th><th class="n">8 in a row</th>
      <th class="n">10 in a row</th></tr></thead><tbody>${streaks}</tbody></table></div>
    <p>At 1% risk, ten losses cost about 10%. At 10% risk they cost 65%. <strong>Losses are harder to undo than they look:</strong></p>
    <div class="tablewrap"><table><thead><tr><th>Drop</th><th class="n">Gain needed to get back</th></tr></thead><tbody>
      ${[10, 20, 30, 50, 75].map(d => `<tr><td>−${d}%</td><td class="n">+${Math.round(100 * d / (100 - d))}%</td></tr>`).join('')}</tbody></table></div>
    <p>Decide the stop before you enter, size the position from it (risk ÷ distance to stop), never move a stop further away,
      and stop for the day after a set loss. The bots do all of this automatically: 1% risk, a 4% daily loss limit, and a
      pause after four losses in a row.</p>`));

  // 8. what works
  const top = (A, p, k) => Object.entries(A.cards || {}).filter(([n, c]) => !n.startsWith('_') && c[p] && c[p].n >= 60)
    .sort((a, b) => b[1][p].exp - a[1][p].exp).slice(0, k);
  const tlist = (A, p) => `<div class="tablewrap"><table><thead><tr><th>Strategy</th><th class="n">Trades</th><th class="n">Win</th>
      <th class="n">Per trade</th><th class="n">Earlier half</th><th class="n">Later half</th><th class="n">Beats random in</th></tr></thead><tbody>
      ${top(A, p, 10).map(([n, c]) => { const x = c[p]; return `<tr><td class="small"><strong>${esc(n)}</strong></td><td class="n">${x.n}</td>
        <td class="n">${x.win}%</td><td class="n ${x.exp > 0 ? 'up' : 'down'}">${rFmt(x.exp)}</td>
        <td class="n">${rFmt(x.early)}</td><td class="n">${rFmt(x.late)}</td><td class="n">${esc(x.beats_random_in)} markets</td></tr>`; }).join('')}
      </tbody></table></div>`;
  out.push(lesson('8. What held up best, measured', `
    <p>The ten best strategies on each market (60+ trades), with their results in the earlier and later half of the data.
      A strategy whose result flips between halves was probably lucky. One that holds up in both, and beats random buying in
      most markets, is the kind worth paying attention to.</p>
    <h3>Crypto</h3>${tlist(C, 'A')}<h3 style="margin-top:10px">US stocks</h3>${tlist(K, 'A')}
    ${(() => {
      const cBest = top(C, 'A', 1)[0], kBest = top(K, 'A', 1)[0];
      const cPos = Object.entries(C.cards || {}).filter(([n, c]) => !n.startsWith('_') && c.A && c.A.n >= 60 && c.A.exp > 0).length;
      const kPos = Object.entries(K.cards || {}).filter(([n, c]) => !n.startsWith('_') && c.A && c.A.n >= 60 && c.A.exp > 0).length;
      return `<p><strong>Crypto and stocks behaved very differently.</strong> On crypto, after a 0.26% taker fee and slippage,
        only ${cPos} strateg${cPos === 1 ? 'y was' : 'ies were'} above zero on its own over this period${cBest ? ` (best: ${esc(cBest[0])}, ${rFmt(cBest[1].A.exp)})` : ''};
        buying at random lost ${rFmt(ctlC && ctlC.exp)} per trade because the period included a long fall. On stocks, with almost no
        fees and a rising market, ${kPos} were positive${kBest ? ` (best: ${esc(kBest[0])}, ${rFmt(kBest[1].A.exp)})` : ''}, but random
        buying made ${rFmt(ctlK && ctlK.exp)} too, so the real edge is the gap between the two.</p>
        <p>Even the best numbers are small: a few hundredths to a tenth of R per trade. That is what a real edge looks like.
        Anything that promises much more is taking hidden risk or has not been measured this way. It is also why the bots
        only use a strategy where it has recently worked on that exact market, and refuse trades where fees are too big.</p>`;
    })()}`));

  // 9. what the Brain can and cannot do
  const bC = ((C.brain || {}).A) || {}, bK = ((K.brain || {}).A) || {};
  const brow = (lbl, x) => x && x.n ? `<tr><td>${esc(lbl)}</td><td class="n">${x.n.toLocaleString()}</td><td class="n">${x.win}%</td>
      <td class="n ${x.exp > 0 ? 'up' : 'down'}">${rFmt(x.exp)}</td></tr>` : '';
  const btab = (e) => `<div class="tablewrap"><table><thead><tr><th>Trades chosen by</th><th class="n">Trades</th><th class="n">Win</th>
      <th class="n">Per trade</th></tr></thead><tbody>
      ${brow('Every moment any strategy fired', e.all_candidates)}${brow("The bots' backtest rule", e.bots_rule)}
      ${e.veto_q ? brow(`Backtest rule, minus the Brain's worst ${e.veto_q}%`, (e.rule_minus_worst || {})[String(e.veto_q)]) : ''}
      ${brow("The Brain's own top 10%", e.brain_top10pct)}</tbody></table></div>`;
  out.push(lesson('9. What 120 agents and a learned brain can and cannot do', `
    <p>The Brain reads every strategy plus 25 context signals and learns, from hundreds of thousands of past moments, which
      combinations tended to end well. It was trained on the first 60% of history and judged on the last 40%, which it never saw.</p>
    <h3>Crypto: correlation with the real outcome ${rFmt(bC.test_ic).replace('R', '')}</h3>${btab(bC)}
    <h3 style="margin-top:10px">US stocks: correlation ${rFmt(bK.test_ic).replace('R', '')}</h3>${btab(bK)}
    <p>${[['crypto', bC], ['stocks', bK]].map(([nm, e]) => e.skilled
        ? `On ${nm} it learned something small but real, mostly how to spot the trades most likely to lose, so it is allowed to veto those.`
        : `On ${nm} it found nothing reliable enough on unseen data, so there it abstains and never blocks a trade.`).join(' ')}
      That is an honest result: more agents and more data do not create an edge where the market does not offer one. A system
      that claims otherwise has usually been tested on the same data it learned from.</p>`));

  // 10. rules
  out.push(lesson('10. Ten rules the bots follow, and you should too', `<ol>
      <li>Know your stop before you enter. The stop decides your size, not the other way round.</li>
      <li>Risk 1% or less per trade. You will have ten losses in a row eventually.</li>
      <li>Judge by average result per trade after fees, never by win rate.</li>
      <li>Compare every strategy with random buying on the same market.</li>
      <li>Trust only what has worked recently on the market you are trading, and re-check it.</li>
      <li>Refuse trades where fees eat more than a fifth of the risk.</li>
      <li>Stop trading for the day after a set loss.</li>
      <li>Keep a journal of every trade with its reason. The Bots tab does this for you.</li>
      <li>Fifty trades before judging anything. Under that, results are mostly noise.</li>
      <li>Practice money until the numbers earn the right to real money.</li></ol>`));
  return out.join('');
}

let learnBook = null;
async function loadLearn() {
  if (!learnBook) {
    try { learnBook = await api('/api/learn'); } catch (e) { $('#learnLessons').innerHTML = `<div class="card down">${esc(e.message)}</div>`; return; }
    if (learnBook.error) { $('#learnLessons').innerHTML = `<div class="card">${esc(learnBook.error)}</div>`; return; }
    $('#learnMeta').textContent = learnBook.generated ? ` Measured ${learnBook.generated}.` : '';
    $('#learnLessons').innerHTML = buildLessons(learnBook);
    const fams = [...new Set(learnBook.strategies.map(s => s.family))].filter(f => f !== 'control').sort();
    $('#encFamily').innerHTML = '<option value="">Every family</option>' + fams.map(f => `<option>${esc(f)}</option>`).join('');
  }
  renderEncyclopedia();
}

function renderEncyclopedia() {
  const b = learnBook; if (!b) return;
  const C = ((b.assets || {}).crypto || {}).cards || {}, K = ((b.assets || {}).stock || {}).cards || {};
  const q = ($('#encSearch').value || '').toLowerCase(), fam = $('#encFamily').value, sort = $('#encSort').value;
  const usedBy = s => b.bots.filter(bt => bt.families === '*' || bt.families.includes(s.family)).map(bt => bt.name);
  let rows = b.strategies.filter(s => s.family !== 'control' && (!fam || s.family === fam)
    && (!q || s.name.includes(q) || s.description.toLowerCase().includes(q)));
  const val = s => ({ crypto: (C[s.name] || {}).A, stock: (K[s.name] || {}).A, stock_dt: (K[s.name] || {}).DT }[sort]);
  if (sort === 'name') rows.sort((a, c) => a.name.localeCompare(c.name));
  else if (sort === 'win') rows.sort((a, c) => (((C[c.name] || {}).A || {}).win || 0) - (((C[a.name] || {}).A || {}).win || 0));
  else rows.sort((a, c) => ((val(c) || {}).exp ?? -9) - ((val(a) || {}).exp ?? -9));
  $('#encCount').textContent = `${rows.length} strategies`;
  const cell = x => x && x.n ? `<td class="n">${x.win}%</td><td class="n ${x.exp > 0 ? 'up' : 'down'}">${rFmt(x.exp)}</td>`
    : '<td class="n muted">—</td><td class="n muted">—</td>';
  $('#encTable').innerHTML = `<div class="tablewrap"><table><thead><tr><th>Strategy</th><th>Family</th>
      <th class="n">Crypto win</th><th class="n">Crypto R</th><th class="n">Stocks win</th><th class="n">Stocks R</th>
      <th class="n">Day-trade win</th><th class="n">Day-trade R</th><th class="n">Beats random</th></tr></thead><tbody>
      ${rows.map(s => { const c = (C[s.name] || {}).A, k = (K[s.name] || {}).A, d = (K[s.name] || {}).DT; return `
        <tr class="row" data-enc="${esc(s.name)}"><td><strong class="small">${esc(s.name)}</strong></td><td class="tiny sec">${esc(s.family)}</td>
          ${cell(c)}${cell(k)}${cell(d)}<td class="n tiny">${esc((c || {}).beats_random_in || '—')} · ${esc((k || {}).beats_random_in || '—')}</td></tr>
        <tr class="encx" data-for="${esc(s.name)}" hidden><td colspan="9"><div class="small">${esc(s.description)}</div>
          <div class="tiny muted" style="margin-top:4px">Used by: ${esc(usedBy(s).join(', ') || '—')}.
          Crypto, earlier vs later half: ${rFmt((c || {}).early)} → ${rFmt((c || {}).late)}.
          Stocks: ${rFmt((k || {}).early)} → ${rFmt((k || {}).late)}. Profit factor ${(c || {}).pf ?? '—'} crypto, ${(k || {}).pf ?? '—'} stocks.</div></td></tr>`; }).join('')}
      </tbody></table></div>
      <p class="tiny muted" style="margin:6px 0 0">"Beats random" is crypto · stocks: markets where it beat random buying out of markets where it traded 5+ times.</p>`;
  $$('#encTable tr[data-enc]').forEach(tr => tr.addEventListener('click', () => {
    const x = $(`#encTable tr[data-for="${CSS.escape(tr.dataset.enc)}"]`); if (x) x.hidden = !x.hidden;
  }));
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
  if (name === 'bots') loadBots();
  if (name === 'brain') loadBrain();
  if (name === 'learn') loadLearn();
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
    await post('/api/research/run', { bars: Number($('#rBars').value), markets: Number($('#rMarkets').value), asset: $('#rAsset').value });
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

  $('#runBots').addEventListener('click', async e => {
    e.target.disabled = true;
    const running = state.bots && state.bots.running;
    try { renderBots(await post(running ? '/api/bots/stop' : '/api/bots/run')); }
    catch (err) { $('#botsState').textContent = err.message; e.target.disabled = false; }
  });
  $('#closeAllBots').addEventListener('click', async () => {
    if (!confirm('Sell every open bot trade at the current price?')) return;
    const r = await post('/api/bots/close-all');
    renderBots(r.status);
  });
  $('#feedKind').addEventListener('change', renderFeed);
  $('#rAsset').addEventListener('change', loadResearch);
  $('#agentSearch').addEventListener('input', renderAgents);
  $('#agentKind').addEventListener('change', renderAgents);
  $('#brainSave').addEventListener('click', async () => {
    await post('/api/bots/settings', { brain_mode: $('#brainMode').value });
    loadBrain();
  });
  ['#encSearch', '#encFamily', '#encSort'].forEach(id => $(id).addEventListener(id === '#encSearch' ? 'input' : 'change', renderEncyclopedia));

  buildSettingsUI(state.health);
  refreshViewSelect();
  syncFilterUI();
  loadBots();
  loadScan(false);
  setInterval(() => loadAlerts(true), 60000);
  // The Bots tab refreshes every few seconds while it is on screen, and quietly otherwise
  // so the ON badge stays true.
  let tick = 0;
  setInterval(() => {
    tick++;
    const onBots = $('#panel-bots').classList.contains('on') && !document.hidden;
    if (onBots || tick % 6 === 0) loadBots();
  }, 5000);
}
boot();
