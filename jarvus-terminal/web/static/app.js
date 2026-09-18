/* Jarvus Terminal front end. No libraries: every chart is inline SVG built here,
   which keeps the app's no-install promise intact all the way to the browser. */
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const state = { scan: null, selected: null, learn: null };

/* ---------- formatting ---------- */
const fmtPrice = v => {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (a >= 1)    return v.toFixed(2);
  if (a >= 0.01) return v.toFixed(4);
  return v.toPrecision(3);
};
const pct  = (v, d = 1) => v == null || !isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`;
const usd  = v => v == null ? '—' : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B`
                 : v >= 1e6 ? `$${(v / 1e6).toFixed(0)}M` : `$${(v / 1e3).toFixed(0)}K`;
/* Position size spans many orders of magnitude across markets, so a fixed number of
   decimals is wrong at both ends: 11 decimal places on a meme, none on Bitcoin. */
const fmtQty = v => {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (a >= 1)    return v.toLocaleString(undefined, { maximumFractionDigits: 3 });
  return Number(v.toPrecision(4)).toString();
};
const esc  = s => String(s ?? '').replace(/[&<>"']/g, c =>
                 ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
/* Direction always carries a glyph and a sign, so colour is reinforcement and never
   the only cue — the accessibility rule that matters most on a trading screen. */
const dirCls = v => v > 0 ? 'up' : v < 0 ? 'down' : 'muted';
const dirGlyph = v => v > 0 ? '▲' : v < 0 ? '▼' : '•';

/* ---------- tooltip ---------- */
const tip = $('#tip');
function showTip(html, ev) {
  tip.innerHTML = html;
  tip.classList.add('on');
  const pad = 14, r = tip.getBoundingClientRect();
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
  tip.style.left = Math.max(8, x) + 'px';
  tip.style.top = Math.max(8, y) + 'px';
}
const hideTip = () => tip.classList.remove('on');
document.addEventListener('scroll', hideTip, true);

/* ---------- charts ---------- */
const SVG = 'http://www.w3.org/2000/svg';
const el = (n, a = {}) => { const e = document.createElementNS(SVG, n);
  for (const k in a) e.setAttribute(k, a[k]); return e; };

/** Sparkline: one series, so no legend — the row names it. 2px line. */
function sparkline(values, w = 76, h = 22) {
  const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, class: 'spark', 'aria-hidden': 'true' });
  const v = values.filter(x => isFinite(x));
  if (v.length < 2) return svg;
  const lo = Math.min(...v), hi = Math.max(...v), span = (hi - lo) || 1;
  const x = i => (i / (v.length - 1)) * (w - 2) + 1;
  const y = k => h - 2 - ((k - lo) / span) * (h - 4);
  const d = v.map((k, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(k).toFixed(1)}`).join(' ');
  const rising = v[v.length - 1] >= v[0];
  svg.appendChild(el('path', { d, fill: 'none', 'stroke-width': 2, 'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    stroke: rising ? 'var(--up)' : 'var(--down)' }));
  return svg;
}

/**
 * Price over time. Price and volume are deliberately two stacked plots rather than
 * one plot with two y-scales: a dual axis lets the designer slide two unrelated
 * scales against each other until they appear correlated, which invents a
 * relationship the data does not contain.
 */
function priceChart(candles, height = 210) {
  const wrap = document.createElement('figure');
  if (!candles || candles.length < 3) { wrap.innerHTML = '<p class="muted small">No candles.</p>'; return wrap; }
  const W = 900, H = height, m = { t: 10, r: 52, b: 20, l: 8 };
  const closes = candles.map(c => c.c);
  const lo = Math.min(...candles.map(c => c.l)), hi = Math.max(...candles.map(c => c.h));
  const span = (hi - lo) || 1;
  const X = i => m.l + (i / (candles.length - 1)) * (W - m.l - m.r);
  const Y = v => m.t + (1 - (v - lo) / span) * (H - m.t - m.b);

  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `Price over the last ${candles.length} hours` });

  // recessive solid hairline grid, never dashed
  const g = el('g', { class: 'axis' });
  for (let i = 0; i <= 4; i++) {
    const v = lo + (span * i) / 4, y = Y(v);
    g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grid-line' }));
    const t = el('text', { x: W - m.r + 6, y: y + 3 }); t.textContent = fmtPrice(v);
    g.appendChild(t);
  }
  svg.appendChild(g);

  const area = candles.map((c, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(c.c).toFixed(1)}`).join(' ')
    + ` L${X(candles.length - 1).toFixed(1)},${Y(lo)} L${X(0).toFixed(1)},${Y(lo)} Z`;
  const grad = el('linearGradient', { id: 'pg', x1: '0', y1: '0', x2: '0', y2: '1' });
  grad.appendChild(el('stop', { offset: '0%', 'stop-color': 'var(--series-1)', 'stop-opacity': '.20' }));
  grad.appendChild(el('stop', { offset: '100%', 'stop-color': 'var(--series-1)', 'stop-opacity': '0' }));
  const defs = el('defs'); defs.appendChild(grad); svg.appendChild(defs);
  svg.appendChild(el('path', { d: area, fill: 'url(#pg)' }));
  svg.appendChild(el('path', {
    d: candles.map((c, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(c.c).toFixed(1)}`).join(' '),
    fill: 'none', stroke: 'var(--series-1)', 'stroke-width': 2,
    'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));

  // crosshair + tooltip
  const cross = el('line', { y1: m.t, y2: H - m.b, stroke: 'var(--text-muted)', 'stroke-width': 1, opacity: 0 });
  const dot = el('circle', { r: 4, fill: 'var(--series-1)', stroke: 'var(--surface-1)', 'stroke-width': 2, opacity: 0 });
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
    showTip(`<div class="t">${esc(c.t)}</div>
      <div class="r"><span>open</span><span>${fmtPrice(c.o)}</span></div>
      <div class="r"><span>high</span><span>${fmtPrice(c.h)}</span></div>
      <div class="r"><span>low</span><span>${fmtPrice(c.l)}</span></div>
      <div class="r"><span>close</span><span>${fmtPrice(c.c)}</span></div>`, ev);
  });
  hit.addEventListener('mouseleave', () => { hideTip(); cross.setAttribute('opacity', 0); dot.setAttribute('opacity', 0); });

  wrap.appendChild(svg);
  const cap = document.createElement('figcaption');
  cap.textContent = `Close, last ${candles.length} hourly bars. Only closed bars are drawn.`;
  wrap.appendChild(cap);
  return wrap;
}

/** Volume, as its own plot sharing the x range. */
function volumeChart(candles, height = 70) {
  const wrap = document.createElement('figure');
  if (!candles || !candles.length) return wrap;
  const W = 900, H = height, m = { t: 6, r: 52, b: 14, l: 8 };
  const hi = Math.max(...candles.map(c => c.v)) || 1;
  const bw = Math.max(1, (W - m.l - m.r) / candles.length - 1);
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Volume per hour' });
  candles.forEach((c, i) => {
    const x = m.l + (i / (candles.length - 1)) * (W - m.l - m.r - bw);
    const h = Math.max(1, (c.v / hi) * (H - m.t - m.b));
    const r = el('rect', { x, y: H - m.b - h, width: bw, height: h, rx: Math.min(2, bw / 2),
      fill: 'var(--text-muted)', opacity: .5 });
    r.addEventListener('mousemove', ev => showTip(
      `<div class="t">${esc(c.t)}</div><div class="r"><span>volume</span><span>${c.v.toLocaleString(undefined,{maximumFractionDigits:0})}</span></div>`, ev));
    r.addEventListener('mouseleave', hideTip);
    svg.appendChild(r);
  });
  wrap.appendChild(svg);
  const cap = document.createElement('figcaption'); cap.textContent = 'Volume, same hours.';
  wrap.appendChild(cap);
  return wrap;
}

/** Reliability curve: two series, so a legend is always present. */
function calibrationChart(buckets) {
  const wrap = document.createElement('figure');
  const pts = buckets.filter(b => b.n > 0 && b.big_move_rate != null);
  if (pts.length < 2) {
    wrap.innerHTML = '<p class="muted small">Not enough graded predictions yet to draw a reliability curve.</p>';
    return wrap;
  }
  const W = 560, H = 300, m = { t: 14, r: 16, b: 38, l: 46 };
  const X = v => m.l + v * (W - m.l - m.r);
  const Y = v => m.t + (1 - v) * (H - m.t - m.b);

  const legend = document.createElement('div');
  legend.className = 'legend';
  legend.innerHTML = `
    <span class="item"><span class="sw" style="background:var(--series-1)"></span>Measured on your data</span>
    <span class="item"><span class="sw" style="background:var(--text-muted)"></span>Perfect calibration</span>`;
  wrap.appendChild(legend);

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

  // the reference: a perfectly calibrated app would sit on this line
  svg.appendChild(el('line', { x1: X(0), y1: Y(0), x2: X(1), y2: Y(1),
    stroke: 'var(--text-muted)', 'stroke-width': 2, opacity: .45 }));

  const d = pts.map((b, i) => `${i ? 'L' : 'M'}${X(b.mean_score)},${Y(b.big_move_rate / 100)}`).join(' ');
  svg.appendChild(el('path', { d, fill: 'none', stroke: 'var(--series-1)', 'stroke-width': 2,
    'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));

  pts.forEach(b => {
    // 2px surface ring keeps overlapping markers separable without a border
    const c = el('circle', { cx: X(b.mean_score), cy: Y(b.big_move_rate / 100),
      r: 5, fill: 'var(--series-1)', stroke: 'var(--surface-1)', 'stroke-width': 2 });
    c.addEventListener('mousemove', ev => showTip(
      `<div class="t">Heat ${esc(b.range)}</div>
       <div class="r"><span>said</span><span>${b.mean_score.toFixed(2)}</span></div>
       <div class="r"><span>big move followed</span><span>${b.big_move_rate}%</span></div>
       <div class="r"><span>sample</span><span>${b.n}</span></div>`, ev));
    c.addEventListener('mouseleave', hideTip);
    svg.appendChild(c);
  });

  const xl = el('text', { x: (m.l + W - m.r) / 2, y: H - 4, 'text-anchor': 'middle', class: 'axis' });
  xl.setAttribute('fill', 'var(--text-muted)'); xl.setAttribute('font-size', '11');
  xl.textContent = 'heat score the app gave'; svg.appendChild(xl);

  wrap.appendChild(svg);
  const cap = document.createElement('figcaption');
  cap.textContent = 'Points above the reference line mean the app understates; below means it overstates.';
  wrap.appendChild(cap);
  return wrap;
}

/** Small horizontal bars showing what drove a gate reading. */
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

/* ---------- gate presentation ---------- */
const gateChip = g => {
  if (!g) return '<span class="chip">no data</span>';
  const cls = g.label === 'LOUD' ? 'loud' : g.label === 'COILED' ? 'coiled' : '';
  return `<span class="chip ${cls}"><span class="sw"></span>${g.label}</span>`;
};
const verdictChip = v =>
  `<span class="chip ${v === 'BUY' ? 'buy' : 'wait'}"><span class="sw"></span>${esc(v)}</span>`;

/* ---------- API ---------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

/* ---------- markets ---------- */
function renderTiles(s) {
  const u = s.universe;
  const buys  = s.markets.filter(m => m.signal && m.signal.verdict === 'BUY').length;
  const louds = s.markets.filter(m => m.gate && m.gate.label === 'LOUD').length;
  const tiles = [
    ['Markets scanned', u.discovered.toLocaleString(), `${u.liquid} cleared the liquidity floor`],
    ['Assets analysed', u.analysed, `deduplicated from ${u.assets_after_dedupe}`],
    ['Moving now', louds, 'gate reads LOUD'],
    ['Plans that passed', buys, 'structure and cost gates both clear'],
    ['Scan time', s.elapsed_s + 's', `fee tier: ${s.fee_tier}`],
    ['Predictions logged', s.predictions_written, `graded after ${s.resolve_horizon_h}h`],
  ];
  $('#tiles').innerHTML = tiles.map(([k, v, sub]) =>
    `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${esc(String(v))}</div>
     <div class="s">${esc(sub)}</div></div>`).join('');
}

function renderMarkets(s) {
  const rows = s.markets.filter(m => !m.error);
  const maxHeat = Math.max(...rows.map(m => m.gate.blow_score), 0.01);
  const wrap = $('#marketsWrap');
  wrap.innerHTML = `<table><thead><tr>
      <th>Market</th><th>Heat</th><th>State</th><th class="n">Price</th><th class="n">24h</th>
      <th>Trend</th><th class="n">Move/bar</th><th class="n">Big move is</th>
      <th>Plan</th><th class="n">Cost</th><th class="n">Liquidity</th><th>News</th>
    </tr></thead><tbody></tbody></table>`;
  const tb = $('tbody', wrap);

  rows.forEach(m => {
    const g = m.gate, sig = m.signal, st = m.structure;
    const tr = document.createElement('tr');
    tr.className = 'row'; tr.tabIndex = 0;
    tr.innerHTML = `
      <td><strong>${esc(m.base)}</strong><span class="muted tiny">/${esc(m.quote)}</span>
          <div class="tiny muted">${esc(m.venue)} · ${esc(m.kind)}</div></td>
      <td><div class="heat"><span class="track"><span class="fill" style="width:${(g.blow_score / maxHeat * 100).toFixed(0)}%"></span></span>
          <span class="val">${g.blow_score.toFixed(2)}</span></div></td>
      <td>${gateChip(g)}</td>
      <td class="n">${fmtPrice(m.price)}</td>
      <td class="n ${dirCls(m.change_24h_pct)}">${dirGlyph(m.change_24h_pct)} ${pct(m.change_24h_pct)}</td>
      <td class="tiny sec">${esc(st.trend)}<div class="tiny muted">${esc(st.ema_stack)}</div></td>
      <td class="n">${st.atr_pct ? st.atr_pct.toFixed(2) + '%' : '—'}</td>
      <td class="n muted">${m.big_move_threshold_pct != null ? '≥' + m.big_move_threshold_pct + '%' : '—'}</td>
      <td>${verdictChip(sig.verdict)}${sig.confluence ? `<div class="tiny muted">${sig.confluence.score}/${sig.confluence.max} ${esc(sig.confluence.grade)}</div>` : ''}</td>
      <td class="n">${sig.confluence ? (sig.confluence.cost_r * 100).toFixed(0) + '%' : '—'}</td>
      <td class="n muted">${usd(m.usd_volume_24h)}</td>
      <td class="tiny">${m.news.length ? `<span class="hot">${m.news.length}</span>` : '<span class="muted">—</span>'}</td>`;

    const sparkTd = document.createElement('td');
    tr.addEventListener('mousemove', ev => showTip(
      `<div class="t">${esc(m.symbol)}</div><div>${esc(g.explain)}</div>`, ev));
    tr.addEventListener('mouseleave', hideTip);
    const open = () => openDetail(m.symbol, m.venue);
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    tb.appendChild(tr);
  });

  if (!rows.length) wrap.innerHTML = '<p class="muted">No markets returned candles. Check the network and rescan.</p>';
}

async function loadScan(force) {
  $('#marketsWrap').innerHTML = '<div class="load"><span class="spin"></span>scanning every liquid market…</div>';
  const q = new URLSearchParams({ n: $('#deepN').value, fee_tier: $('#feeTier').value,
    account: $('#account').value, force: force ? '1' : '0' });
  try {
    const s = await api('/api/scan?' + q);
    state.scan = s;
    renderTiles(s); renderMarkets(s);
    $('#subtitle').textContent =
      `${s.universe.discovered.toLocaleString()} markets seen · ${s.universe.analysed} analysed · ${s.elapsed_s}s`;
  } catch (e) {
    $('#marketsWrap').innerHTML = `<p class="down">Scan failed: ${esc(e.message)}</p>`;
  }
}

/* ---------- detail ---------- */
async function openDetail(symbol, venue) {
  showTab('detail');
  const box = $('#detail');
  box.innerHTML = '<div class="card"><div class="load"><span class="spin"></span>loading ' + esc(symbol) + '…</div></div>';
  let d;
  try {
    d = await api('/api/market?' + new URLSearchParams({ symbol, venue: venue || 'okx',
      fee_tier: $('#feeTier').value, account: $('#account').value }));
  } catch (e) { box.innerHTML = `<div class="card down">Could not load ${esc(symbol)}: ${esc(e.message)}</div>`; return; }
  if (d.error) { box.innerHTML = `<div class="card down">${esc(d.error)}</div>`; return; }
  state.selected = d;

  const m = d.market, g = d.gate, sig = d.signal, st = d.structure;
  box.innerHTML = `
    <div class="card">
      <div class="bar" style="margin-bottom:8px">
        <div class="brand" style="margin-right:auto">
          <h2>${esc(m.base)}/${esc(m.quote)}</h2>
          <span class="mono">${fmtPrice(m.price)}</span>
          <span class="${dirCls(m.change_24h_pct)}">${dirGlyph(m.change_24h_pct)} ${pct(m.change_24h_pct)}</span>
          ${gateChip(g)} ${verdictChip(sig.verdict)}
        </div>
        <a href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(d.tradingview)}"
           target="_blank" rel="noopener"><button>Open in TradingView ↗</button></a>
      </div>
      <div id="tvHost"></div>
    </div>

    <div class="grid two">
      <div>
        <div class="card"><h3>Price</h3><div id="pxChart"></div><div id="volChart"></div></div>
        <div class="card"><h3>Why the gate reads ${esc(g.label)}</h3>
          <p class="small sec" style="margin:4px 0 10px">${esc(g.explain)}</p>
          <div class="grid" style="grid-template-columns:1fr 1fr;gap:18px">
            <div><h3>Already moving</h3><div id="expTerms"></div>
                 <div class="tiny muted" style="margin-top:4px">expansion ${g.expansion.toFixed(2)}</div></div>
            <div><h3>Wound tight</h3><div id="cmpTerms"></div>
                 <div class="tiny muted" style="margin-top:4px">compression ${g.compression.toFixed(2)}</div></div>
          </div>
          <div class="note" style="margin-top:12px">
            Heat <strong>${g.blow_score.toFixed(2)}</strong> — absolute speed ${g.energy.toFixed(2)},
            relative signal ${Math.max(g.expansion, g.compression).toFixed(2)}.
            ${d.calibrated
              ? `On this app's own record, readings in the ${esc(d.calibrated.bucket)} band were followed by a big move
                 <strong>${d.calibrated.probability_pct}%</strong> of the time (${d.calibrated.sample} graded).`
              : `Not enough graded predictions yet to say how often this score is followed by a big move.
                 The Learning tab fills in once the horizon passes.`}
          </div>
        </div>
        <div class="card"><h3>Structure</h3>
          <div class="kv" style="margin-top:6px">
            <span class="k">Trend</span><span class="v">${esc(st.trend)}</span>
            <span class="k">EMA stack</span><span class="v">${esc(st.ema_stack)}</span>
            <span class="k">vs 200 EMA</span><span class="v">${esc(st.price_vs_ema200 || '—')}</span>
            <span class="k">From 21 EMA</span><span class="v">${st.dist_ema21_atr ?? '—'} ATR</span>
            <span class="k">RSI(14)</span><span class="v">${st.rsi14 ?? '—'}</span>
            <span class="k">RVOL</span><span class="v">${st.rvol ?? '—'}</span>
            <span class="k">In range</span><span class="v">${st.position_in_range_pct ?? '—'}%</span>
          </div>
          <h3 style="margin-top:12px">Nearest levels</h3>
          <table><tbody>${st.levels.slice(0, 7).map(l => `
            <tr><td class="small">${esc(l.name)}</td>
                <td class="n small">${fmtPrice(l.price)}</td>
                <td class="n tiny ${dirCls(l.distance_pct)}">${pct(l.distance_pct, 2)}</td></tr>`).join('')}</tbody></table>
        </div>
      </div>

      <div>
        <div class="card"><h3>The plan</h3>${planHtml(sig, m)}</div>
        <div class="card"><h3>Confluence ${sig.confluence.score}/${sig.confluence.max} · ${esc(sig.confluence.grade)}</h3>
          <table style="margin-top:6px"><tbody>${sig.confluence.rows.map(r => `
            <tr><td style="width:18px">${r.point ? '✓' : '·'}</td>
                <td><strong class="small">${esc(r.factor)}</strong>
                    <div class="tiny muted">${esc(r.why)}</div></td></tr>`).join('')}</tbody></table>
        </div>
        <div class="card"><h3>News naming ${esc(m.base)}</h3>
          ${d.news.length ? d.news.map(newsHtml).join('')
            : '<p class="muted small" style="margin-top:6px">Nothing in the current feeds names this asset.</p>'}
        </div>
      </div>
    </div>`;

  $('#pxChart').appendChild(priceChart(d.candles));
  $('#volChart').appendChild(volumeChart(d.candles));
  $('#expTerms').appendChild(termBars(g.expansion_terms, 'var(--series-2)'));
  $('#cmpTerms').appendChild(termBars(g.compression_terms, 'var(--series-1)'));
  mountTradingView(d.tradingview);
  $$('#detail [data-journal]').forEach(b => b.addEventListener('click', () => addToJournal(d)));
}

function planHtml(sig, m) {
  if (sig.verdict !== 'BUY') {
    return `<p class="small sec" style="margin:6px 0 10px">No plan. What is blocking it:</p>
      ${sig.blockers.map(b => `<div class="note warn" style="margin-bottom:6px">${esc(b)}</div>`).join('')}
      <p class="tiny muted" style="margin-top:10px">${esc(sig.direction_note)}</p>`;
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
    <button data-journal class="primary" style="margin-top:10px">Log this plan</button>
    <p class="tiny muted" style="margin-top:10px">${esc(sig.direction_note)}</p>`;
}

/* TradingView's official embeddable widget: the legitimate way to show their charts.
   If it is blocked or offline the app still works; the native chart above is the fallback. */
function mountTradingView(tvSymbol) {
  const host = $('#tvHost');
  if (!host) return;
  const dark = matchMedia('(prefers-color-scheme: dark)').matches &&
               document.documentElement.dataset.theme !== 'light' ||
               document.documentElement.dataset.theme === 'dark';
  const id = 'tv_' + Math.random().toString(36).slice(2);
  host.innerHTML = `<div id="${id}" class="tv"></div>
    <p class="tiny muted" id="${id}_cap" style="margin-top:6px">TradingView advanced chart widget,
      loading. The price chart below is computed locally and does not depend on it.</p>`;
  const s = document.createElement('script');
  s.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
  s.async = true;
  s.innerHTML = JSON.stringify({
    autosize: true, symbol: tvSymbol, interval: '60', timezone: 'Etc/UTC',
    theme: dark ? 'dark' : 'light', style: '1', locale: 'en',
    hide_side_toolbar: false, allow_symbol_change: true, container_id: id,
  });
  const mount = $('#' + id);
  mount.appendChild(s);
  // An empty 420px box is worse than no box. If the widget has not produced an
  // iframe shortly after mounting, the network is blocking it — collapse the space
  // and say so, since the locally computed chart below already covers the need.
  const collapse = () => {
    const box = $('#' + id);
    if (!box) return;
    if (box.querySelector('iframe')) {           // it loaded: drop the loading caption
      const cap = document.getElementById(id + '_cap');
      if (cap) cap.remove();
      return;
    }
    box.classList.add('tv-failed');
    box.style.height = 'auto';
    const cap = document.getElementById(id + '_cap');
    if (cap) cap.remove();
    box.innerHTML = `<div class="note warn">TradingView's widget did not load — this network blocks it.
      Everything below is computed locally from exchange candles and is unaffected.
      <a href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}"
         target="_blank" rel="noopener">Open ${esc(tvSymbol)} on TradingView ↗</a></div>`;
  };
  s.addEventListener('error', collapse);
  setTimeout(collapse, 4500);
}

/* ---------- news ---------- */
const newsHtml = n => `
  <div class="news-item">
    <a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>
    ${(n.hot || []).map(h => `<span class="hot">${esc(h.trim())}</span>`).join('')}
    <div class="tiny muted">${esc(n.source)}${n.age_minutes != null ? ` · ${n.age_minutes} min ago` : ''}</div>
  </div>`;

async function loadNews() {
  const w = $('#newsWrap');
  try {
    const n = await api('/api/news');
    w.innerHTML = `<p class="tiny muted" style="margin-bottom:8px">
        Sources live: ${esc(n.sources_ok.join(', ') || 'none')}
        ${n.sources_dead.length ? ` · not responding: ${esc(n.sources_dead.join(', '))}` : ''}</p>`
      + n.items.map(newsHtml).join('');
  } catch (e) { w.innerHTML = `<p class="down">News failed: ${esc(e.message)}</p>`; }
}

/* ---------- learning ---------- */
async function loadLearning() {
  const w = $('#learnWrap');
  try {
    const L = await api('/api/learning');
    state.learn = L;
    const c = L.counts, cal = L.calibration;
    let html = `<div class="grid tiles" style="margin-bottom:14px">
      ${[['Predictions made', c.predictions_total, 'written before the outcome'],
         ['Graded', c.resolved, `after ${cal.horizon_hours || 12}h`],
         ['Awaiting horizon', c.pending, 'not yet gradeable'],
         ['Scans run', c.scans, '']]
        .map(([k, v, s]) => `<div class="tile"><div class="k">${esc(k)}</div>
          <div class="v">${esc(String(v))}</div><div class="s">${esc(s)}</div></div>`).join('')}
      </div>`;

    if (!cal.samples) {
      html += `<div class="note">${esc(cal.note)}</div>`;
      w.innerHTML = html; return;
    }

    html += `<div class="grid two"><div><h3>Is the heat score honest?</h3>
        <div id="calChart" style="margin-top:8px"></div></div>
      <div><h3>By state</h3>
        <table style="margin-top:8px"><thead><tr><th>State</th><th class="n">n</th>
          <th class="n">Big move followed</th><th class="n">Median range</th></tr></thead><tbody>
          ${Object.entries(cal.by_label).map(([k, v]) => `<tr>
            <td>${gateChip({ label: k })}</td><td class="n">${v.n}</td>
            <td class="n">${v.big_move_rate}%</td><td class="n">${v.median_realized_range_pct}%</td>
          </tr>`).join('')}
        </tbody></table>
        <h3 style="margin-top:16px">The direction reality check</h3>
        <div class="kv" style="margin-top:6px">
          <span class="k">All predictions finished up</span><span class="v">${cal.direction_up_rate ?? '—'}%</span>
          <span class="k">BUY signals finished up</span><span class="v">${cal.buy_signal_up_rate ?? '—'}%</span>
        </div>
        <div class="note warn" style="margin-top:10px">${esc(cal.direction_note)}</div>
      </div></div>`;

    if (!cal.ready) {
      html += `<div class="note" style="margin-top:12px">Only ${cal.samples} graded so far;
        calibrated probabilities switch on at ${cal.min_samples}. Until then the app shows its raw
        score and says so, rather than dressing an unproven number up as a probability.</div>`;
    }
    w.innerHTML = html;
    const host = $('#calChart');
    if (host) host.appendChild(calibrationChart(cal.buckets));
  } catch (e) { w.innerHTML = `<p class="down">Learning failed: ${esc(e.message)}</p>`; }
}

/* ---------- journal ---------- */
async function addToJournal(d) {
  const s = d.signal;
  await api('/api/journal', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: d.market.symbol, entry: s.entry, stop: s.stop, target: s.target,
      risk_pct: s.risk_pct, units: s.units, grade: s.confluence.grade,
      gate_label: d.gate.label, cost_r: s.confluence.cost_r,
      notes: `heat ${d.gate.blow_score} · ${d.gate.label}` }) });
  showTab('journal'); loadJournal();
}

