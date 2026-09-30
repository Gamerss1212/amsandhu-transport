// Charts (TradingView Lightweight Charts v5, Apache-2.0, vendored in /vendor with its licence; its attribution
// logo stays on as the licence's notice asks). Candles with volume, indicators computed here from the same bars, and
// markers for the orders that actually filled.
const LW = window.LightweightCharts;

const THEME = {
  layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#b7a9d9', fontFamily: 'JetBrains Mono, Consolas, monospace', fontSize: 11 },
  grid: { vertLines: { color: 'rgba(168,85,247,0.07)' }, horzLines: { color: 'rgba(168,85,247,0.07)' } },
  rightPriceScale: { borderColor: 'rgba(168,85,247,0.3)' },
  timeScale: { borderColor: 'rgba(168,85,247,0.3)', timeVisible: true, secondsVisible: false },
  crosshair: { mode: 1, vertLine: { color: 'rgba(255,43,214,0.5)', labelBackgroundColor: '#7c3aed' }, horzLine: { color: 'rgba(255,43,214,0.5)', labelBackgroundColor: '#7c3aed' } },
};
export const MODE_COLOR = { live: '#ff3b5c', paper: '#22d3ee', demo: '#f5b301', research: '#8fb4ff' };
export const TF_S = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 };

export function available() { return !!LW; }

function ema(c, n) {
  const out = new Array(c.length).fill(null); const a = 2 / (n + 1); let e = null;
  for (let i = 0; i < c.length; i++) {
    if (i === n - 1) { let s = 0; for (let k = 0; k < n; k++) s += c[k]; e = s / n; }
    else if (i >= n) e = e + a * (c[i] - e);
    out[i] = i >= n - 1 ? e : null;
  }
  return out;
}
function bb(c, n = 20, k = 2) {
  const up = [], lo = [], mid = [];
  for (let i = 0; i < c.length; i++) {
    if (i < n - 1) { up.push(null); lo.push(null); mid.push(null); continue; }
    let s = 0; for (let j = i - n + 1; j <= i; j++) s += c[j];
    const m = s / n; let v = 0; for (let j = i - n + 1; j <= i; j++) v += (c[j] - m) ** 2;
    const sd = Math.sqrt(v / n); mid.push(m); up.push(m + k * sd); lo.push(m - k * sd);
  }
  return { up, lo, mid };
}
function vwap(d) {           // session VWAP reset at each UTC day (crypto) / each date (stocks)
  const out = []; let pv = 0, vv = 0, day = null;
  for (let i = 0; i < d.t.length; i++) {
    const dd = Math.floor(d.t[i] / 86400000);
    if (dd !== day) { day = dd; pv = 0; vv = 0; }
    const tp = (d.h[i] + d.l[i] + d.c[i]) / 3; pv += tp * (d.v[i] || 0); vv += (d.v[i] || 0);
    out.push(vv > 0 ? pv / vv : tp);
  }
  return out;
}

