import { useEffect, useState } from "react";
import { fmt, tone } from "../api";
import { go } from "../App";
import { useLive, usePoll } from "../store";
import { Badge, Card, Empty } from "./ui";

// Page 1 pieces in the order of specification section 8A: market strip, KPI strip, engine summary, decision activity,
// execution stream and the agent strip. Every figure is read from the server; a missing value shows as a dash.

// ---------------------------------------------------------------- 2. market strip (pausable, no continuous motion)
export function MarketStrip() {
  const [paused, setPaused] = useState(false);
  const [s] = usePoll<any>("/api/market/strip", paused ? 0 : 15000, [paused]);
  const items: any[] = s?.items ?? [];
  return (
    <div className="mstrip" aria-label="Market strip">
      <button className="btn sm ghost" onClick={() => setPaused((p) => !p)} aria-pressed={paused} title="Stop or resume refreshing these prices">
        {paused ? "▶ Resume" : "❚❚ Pause"}
      </button>
      <div className="mstrip-items">
        {!s ? <span className="tiny muted">Loading prices…</span> : !items.length ? <span className="tiny muted">No prices yet: the shared market snapshot arrives about a minute after start.</span> : items.map((it) => {
          const up = it.change !== null && it.change > 0, down = it.change !== null && it.change < 0;
          return (
            <div key={it.instrument_id} className="mitem" title={`${it.source} · change vs ${it.basis} · as of ${fmt.datetime(it.as_of)}`}>
              <span className={`fdot ${it.fresh ? "ok" : "stale"}`} aria-label={it.fresh ? "fresh" : "stale"} />
              <b>{it.label}</b>
              {it.meme && <Badge kind="info">meme</Badge>}
              <span className="mono">{fmt.price(it.price)}</span>
              <span className={`mono ${up ? "pos" : down ? "neg" : "muted"}`}>{it.change === null ? "—" : `${up ? "▲" : down ? "▼" : ""}${(Math.abs(it.change) * 100).toFixed(2)}%`}</span>
              <span className="tiny muted">{it.basis}{it.simulated ? " · sim" : ""}</span>
            </div>
          );
        })}
      </div>
      {paused && <span className="tiny muted">paused</span>}
    </div>
  );
}

// ---------------------------------------------------------------- 3. KPI strip
export function readiness(o: any, ap: any): { label: string; kind: "good" | "warn" | "bad" | "info" | ""; why: string } {
  if (o.risk?.kill_switch) return { label: "Stopped", kind: "bad", why: "STOP ALL TRADING is engaged" };
  if (o.risk?.trading_locked) return { label: "Locked", kind: "bad", why: o.risk.trading_locked.reason };
  if (o.state?.state === "RECONCILIATION_REQUIRED") return { label: "Blocked", kind: "bad", why: "reconciliation required" };
  if (o.risk?.entries_paused) return { label: "Entries paused", kind: "warn", why: "exits and position management continue" };
  if (!o.autopilot?.enabled) return { label: "Stopped", kind: "", why: "press Start System" };
  const running = o.bots.filter((b: any) => b.state === "running").length;
  if (running) return { label: o.mode === "live" ? "Trading (live)" : "Trading (paper)", kind: "good", why: `${running} qualified bot(s) running` };
  return { label: "Waiting in cash", kind: "info", why: `${ap?.candidates?.length ?? 0} strategy(ies) qualified; research continues automatically` };
}

