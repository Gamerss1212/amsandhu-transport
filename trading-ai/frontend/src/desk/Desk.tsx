import { useEffect, useState } from "react";
import { fmt } from "../api";
import { JarvisRequests } from "../components/JarvisRequests";
import { usePoll } from "../store";
import { Dome } from "./Dome";

/* Page 1: the JARVIS desk. One read (/api/desk) every 3 seconds; every number below comes from it. */

const n = (v: any): number | null => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));
const sym = (iid: string) => (iid.includes(":") ? iid.split(":")[1] : iid).replace(/-USD$/, "");
const hhmm = (ms: number) => new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
const clock = (s: number | null) => {
  if (s === null) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
};
const mmss = (s: number) => (s >= 3600 ? clock(s) : `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`);

function Seg({ have, of, good }: { have: number; of: number; good?: boolean }) {
  const on = of ? Math.round((have / of) * 8) : 0;
  return <span className={`seg ${good ? "g" : ""}`}>{Array.from({ length: 8 }, (_, i) => <span key={i} className={i < on ? "on" : ""} />)}</span>;
}

function Chart({ pts, up }: { pts: number[][]; up: boolean }) {
  if (pts.length < 2) return <div className="empty">Balance history appears after the first few minutes.</div>;
  const W = 1000, H = 150, P = 26;
  const ys = pts.map((p) => p[1]), t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  const lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || Math.max(1, hi * 0.001);
  const X = (t: number) => P + ((t - t0) / (t1 - t0 || 1)) * (W - 2 * P);
  const Y = (v: number) => H - 18 - ((v - lo) / span) * (H - 40);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join(" ");
  const col = up ? "var(--teal)" : "var(--red)";
  const ticks = [lo, (lo + hi) / 2, hi];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Balance history">
      <g className="grid">{ticks.map((v, i) => <g key={i}><line x1={P} x2={W - P} y1={Y(v)} y2={Y(v)} /><text x={P} y={Y(v) - 3}>{fmt.money(v, "USD", 0)}</text></g>)}</g>
      <path className="ln" d={d} stroke={col} style={{ filter: `drop-shadow(0 0 4px ${up ? "#22c3a6" : "#ff4b55"})` }} />
      <circle className="mk" cx={X(t0)} cy={Y(pts[0][1])} r="4" stroke="#ececf1" />
      <circle className="mk" cx={X(t1)} cy={Y(pts[pts.length - 1][1])} r="4" stroke={col} />
      <text className="tag" x={X(t0) + 8} y={Y(pts[0][1]) - 8}>{fmt.money(pts[0][1])}</text>
      <text className="tag" x={X(t1) - 8} y={Y(pts[pts.length - 1][1]) - 8} textAnchor="end">{fmt.money(pts[pts.length - 1][1])}</text>
      <text className="tag" x={P} y={H - 2} fill="#55556a">{fmt.datetime(t0)}</text>
      <text className="tag" x={W - P} y={H - 2} textAnchor="end" fill="#55556a">now</text>
    </svg>
  );
}