export class PriceChart {
  constructor(el, legendEl) {
    this.el = el; this.legend = legendEl;
    this.chart = LW.createChart(el, { ...THEME, autoSize: true, layout: { ...THEME.layout, attributionLogo: true } });
    this.candles = this.chart.addSeries(LW.CandlestickSeries, {
      upColor: '#22e39a', downColor: '#ff3b5c', borderUpColor: '#22e39a', borderDownColor: '#ff3b5c', wickUpColor: '#22e39a', wickDownColor: '#ff3b5c',
    });
    this.volume = this.chart.addSeries(LW.HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false });
    this.chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    this.ind = {};
    this.markersApi = LW.createSeriesMarkers ? LW.createSeriesMarkers(this.candles, []) : null;
    this.data = null;
    this.chart.subscribeCrosshairMove((p) => this._legend(p));
  }
  set(d, opts = {}) {
    this.data = d;
    const t = d.t.map(x => Math.floor(x / 1000));
    this.candles.setData(t.map((x, i) => ({ time: x, open: d.o[i], high: d.h[i], low: d.l[i], close: d.c[i] })));
    this.volume.setData(t.map((x, i) => ({ time: x, value: d.v[i] || 0, color: d.c[i] >= d.o[i] ? 'rgba(34,227,154,0.28)' : 'rgba(255,59,92,0.28)' })));
    this.indicators(opts.indicators || {});
    this._legend(null);
    if (opts.fit) this.chart.timeScale().fitContent();
  }
  indicators(which) {
    for (const s of Object.values(this.ind)) this.chart.removeSeries(s);
    this.ind = {};
    const d = this.data;
    if (!d || !d.c.length) return;
    const t = d.t.map(x => Math.floor(x / 1000));
    const line = (key, vals, color, width = 1.5) => {
      const s = this.chart.addSeries(LW.LineSeries, { color, lineWidth: width, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
      s.setData(t.map((x, i) => (vals[i] === null ? { time: x } : { time: x, value: vals[i] })));
      this.ind[key] = s;
    };
    if (which.ema21) line('ema21', ema(d.c, 21), '#c084fc');
    if (which.ema50) line('ema50', ema(d.c, 50), '#ff2bd6');
    if (which.vwap) line('vwap', vwap(d), '#22d3ee', 1.2);
    if (which.bb) { const b = bb(d.c); line('bbu', b.up, 'rgba(245,179,1,0.6)', 1); line('bbl', b.lo, 'rgba(245,179,1,0.6)', 1); }
  }
  markers(list, tf, show = true) {
    if (!this.markersApi) return;
    if (!show || !this.data) { this.markersApi.setMarkers([]); return; }
    const step = TF_S[tf] || 300;
    const first = this.data.t.length ? this.data.t[0] / 1000 : 0;
    const ms = list.filter(m => m.time / 1000 >= first).map(m => {
      const buy = m.side === 'buy';
      return { time: Math.floor(m.time / 1000 / step) * step, position: buy ? 'belowBar' : 'aboveBar',
        shape: buy ? 'arrowUp' : 'arrowDown', color: MODE_COLOR[m.mode] || '#fff',
        text: `${(m.mode || '').toUpperCase()} ${buy ? 'BUY' : 'SELL'} ${Number(m.price).toPrecision(6)}` };
    });
    ms.sort((a, b) => a.time - b.time);
    this.markersApi.setMarkers(ms);
  }
  _legend(p) {
    if (!this.legend || !this.data || !this.data.c.length) return;
    let i = this.data.c.length - 1;
    if (p && p.time) { const idx = this.data.t.findIndex(x => Math.floor(x / 1000) === p.time); if (idx >= 0) i = idx; }
    const d = this.data;
    const chg = d.o[i] ? (d.c[i] / d.o[i] - 1) * 100 : 0;
    this.legend.textContent = `O ${fmt(d.o[i])}  H ${fmt(d.h[i])}  L ${fmt(d.l[i])}  C ${fmt(d.c[i])}  ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%  V ${fmt(d.v[i])}`;
  }
  destroy() { try { this.chart.remove(); } catch { /* ignore */ } }
}

export class LineChart {
  constructor(el, { color = '#a855f7', area = true, baseline = false, percent = false } = {}) {
    this.chart = LW.createChart(el, { ...THEME, autoSize: true, layout: { ...THEME.layout, attributionLogo: true }, rightPriceScale: { ...THEME.rightPriceScale } });
    if (baseline) {
      this.s = this.chart.addSeries(LW.BaselineSeries, { baseValue: { type: 'price', price: 0 }, topLineColor: '#22e39a', bottomLineColor: '#ff3b5c',
        topFillColor1: 'rgba(34,227,154,0.2)', topFillColor2: 'rgba(34,227,154,0.02)', bottomFillColor1: 'rgba(255,59,92,0.02)', bottomFillColor2: 'rgba(255,59,92,0.25)', lineWidth: 2 });
    } else if (area) {
      this.s = this.chart.addSeries(LW.AreaSeries, { lineColor: color, topColor: color + '55', bottomColor: color + '05', lineWidth: 2 });
    } else {
      this.s = this.chart.addSeries(LW.LineSeries, { color, lineWidth: 2 });
    }
    if (percent) this.s.applyOptions({ priceFormat: { type: 'custom', formatter: (v) => v.toFixed(2) + '%' } });
  }
  set(points, key = 'value') {
    const seen = new Set();
    const data = [];
    for (const p of points) {
      const t = Math.floor(p.ts / 1000);
      if (seen.has(t) || p[key] === null || p[key] === undefined) continue;
      seen.add(t); data.push({ time: t, value: p[key] });
    }
    this.s.setData(data);
    this.chart.timeScale().fitContent();
  }
  destroy() { try { this.chart.remove(); } catch { /* ignore */ } }
}

function fmt(x) {
  if (x === null || x === undefined) return '—';
  const a = Math.abs(x);
  if (a >= 1000) return x.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (a >= 1) return x.toFixed(4);
  return x.toPrecision(4);
}