export function KpiStrip() {
  const live = useLive();
  const o = live.overview!;
  const a = live.account;
  const acct = a?.account;
  const ccy = acct?.currency ?? "USD";
  const [risk] = usePoll<any>("/api/risk", 10000);
  const [fleet] = usePoll<any>("/api/fleet/summary", 10000);
  const [ap] = usePoll<any>("/api/autopilot", 10000);
  const net = a ? Number(a.realized) + Number(a.unrealized) - Number(a.fees) : null;
  const gross = risk?.usage?.gross_exposure !== null && risk?.usage?.gross_exposure !== undefined ? risk.usage.gross_exposure * risk.limits.max_gross_exposure : null;
  const r = readiness(o, ap);
  const c = fleet?.counts;
  return (
    <div className="stats kpis">
      <div className="stat"><div className="k">Equity</div><div className="v">{fmt.money(acct?.equity, ccy)}</div><div className="s"><Badge kind={acct?.simulated ? "sim" : "bad"}>{a?.badge ?? "—"}</Badge></div></div>
      <div className="stat" title="Realized plus unrealized, minus fees. Deposits, withdrawals and paper balance changes are not trading results."><div className="k">Net P&amp;L</div>
        <div className={`v ${tone(net)}`}>{net === null || !Number.isFinite(net) ? "—" : fmt.signed(net, ccy)}</div><div className="s">trading only · fees {fmt.money(a?.fees, ccy)}</div></div>
      <div className="stat" title="Gross open notional divided by equity"><div className="k">Exposure</div><div className="v">{gross === null ? "—" : `${(gross * 100).toFixed(1)}%`}</div><div className="s">{a?.positions?.length ?? 0} position(s) · {a?.open_orders?.length ?? 0} order(s)</div></div>
      <div className="stat" title="Fall from the highest recorded equity"><div className="k">Drawdown</div><div className="v">{fmt.pct(a?.drawdown)}</div><div className="s">from the equity peak</div></div>
      <div className="stat" title="Agents whose own market sent fresh data, out of agents with a distinct market"><div className="k">Agent availability</div>
        <div className="v">{c ? `${c.data_ready}/${c.assigned}` : "—"}</div><div className="s">{c ? `fresh data · ${c.registered} agents, ${c.blocked} blocked` : "loading"}</div></div>
      <div className="stat"><div className="k">Trading readiness</div><div className="v"><Badge kind={r.kind} dot>{r.label}</Badge></div><div className="s">{r.why}</div></div>
    </div>
  );
}

// ---------------------------------------------------------------- 4 (left). coordinated-engine summary
export function EngineSummary({ decision, iid }: { decision: any; iid: string }) {
  const live = useLive();
  const o = live.overview!;
  const [fleet] = usePoll<any>("/api/fleet/summary", 10000);
  const [ap] = usePoll<any>("/api/autopilot", 10000);
  const r = readiness(o, ap);
  const bots = o.bots.filter((b) => b.state === "running");
  const reg = decision?.regime;
  const c = fleet?.counts;
  return (
    <Card title="Coordinated engine" sub="what the system is doing now" right={<button className="btn sm ghost" onClick={() => go("/intelligence")}>Agent activity →</button>}>
      <div className="engine">
        <div className="vortex" aria-hidden>
          <svg viewBox="0 0 200 200">
            <defs>
              <radialGradient id="vx" cx="50%" cy="50%" r="50%"><stop offset="0%" stopColor="#3dd9ff" stopOpacity="0.45" /><stop offset="70%" stopColor="#a78bfa" stopOpacity="0.12" /><stop offset="100%" stopColor="#a78bfa" stopOpacity="0" /></radialGradient>
            </defs>
            <circle cx="100" cy="100" r="96" fill="url(#vx)" />
            <g className="vx-ring"><ellipse cx="100" cy="100" rx="80" ry="34" fill="none" stroke="#3dd9ff" strokeOpacity="0.45" /></g>
            <g className="vx-ring r2"><ellipse cx="100" cy="100" rx="64" ry="26" fill="none" stroke="#a78bfa" strokeOpacity="0.6" /></g>
            <g className="vx-ring r3"><ellipse cx="100" cy="100" rx="44" ry="18" fill="none" stroke="#f08cda" strokeOpacity="0.5" /></g>
            <circle cx="100" cy="100" r="26" fill="#101a2b" stroke="#a78bfa" strokeWidth="2" />
            <text x="100" y="98" textAnchor="middle" fontSize="15" fontWeight="700" fill="#f2f6ff">{c ? c.assigned : "—"}</text>
            <text x="100" y="112" textAnchor="middle" fontSize="8" fill="#a9b8ce">markets</text>
          </svg>
          <div className="tiny muted center">animation is decoration only; numbers are measured</div>
        </div>
        <div className="col" style={{ gap: 8, minWidth: 0 }}>
          <div className="row wrap"><Badge kind={r.kind} dot>{r.label}</Badge><span className="small dim">{r.why}</span></div>
          <div className="small"><b>Now:</b> <span className="dim">{o.autopilot?.enabled ? o.autopilot.doing : "the autopilot is off"}</span></div>
          <div className="kv small">
            <div>Agents</div><div>{c ? `${c.assigned} with a market · ${c.data_ready} fresh data · ${c.market_closed} in closed markets · ${c.blocked} blocked` : "—"}</div>
            <div>Research</div><div>{ap ? `${ap.counts.screened} screened · ${ap.counts.confirmed} full tests · ${ap.candidates?.length ?? 0} qualified` : "—"}</div>
            <div>Active strategies</div><div>{bots.length ? bots.map((b) => `${b.strategy_id} on ${b.instrument_id}`).join(" · ") : "none (no strategy has qualified, so nothing trades)"}</div>
            <div>Regime</div><div>{iid}: {reg ? `${reg.trend} · ${reg.volatility} volatility · ${reg.character}` : "no decision on this market yet"}</div>
            <div>Operating mode</div><div><DayRules /></div>
            <div>Meme coins</div><div>{o.offline ? "discovery off (offline mode)" : <MemeLine />}</div>
            <div>Mode</div><div>{o.mode === "live" ? "LIVE (real money)" : o.mode === "shadow" ? "Shadow (orders recorded, not sent)" : "Paper (simulated money)"}</div>
          </div>
        </div>
      </div>
    </Card>
  );
}