export default function Desk() {
  const [d] = usePoll<any>("/api/desk", 3000);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const i = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(i); }, []);
  if (!d) return <div className="dk-main"><div className="empty">Loading the desk…</div></div>;

  const net = n(d.net_pnl);
  const bal = n(d.balance);
  const down = net !== null && net < 0;
  const ctl = d.control?.state ?? "—";
  const ctlCls = ctl === "OPEN" ? "grn" : ctl === "BLOCKED" || ctl === "STOPPED" ? "red" : "amb";
  const tint = ctl === "OPEN" ? "#22c3a6" : ctl === "BLOCKED" ? "#ff4b55" : "#ff4b55";
  const decs: any[] = d.decisions ?? [];
  const pipe = decs.slice(0, 4);
  const tags = Array.from(new Set([...(d.positions ?? []).map((p: any) => p.instrument_id), ...decs.map((x) => x.instrument)]))
    .slice(0, 6).map((iid: any) => { const x = decs.find((y) => y.instrument === iid); return `${x?.agent ? `#${x.agent} ` : ""}${sym(iid)}`; });
  const uptime = n(d.uptime_s) === null ? null : Number(d.uptime_s) + (now - d.ts) / 1000;
  const since = d.last_trade_ts ? (now - d.last_trade_ts) / 1000 : null;
  const hour = d.hour ?? {};
  const g = d.agents?.groups ?? {};
  const positions = (d.positions ?? []).filter((p: any) => Number(p.qty) !== 0);
  const tl = [...(d.timeline ?? [])];

  return (
    <div className="dk-main">
      <JarvisRequests />
      <section className="dk-kpis">
        <div className="dk-kpi"><div className="lab">Session balance / USD</div>
          <div className={`v ${down ? "red" : ""}`}>{fmt.money(bal)}</div>
          <div className="s">Start {fmt.money(d.contributed)}{d.simulated ? " · paper (simulated)" : " · live"}</div></div>
        <div className="dk-kpi"><div className="lab">Net PnL / USD</div>
          <div className={`v ${net === null ? "" : down ? "red" : net > 0 ? "grn" : ""}`}>{net === null ? "—" : `${net > 0 ? "+" : net < 0 ? "−" : ""}${fmt.money(Math.abs(net))}`}</div>
          <div className="s">Today {fmt.signed(d.day_pnl)} · fees {fmt.money(d.fees)}</div></div>
        <div className="dk-kpi"><div className="lab">Session clock</div>
          <div className="v">{uptime === null ? "—" : mmss(uptime)}</div>
          <div className="s">One line: "{d.doing ?? "—"}"</div></div>
      </section>

      <section className="dk-box">
        <div className="t"><span className="lab">Decision pipeline / active cycles</span><span className="lab">Read → Gate → Execute</span></div>
        {!pipe.length ? <div className="empty">No decisions yet. They appear here as each agent reads its market.</div> : (
          <div className="dk-pipe">
            {(["READ", "GATE", "EXECUTE"] as const).map((row) => (
              <div key={row} style={{ display: "contents" }}>
                <span className="row">{row}</span>
                {[0, 1, 2, 3].map((i) => {
                  const x = pipe[i];
                  if (!x) return <span key={i} className={`cell n c${i + 1}`}>—</span>;
                  const ok = !!x.order, hold = x.outcome === "HOLD";
                  const text = row === "READ" ? `${x.agent ?? ""} ${sym(x.instrument)}.${x.tf}` : row === "GATE" ? `${x.outcome.toLowerCase()}: ${x.reason ?? ""}` : ok ? `order.${String(x.order).toLowerCase()}` : "—";
                  const cls = row === "READ" ? "" : row === "GATE" ? (ok ? "g" : hold ? "p" : "r") : ok ? "g" : "n";
                  return <span key={i} className={`cell ${cls} c${i + 1}`} title={text}>{text}</span>;
                })}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="dk-mid">
        <div className="dk-col">
          <div className="lab">Session / today</div>
          <div className="dk-tl">
            {tl.map((e: any, i: number) => (
              <div key={i} className={`ev ${e.kind ?? ""}`}><div className="tm">{hhmm(e.ts)}</div><div className="lb">{e.label}</div></div>
            ))}
            <div className={`ev now`}><div className="tm">{hhmm(now)}</div><div className="lb">{ctl.toLowerCase()} · {d.control?.why}</div></div>
          </div>
        </div>

        <div className="dk-box dk-dome">
          <div className="t"><span className="lab">Agent matrix / live markets</span><span className={`lab ${ctlCls}`}>{ctl}</span></div>
          <Dome tags={tags} tint={tint} />
          <div className="story">
            <div className="lab red">Last hour · {hour.decisions ?? 0} decisions · {hour.entries ?? 0} entries</div>
            <b>{hour.entries ? `${hour.entries} trade${hour.entries === 1 ? "" : "s"} taken` : hour.decisions ? "Watching, not entering" : "Waiting for data"}</b>
            <p>{hour.entries ? "Every entry passed the strategy gate and the risk checks." : hour.top_refusal ? `Most common reason: ${hour.top_refusal}.` : d.control?.why}</p>
          </div>
        </div>

        <div className="dk-col">
          <div className="dk-box hot">
            <div className="t"><span className="lab">Entry checks · risk</span></div>
            <div className="chk"><span>Strategy qualified</span><Seg have={d.checks?.qualified?.[0] ?? 0} of={d.checks?.qualified?.[1] ?? 0} /></div>
            <div className="chk"><span>Data fresh</span><Seg have={d.checks?.fresh_data?.[0] ?? 0} of={d.checks?.fresh_data?.[1] ?? 0} /></div>
            <div className="chk"><span>Signals agree</span>{d.checks?.signals_agree ? <Seg have={d.checks.signals_agree[0]} of={d.checks.signals_agree[1]} /> : <span className="empty">—</span>}</div>
          </div>
          <div className="dk-box">
            <div className="t"><span className="lab">Position control · risk</span></div>
            <div className={`ctl ${ctlCls}`}>{ctl}</div>
            <div className="ctl-sub">Daily loss {d.day_loss === null ? "—" : fmt.pct(Math.max(0, d.day_loss), 2)} of {fmt.pct(d.day_loss_limit, 0)} limit<br />Limits enforced by code · no revenge entries</div>
          </div>
          <div className="dk-box">
            <div className="t"><span className="lab">Decision log</span></div>
            <div className="log">
              {!decs.length ? <div className="empty">Empty.</div> : decs.slice(0, 12).map((x) => (
                <div className="l" key={x.id}>
                  <span className="who">{x.agent ?? "BRAIN"}</span>
                  <span className={x.order ? "ok" : "x"}>{x.order ? "✓" : "✕"}</span>
                  <span className={x.order ? "ok" : "x"}>{sym(x.instrument)} · {x.order ? `order ${String(x.order).toLowerCase()}` : (x.reason ?? x.outcome).toLowerCase()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="dk-box dk-chart">
        <div className="t"><span className="lab">Balance history / USD · 7 days</span><span className={`lab ${down ? "red" : "grn"}`}>{fmt.money(d.contributed)} → {fmt.money(bal)}</span></div>
        <Chart pts={d.equity ?? []} up={!down} />
      </section>

      <section className="dk-bottom">
        <div className="dk-box">
          <div className="t"><span className="lab">Positions · holding</span><span className="lab">{positions.length || ""}</span></div>
          {!positions.length ? <div className="empty">No open positions.</div> : positions.slice(0, 6).map((p: any) => {
            const px = n(p.price) ?? n(p.avg_price) ?? 0, val = Math.abs(Number(p.qty) * px * (n(p.multiplier) ?? 1)), u = n(p.unrealized);
            return (
              <div className="pos" key={p.instrument_id}>
                <div><div className="n">{sym(p.instrument_id)}</div><div className="q">{fmt.num(p.qty, 6)} @ {fmt.price(p.avg_price)}</div></div>
                <div className="v">{fmt.money(val)}<small className={u === null ? "" : u >= 0 ? "grn" : "red"}>{u === null ? "—" : fmt.signed(u)}</small></div>
              </div>
            );
          })}
        </div>
        <div className="dk-box">
          <div className="t"><span className="lab">Trades · filled</span><span className="lab">{d.trades_today ?? 0} today</span></div>
          {!(d.fills ?? []).length ? <div className="empty">No trades yet.</div> : d.fills.slice(0, 6).map((f: any, i: number) => (
            <div className="pos" key={f.fill_id ?? i}>
              <div className="n"><span className={`side ${f.side}`}>{String(f.side).toUpperCase()}</span>{sym(f.instrument_id)}</div>
              <div className="v mono" style={{ fontSize: 11 }}>{fmt.num(f.qty, 6)} @ {fmt.price(f.price)}<small style={{ color: "var(--mute)" }}>{hhmm(Number(f.ts))}</small></div>
            </div>
          ))}
          <div className="pos"><div className="q">Earned (closed) · open</div><div className="v mono" style={{ fontSize: 11 }}>{fmt.signed(d.realized)} · {fmt.signed(d.unrealized)}</div></div>
        </div>
        <div className="dk-box">
          <div className="t"><span className="lab">Agents / roles</span><span className="lab">{d.agents?.running ?? 0}/{d.agents?.target ?? 0}</span></div>
          <div className="role"><i style={{ background: "var(--purple)" }} /><div><b>BRAIN</b><small>assigns, trains, promotes</small></div><span className="c">100 agents</span></div>
          <div className="role"><i style={{ background: "var(--amber)" }} /><div><b>RISK</b><small>last word before money</small></div><span className="c">{d.risk_counters?.denied ?? 0} vetoes</span></div>
          <div className="role"><i style={{ background: "var(--teal)" }} /><div><b>EXECUTION</b><small>the only one that trades</small></div><span className="c">{d.agents?.eligible ?? 0} cleared</span></div>
          <div className="q mono" style={{ fontSize: 10, color: "var(--mute)", marginTop: 6 }}>
            crypto {g.crypto?.active ?? 0}/{g.crypto?.target ?? 0} · meme {g.meme?.active ?? 0}/{g.meme?.target ?? 0} · stocks {g.stock?.active ?? 0}/{g.stock?.target ?? 0}
          </div>
        </div>
        <div className={`dk-box ${since === null || since > 3600 ? "hot" : ""}`}>
          <div className="t"><span className="lab">Since last trade</span></div>
          <div className={`clock ${since === null ? "" : "red"}`}>{since === null ? "—" : mmss(since)}</div>
          <div className="ctl-sub">{since === null ? "no trade yet" : "of no new fills"} · balance {fmt.money(bal)}</div>
          <div className="bar32" title={`${hour.decisions ?? 0} decisions in the last hour`}>
            {Array.from({ length: 32 }, (_, i) => <span key={i} className={i < Math.min(32, hour.decisions ?? 0) ? "on" : ""} />)}
          </div>
          <div className="ctl-sub" style={{ marginTop: 6 }}>Every entry, every veto, in the log</div>
        </div>
      </section>
    </div>
  );
}