async function loadJournal() {
  const w = $('#journalWrap');
  try {
    const { rows } = await api('/api/journal');
    if (!rows.length) {
      w.innerHTML = '<p class="muted small">Nothing logged yet. Open a market with a plan and press “Log this plan”.</p>';
      return;
    }
    const closed = rows.filter(r => r.r_multiple != null);
    const tot = closed.reduce((a, r) => a + r.r_multiple, 0);
    const wins = closed.filter(r => r.r_multiple > 0).length;
    w.innerHTML = `
      <div class="grid tiles" style="margin-bottom:14px">
        <div class="tile"><div class="k">Closed</div><div class="v">${closed.length}</div></div>
        <div class="tile"><div class="k">Total</div><div class="v">${tot.toFixed(2)}R</div></div>
        <div class="tile"><div class="k">Expectancy</div><div class="v">${closed.length ? (tot / closed.length).toFixed(3) : '—'}R</div>
          <div class="s">per trade</div></div>
        <div class="tile"><div class="k">Closed green</div><div class="v">${closed.length ? Math.round(wins / closed.length * 100) : '—'}%</div>
          <div class="s">${closed.length < 50 ? 'under 50 trades: noise' : 'meaningful sample'}</div></div>
      </div>
      <table><thead><tr><th>Opened</th><th>Market</th><th class="n">Entry</th><th class="n">Stop</th>
        <th class="n">Target</th><th>Grade</th><th class="n">R</th><th></th></tr></thead><tbody>
        ${rows.map(r => `<tr>
          <td class="tiny muted">${esc((r.opened_at || '').replace('T', ' ').replace('Z', ''))}</td>
          <td><strong>${esc(r.symbol)}</strong></td>
          <td class="n">${fmtPrice(r.entry)}</td><td class="n">${fmtPrice(r.stop)}</td>
          <td class="n">${fmtPrice(r.target)}</td><td class="tiny">${esc(r.grade || '')}</td>
          <td class="n ${r.r_multiple > 0 ? 'up' : r.r_multiple < 0 ? 'down' : ''}">
            ${r.r_multiple != null ? r.r_multiple.toFixed(2) + 'R' : '<span class="muted">open</span>'}</td>
          <td>${r.closed_at ? '' : `<button data-close="${r.id}">Close</button>`}</td>
        </tr>`).join('')}
      </tbody></table>`;
    $$('#journalWrap [data-close]').forEach(b => b.addEventListener('click', async () => {
      const px = prompt('Exit price?');
      if (!px) return;
      await api('/api/journal', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ close_id: Number(b.dataset.close), exit_price: Number(px) }) });
      loadJournal();
    }));
  } catch (e) { w.innerHTML = `<p class="down">Journal failed: ${esc(e.message)}</p>`; }
}