function DayRules() {
  const [d] = usePoll<any>("/api/daytrade", 0);
  if (!d) return <>—</>;
  const tip = Object.entries(d.rules).map(([k, r]: any) => `${k} (${r.timezone}): entries ${r.entry_window}; flat ${r.flatten}`).join("\n");
  return <span title={`${tip}\n${d.note}`}>Intraday: stocks flat 10 min before the close, futures and forex before 17:00 New York, crypto held 24 h at most <span className="muted">(hover for all rules)</span></span>;
}

function MemeLine() {
  const [d] = usePoll<any>("/api/coverage/discovery", 60000);
  if (!d) return <>—</>;
  const p = d.meme.pairs;
  return <>{p.length} tagged pair(s) on {Object.keys(d.venues).length} venues · {p.filter((m: any) => m.execution_eligible).length} paper-tradable · tags unverified</>;
}

// ---------------------------------------------------------------- 5. measured decision activity
const OUT_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = { ORDER: "good", HOLD: "info", NO_TRADE: "", RISK_REJECT: "bad" };

export function DecisionActivity() {
  const [d] = usePoll<any>("/api/activity?minutes=60", 15000);
  if (!d) return <Card title="Decision activity"><Empty>Loading…</Empty></Card>;
  const max = Math.max(1, ...d.per_bucket);
  return (
    <Card title="Decision activity" sub="last 60 minutes, from the decision log">
      <div className="col" style={{ gap: 8 }}>
        <div className="row wrap">
          <b className="mono" style={{ fontSize: 20 }}>{d.decisions}</b><span className="small dim">decisions</span>
          {Object.entries(d.by_outcome).map(([k, n]: any) => <Badge key={k} kind={OUT_KIND[k] ?? ""}>{k.replace("_", " ")} {n}</Badge>)}
        </div>
        <svg viewBox="0 0 240 48" className="spark" role="img" aria-label={`decisions per 5 minutes: ${d.per_bucket.join(", ")}`}>
          {d.per_bucket.map((n: number, i: number) => <rect key={i} x={i * 20 + 2} y={46 - (n / max) * 42} width={16} height={Math.max(1, (n / max) * 42)} rx={2} fill={n ? "#3dd9ff" : "#2a3b55"} />)}
        </svg>
        <div className="kv small">
          <div title={d.definitions.abstention}>Abstention</div><div className="mono">{d.abstention === null ? "—" : fmt.pct(d.abstention, 0)}</div>
          <div title={d.definitions.disagreement}>Signal disagreement</div><div className="mono">{d.disagreement === null ? "—" : fmt.pct(d.disagreement, 0)}</div>
          <div title={d.definitions.latency}>Decision latency</div><div className="mono">{d.latency_ms.p50 === null ? "—" : `p50 ${d.latency_ms.p50} ms`}{d.latency_ms.p95 !== null ? ` · p95 ${d.latency_ms.p95} ms` : ""}</div>
        </div>
        {!d.decisions && <div className="note">Decisions are made only by bots running a qualified strategy; none ran in this window.</div>}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- 5. confirmed execution stream
export function ExecutionStream() {
  const live = useLive();
  const fills: any[] = live.account?.fills ?? [];
  const paper = live.account?.mode !== "live";
  return (
    <Card title="Execution stream" sub={paper ? "confirmed paper fills (simulated)" : "confirmed broker fills"} flush>
      {!fills.length ? <Empty>No fills yet. A fill appears here only when the {paper ? "paper broker" : "broker"} confirms it.</Empty> : (
        <div className="scroll" style={{ maxHeight: 250 }}>
          <table className="t small">
            <thead><tr><th>Time</th><th>Side</th><th>Instrument</th><th className="num">Qty</th><th className="num">Price</th><th className="num">Fee</th></tr></thead>
            <tbody>{fills.map((f) => (
              <tr key={f.fill_id}><td className="nowrap mono">{fmt.time(f.ts)}</td><td><Badge kind={f.side === "buy" ? "info" : "warn"}>{f.side}</Badge></td>
                <td className="mono tiny">{f.instrument_id}</td><td className="num mono">{fmt.num(f.qty, 8)}</td><td className="num mono">{fmt.price(f.price)}</td><td className="num mono">{fmt.money(f.fee)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- 6. agent strip: one card per team, stable colors
const TEAM_COLOR: Record<string, string> = {
  equities: "#3dd9ff", crypto: "#f08cda", fx: "#7aa2ff", futures: "#ffb86b", options: "#9be7c4", rates: "#c3a6ff",
  specialty: "#8fd3ff", overflow: "#a9b8ce",
};
const TEAM_LABEL: Record<string, string> = {
  equities: "Equities", crypto: "Crypto", fx: "FX", futures: "Futures", options: "Options", rates: "Rates", specialty: "Specialty", overflow: "Overflow",
};

export function AgentStrip() {
  const [f] = usePoll<any>("/api/fleet/summary", 10000);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 10000); return () => window.clearInterval(t); }, []);
  if (!f) return null;
  return (
    <Card title="Trading agents" sub={`${f.counts.registered} configured (target ${f.counts.target}); one card per team. Health is the badge, not the color.`}
      right={<button className="btn sm" onClick={() => go("/intelligence")}>Open all {f.counts.registered} agents →</button>}>
      <div className="astrip">
        {f.groups.map((g: any) => {
          const top = Object.entries(g.jobs as Record<string, number>).filter(([j]) => j !== "idle").sort((a, b) => b[1] - a[1])[0];
          const kind = g.ready ? "good" : g.assigned ? "warn" : "";
          const stale = g.heartbeat && now - g.heartbeat > 60000;
          return (
            <button key={g.group} className="acard" style={{ borderTopColor: TEAM_COLOR[g.group] }} onClick={() => go("/intelligence")}>
              <div className="spread"><b style={{ color: TEAM_COLOR[g.group] }}>{TEAM_LABEL[g.group] ?? g.group}</b>
                <Badge kind={stale ? "warn" : kind}>{stale ? "no heartbeat" : g.ready ? `${g.ready} fresh` : g.assigned ? `${g.assigned} assigned` : "no access"}</Badge></div>
              <div className="tiny muted mono">{g.ids}</div>
              <div className="abar" title={`${g.ready} fresh data · ${g.assigned - g.ready} assigned without fresh data · ${g.target - g.assigned} without a market`}>
                <i style={{ width: `${(g.ready / g.target) * 100}%`, background: "var(--good)" }} />
                <i style={{ width: `${((g.assigned - g.ready) / g.target) * 100}%`, background: "var(--warn)" }} />
              </div>
              <div className="tiny dim ell">{top ? `${top[1]} ${top[0]}` : "idle: no distinct market"}</div>
              {g.reassigned > 0 && <div className="tiny" style={{ color: "var(--warn)" }}>{g.reassigned} reassigned (gap kept)</div>}
            </button>
          );
        })}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- top bar: clock
export function Clock() {
  const [t, setT] = useState(() => new Date());
  useEffect(() => { const i = window.setInterval(() => setT(new Date()), 1000); return () => window.clearInterval(i); }, []);
  return <span className="mono small dim" title={Intl.DateTimeFormat().resolvedOptions().timeZone}>{t.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>;
}
