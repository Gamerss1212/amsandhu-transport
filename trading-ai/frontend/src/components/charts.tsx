import { useEffect, useRef, useState } from "react";
import {
  ColorType, CrosshairMode, LineStyle, PriceScaleMode, createChart,
  type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { fmt } from "../api";

// lightweight-charts draws in UTC; shift by the computer's offset so the axis reads local time.
const TZ = -new Date().getTimezoneOffset() * 60;
const t = (ms: number) => (Math.floor(ms / 1000) + TZ) as UTCTimestamp;

const base = (el: HTMLElement): IChartApi =>
  createChart(el, {
    autoSize: true,
    layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8792a6", fontSize: 11 },
    grid: { vertLines: { color: "rgba(34,44,61,0.55)" }, horzLines: { color: "rgba(34,44,61,0.55)" } },
    rightPriceScale: { borderColor: "#222c3d" },
    timeScale: { borderColor: "#222c3d", timeVisible: true, secondsVisible: false },
    crosshair: { mode: CrosshairMode.Normal },
  });

export type Bar = [number, number, number, number, number, number];   // ts ms, o, h, l, c, v
export type Fill = { ts: number; side: string; qty: string; price: string; environment: string };

export function PriceChart({ bars, fills, tfMs, simulated }: { bars: Bar[]; fills: Fill[]; tfMs: number; simulated: boolean }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candles = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const vol = useRef<ISeriesApi<"Histogram"> | null>(null);
  const [hover, setHover] = useState<Bar | null>(null);
  const lastFirst = useRef<number | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const c = base(el.current);
    candles.current = c.addCandlestickSeries({
      upColor: "#33c481", downColor: "#ff5d5d", borderVisible: false, wickUpColor: "#33c481", wickDownColor: "#ff5d5d",
    });
    vol.current = c.addHistogramSeries({ priceScaleId: "", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    vol.current.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    c.subscribeCrosshairMove((p) => {
      const d = p.seriesData.get(candles.current!) as any;
      if (!d || p.time === undefined) return setHover(null);
      const v = p.seriesData.get(vol.current!) as any;
      setHover([(Number(p.time) - TZ) * 1000, d.open, d.high, d.low, d.close, v?.value ?? 0]);
    });
    chart.current = c;
    return () => {
      c.remove();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    if (!candles.current || !vol.current) return;
    candles.current.setData(bars.map((b) => ({ time: t(b[0]), open: b[1], high: b[2], low: b[3], close: b[4] })));
    vol.current.setData(bars.map((b) => ({ time: t(b[0]), value: b[5], color: b[4] >= b[1] ? "rgba(51,196,129,0.35)" : "rgba(255,93,93,0.35)" })));
    const first = bars.length ? bars[0][0] : null;
    if (first !== lastFirst.current) chart.current?.timeScale().fitContent();
    lastFirst.current = first;
    // fills: snapped to the bar they happened in, sorted by time (the library needs both)
    if (bars.length) {
      const start = bars[0][0];
      const marks: SeriesMarker<Time>[] = fills
        .filter((f) => f.ts >= start)
        .map((f) => {
          const barTs = Math.floor(f.ts / tfMs) * tfMs;
          const buy = f.side === "buy";
          return {
            time: t(barTs), position: buy ? "belowBar" : "aboveBar", color: buy ? "#4cc2ff" : "#f2b33d",
            shape: buy ? "arrowUp" : "arrowDown", text: `${buy ? "B" : "S"} ${fmt.num(f.qty, 4)}`,
          } as SeriesMarker<Time>;
        })
        .sort((a, b) => Number(a.time) - Number(b.time));
      candles.current.setMarkers(marks);
    }
  }, [bars, fills, tfMs]);

  const last = hover ?? bars[bars.length - 1];
  return (
    <div className="chartbox">
      <div className="chart-legend mono">
        {last ? <>
          {fmt.datetime(last[0])} · O {fmt.num(last[1], 6)} H {fmt.num(last[2], 6)} L {fmt.num(last[3], 6)} C {fmt.num(last[4], 6)} · V {fmt.num(last[5], 2)}
          {simulated && <span style={{ color: "var(--sim)", marginLeft: 8 }}>SIMULATED PRICES</span>}
        </> : "no completed bars yet"}
      </div>
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
    </div>
  );
}

const uniq = (pts: [number, number][]) => {
  const seen = new Set<number>();
  return pts.filter(([ts]) => !seen.has(ts) && seen.add(ts)).map(([ts, v]) => ({ time: t(ts), value: v }));
};

// One equity line, plus an optional benchmark line drawn from the same result (never invented here).
export function EquityChart({ points, start, height = 220, bench, labels, log }: {
  points: [number, number][]; start?: number; height?: number; bench?: [number, number][]; labels?: [string, string]; log?: boolean;
}) {
  const el = useRef<HTMLDivElement>(null);
  const two = !!bench?.length;
  useEffect(() => {
    if (!el.current || !points.length) return;
    const c = base(el.current);
    if (log) c.priceScale("right").applyOptions({ mode: PriceScaleMode.Logarithmic });
    const s = c.addAreaSeries({
      lineColor: "#4cc2ff", topColor: "rgba(76,194,255,0.22)", bottomColor: "rgba(76,194,255,0.0)", lineWidth: 2,
      priceLineVisible: false,
    });
    s.setData(uniq(points));
    if (bench?.length) {
      const b = c.addLineSeries({ color: "#c9a2ff", lineWidth: 2, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true });
      b.setData(uniq(bench));
    }
    if (start !== undefined) s.createPriceLine({ price: start, color: "#6f7b90", lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: "start" });
    c.timeScale().fitContent();
    return () => c.remove();
  }, [points, start, bench, log]);
  if (!points.length) return <div className="empty">No equity curve in this result.</div>;
  return (
    <div>
      {two && (
        <div className="row tiny dim" style={{ gap: 14, padding: "6px 10px 0" }}>
          <span className="row" style={{ gap: 6 }}><span style={{ width: 14, height: 2, background: "#4cc2ff", display: "inline-block" }} />{labels?.[0] ?? "Strategy"}</span>
          <span className="row" style={{ gap: 6 }}><span style={{ width: 14, height: 0, borderTop: "2px dashed #c9a2ff", display: "inline-block" }} />{labels?.[1] ?? "Benchmark"}</span>
        </div>
      )}
      <div ref={el} style={{ height, position: "relative" }} />
    </div>
  );
}