/* ---------- tabs & boot ---------- */
function showTab(name) {
  $$('nav button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  $$('.panel').forEach(p => p.classList.toggle('on', p.id === 'panel-' + name));
  if (name === 'news' && !$('#newsWrap').dataset.loaded) { $('#newsWrap').dataset.loaded = '1'; loadNews(); }
  if (name === 'learning') loadLearning();
  if (name === 'journal') loadJournal();
}

async function boot() {
  $$('nav button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  $('#refresh').addEventListener('click', () => loadScan(true));
  $('#theme').addEventListener('click', () => {
    const cur = document.documentElement.dataset.theme;
    const next = cur === 'dark' ? 'light' : cur === 'light' ? 'dark'
      : (matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark');
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('jarvus-theme', next); } catch {}
    if (state.selected) mountTradingView(state.selected.tradingview);
  });
  try { const t = localStorage.getItem('jarvus-theme'); if (t) document.documentElement.dataset.theme = t; } catch {}
  $('#resolveBtn').addEventListener('click', async e => {
    e.target.disabled = true; e.target.textContent = 'grading…';
    try { const r = await api('/api/resolve', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: '{"limit":200}' });
      e.target.textContent = `graded ${r.graded}, ${r.failed} unavailable`; } catch { e.target.textContent = 'failed'; }
    setTimeout(() => { e.target.disabled = false; e.target.textContent = 'Grade what is due'; loadLearning(); }, 900);
  });
  $('#reloadLearn').addEventListener('click', loadLearning);
  [$('#feeTier'), $('#deepN'), $('#account')].forEach(i => i.addEventListener('change', () => loadScan(true)));

  try {
    const h = await api('/api/health');
    $('#feeTier').innerHTML = h.fee_tiers.map(t =>
      `<option ${t === h.default_fee_tier ? 'selected' : ''}>${esc(t)}</option>`).join('');
    $('#deepN').value = String(h.deep_n);
  } catch { $('#feeTier').innerHTML = '<option>Kraken Pro taker</option>'; }
  loadScan(false);
}
boot();
