import { useEffect, useMemo, useState } from "react";
import { api, fmt, tone } from "../api";
import { PriceChart, type Bar, type Fill } from "../components/charts";
import { Badge, Card, Diverge, Empty, Meter, Modal, PhraseConfirm, Stat } from "../components/ui";
import { useLive, usePoll } from "../store";
import { go } from "../App";
import StrategyLab from "./StrategyLab";
import { CatalogCard } from "./Catalog";
import { EquityChart } from "../components/charts";
import { Drawer } from "../components/ui";

export type Instrument = {
  instrument_id: string; name: string; market: string; market_type: string; provider: string; symbol: string;
  note: string; timeframes: string[]; simulated: boolean; paper_tradable: boolean; why: string; currency: string;
};

const TF_MS: Record<string, number> = { "1m": 60e3, "5m": 300e3, "15m": 900e3, "30m": 1800e3, "1h": 3600e3, "4h": 14400e3, "1d": 86400e3 };
const TF_ORDER = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];
const MARKET_LABEL: Record<string, string> = { crypto: "Crypto", stock: "Stocks", etf: "ETFs", fx: "Forex", future: "Futures", index: "Indices (reference)" };

export function useInstruments() {
  const [list] = usePoll<Instrument[]>("/api/instruments", 0);
  return list ?? [];
}

export function InstrumentSelect({ value, onChange, list, tradableOnly }: {
  value: string; onChange: (v: string) => void; list: Instrument[]; tradableOnly?: boolean;
}) {
  const groups = useMemo(() => {
    const g: Record<string, Instrument[]> = {};
    for (const i of list) if (!tradableOnly || i.paper_tradable) (g[i.market] ??= []).push(i);
    return g;
  }, [list, tradableOnly]);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Instrument">
      {Object.entries(groups).map(([m, items]) => (
        <optgroup key={m} label={MARKET_LABEL[m] ?? m}>
          {items.map((i) => <option key={i.instrument_id} value={i.instrument_id}>{i.instrument_id}{i.simulated ? " (simulated)" : ""}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

export default function CommandCenter() {
  const live = useLive();
  const instruments = useInstruments();
  const [iid, setIid] = useState(() => {
    try { return localStorage.getItem("cc.iid") ?? (live.overview?.offline ? "DEMO:DEMO-TREND" : "COINBASE:BTC-USD"); }
    catch { return live.overview?.offline ? "DEMO:DEMO-TREND" : "COINBASE:BTC-USD"; }
  });
  const [tf, setTf] = useState(() => { try { return localStorage.getItem("cc.tf") ?? "5m"; } catch { return "5m"; } });
  const inst = instruments.find((i) => i.instrument_id === iid);
  const tfs = TF_ORDER.filter((t) => inst?.timeframes.includes(t));
  useEffect(() => {
    try { localStorage.setItem("cc.iid", iid); localStorage.setItem("cc.tf", tf); } catch { /* private window */ }
  }, [iid, tf]);
  useEffect(() => {
    if (inst && !inst.timeframes.includes(tf)) setTf(inst.timeframes.includes("1h") ? "1h" : inst.timeframes[0]);
  }, [inst, tf]);
  const [chart, , chartErr] = usePoll<any>(inst ? `/api/chart?instrument=${encodeURIComponent(iid)}&tf=${tf}&n=300` : null, 5000, [iid, tf]);
  const a = live.account;
  const acct = a?.account;
  const ccy = acct?.currency ?? "USD";
  const lastDecision = live.decisions.find((d) => d.instrument === iid);

  return (
    <>
      <div className="stats">
        <Stat k="Equity" v={fmt.money(acct?.equity, ccy)} s={<Badge kind={acct?.simulated ? "sim" : "bad"}>{a?.badge ?? "—"}</Badge>} />
        <Stat k="Cash" v={fmt.money(acct?.cash, ccy)} s={`buying power ${fmt.money(acct?.buying_power, ccy)}`} />
        <Stat k="Today P&L" v={fmt.signed(a?.day_pnl, ccy)} cls={tone(a?.day_pnl)} s="vs equity at the day's first check" />
        <Stat k="Realized" v={fmt.signed(a?.realized, ccy)} cls={tone(a?.realized)} s={`closed trades, before ${fmt.money(a?.fees, ccy)} fees`} />
        <Stat k="Unrealized" v={fmt.signed(a?.unrealized, ccy)} cls={tone(a?.unrealized)} s="marked at the newest completed bar" />
        <Stat k="Drawdown" v={fmt.pct(a?.drawdown)} s="from the equity peak" />
        <Stat k="Trades today" v={a?.trades_today ?? "—"} s={`${live.overview?.bots.filter((b) => b.state === "running").length ?? 0} bot(s) running`} />
      </div>

      <div className="grid g-main">
        <div className="col" style={{ gap: 14, minWidth: 0 }}>
          <Card title="Market" right={
            <div className="row wrap">
              <InstrumentSelect value={iid} onChange={setIid} list={instruments} />
              <div className="seg" role="group" aria-label="Timeframe">
                {tfs.map((t) => <button key={t} className={t === tf ? "on" : ""} onClick={() => setTf(t)}>{t}</button>)}
              </div>
            </div>
          } flush>
            {chartErr && <div className="callout bad" style={{ margin: 12 }}>{chartErr}</div>}
            {chart && chart.instrument === iid && chart.tf === tf
              ? <PriceChart bars={chart.bars as Bar[]} fills={chart.fills as Fill[]} tfMs={TF_MS[tf]} simulated={chart.simulated} />
              : <div className="chartbox"><Empty>Loading {iid} {tf}…</Empty></div>}
            <div className="row wrap small" style={{ padding: "8px 14px", borderTop: "1px solid var(--line)" }}>
              <span className="dim">Source</span><b>{chart?.status?.provider ?? "—"}</b>
              {chart?.simulated ? <Badge kind="sim">SIMULATED</Badge> : chart?.status?.fresh ? <Badge kind="good">FRESH</Badge> : <Badge kind="warn">STALE / STORED</Badge>}
              {chart?.quality !== undefined && chart?.quality !== null && <span className="dim">quality {fmt.num(chart.quality, 0)}/100</span>}
              {chart?.status?.error && <span className="neg">{chart.status.error}</span>}
              <span className="grow" />
              <span className="muted tiny">{inst?.note}</span>
              <span className="muted tiny">Completed bars only · local time</span>
            </div>
          </Card>

          <EquityCard />
          <Positions />
          <CatalogCard />
          <StrategyLab instruments={instruments} defaultInstrument={iid} />
        </div>

        <div className="col" style={{ gap: 14, minWidth: 0 }}>
          <AutopilotCard />
          <BotControl instruments={instruments} iid={iid} tf={tf} />
          <RegimeAgents decision={lastDecision} iid={iid} />
          <RiskPanel />
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- autopilot
const AP_MARKETS: [string, string][] = [["crypto", "Crypto"], ["stock", "Stocks"], ["etf", "ETFs"], ["fx", "Forex"], ["future", "Futures"]];

function AutopilotCard() {
  const live = useLive();
  const [ap, reload] = usePoll<any>("/api/autopilot", 4000);
  const o = live.overview!;
  if (!ap) return <Card title="Autopilot"><Empty>Loading…</Empty></Card>;
  const cfg = ap.config;
  const set = async (changes: Record<string, unknown>, ok?: string) => {
    try {
      await api.post("/api/autopilot", changes);
      if (ok) live.toast(ok, "ok");
    } catch (e: any) {
      live.toast(e.message, "error");
    }
    reload();
    await live.refresh();
  };
  const autostart = o.autostart;
  return (
    <Card title="Autopilot" sub="fully automatic paper trading" right={
      <button className={`btn ${cfg.enabled ? "go" : ""}`} onClick={() => set({ enabled: !cfg.enabled }, cfg.enabled ? "Autopilot off" : "Autopilot on")}
        disabled={!cfg.enabled && !!o.risk.kill_switch}>{cfg.enabled ? "ON" : "OFF"}</button>
    }>
      <div className="col">
        <div className={`callout ${cfg.enabled ? "good" : ""} small`}>
          <b>{cfg.enabled ? "Now: " : "Autopilot is off. "}</b>{cfg.enabled ? ap.doing : "Press ON (or START BOT) and it researches, starts, watches and retires paper bots by itself."}
        </div>
        <div className="stats" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <Stat k="Strategies screened" v={ap.counts.screened} />
          <Stat k="Full tests" v={ap.counts.confirmed} />
          <Stat k="Bots running" v={`${ap.running} / ${cfg.max_bots}`} />
          <Stat k="Retired" v={ap.counts.retired_count} />
        </div>
        <div className="row wrap small">
          <label className="field" style={{ width: 120 }}>Max bots
            <select value={cfg.max_bots} onChange={(e) => set({ max_bots: Number(e.target.value) })}>
              {[1, 2, 3, 4, 6, 8, 10, 12].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="row small" style={{ gap: 6, marginTop: 16 }}>
            <input type="checkbox" checked={cfg.allow_probation} onChange={(e) => set({ allow_probation: e.target.checked })} />
            allow PROBATION bots
          </label>
        </div>
        <div className="row wrap small">
          {AP_MARKETS.map(([m, label]) => (
            <label key={m} className="row" style={{ gap: 5 }}>
              <input type="checkbox" checked={cfg.markets.includes(m)}
                onChange={(e) => set({ markets: e.target.checked ? [...cfg.markets, m] : cfg.markets.filter((x: string) => x !== m) })} />
              {label}
            </label>
          ))}
        </div>
        <label className="row small" style={{ gap: 6 }} title={autostart?.reason}>
          <input type="checkbox" disabled={!autostart?.supported} checked={!!autostart?.enabled}
            onChange={async (e) => {
              try {
                await api.post("/api/system/autostart", { enabled: e.target.checked });
                live.toast(e.target.checked ? "Trading AI will start when you sign in to Windows" : "Start with Windows turned off", "ok");
              } catch (err: any) {
                live.toast(err.message, "error");
              }
              await live.refresh();
            }} />
          Start automatically when Windows starts {!autostart?.supported && <span className="muted">(Windows program only)</span>}
        </label>
        {ap.candidates?.length > 0 && (
          <div className="col" style={{ gap: 4 }}>
            <div className="tiny muted">BEST RESEARCH RESULTS (deployed when a slot is free)</div>
            {ap.candidates.slice(0, 4).map((c: any) => (
              <div key={c.key} className="spread tiny">
                <span className="mono" style={{ wordBreak: "break-all" }}>{c.strategy_id} · {c.iid} {c.tf}</span>
                <Badge kind={c.tier === "qualified" ? "good" : "warn"}>{c.tier} {c.quality !== null ? Math.round(c.quality) : ""}</Badge>
              </div>
            ))}
          </div>
        )}
        {ap.activity?.length > 0 && (
          <div className="col" style={{ gap: 3 }}>
            <div className="tiny muted">RECENT</div>
            {ap.activity.slice(0, 6).map((a: any, i: number) => (
              <div key={i} className="tiny"><span className="muted mono">{fmt.time(a.ts)}</span> {a.message}</div>
            ))}
          </div>
        )}
        <div className="note">Paper only: it never trades real money, never changes risk limits, never re-arms after an emergency
          stop, and only chooses among the fixed strategy templates. PROBATION = did not pass every research gate; paper trading
          collects real out-of-sample evidence and it is retired automatically if results fall short.</div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- bots
function BotControl({ instruments, iid, tf }: { instruments: Instrument[]; iid: string; tf: string }) {
  const live = useLive();
  const o = live.overview!;
  const [adding, setAdding] = useState(false);
  const running = o.bots.filter((b) => b.state === "running").length;
  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn();
      if (ok) live.toast(ok, "ok");
    } catch (e: any) {
      live.toast(e.message, "error");
    }
    await live.refresh();
  };
  return (
    <Card title="Bots" sub={`${o.bots.length} configured · ${running} running`}>
      <div className="col">
        <div className="row">
          <button className="btn go big grow" disabled={!!o.risk.kill_switch || (!!o.autopilot?.enabled && running === o.bots.length)}
            onClick={() => act(() => api.post("/api/bot/start"), "Autopilot on, all bots running")}>START BOT</button>
          <button className="btn big grow" disabled={!running && !o.autopilot?.enabled} onClick={() => act(() => api.post("/api/bot/stop"), "All bots stopped, autopilot paused")}>STOP BOT</button>
        </div>
        <div className="spread">
          <span className="dim small">Mode</span>
          <div className="seg" role="group" aria-label="Mode">
            {(["paper", "shadow"] as const).map((m) => (
              <button key={m} className={o.mode === m ? "on" : ""} onClick={() => act(() => api.post("/api/mode", { mode: m }), `Mode: ${m.toUpperCase()}`)}>
                {m === "paper" ? "Paper" : "Shadow"}
              </button>
            ))}
            <button className={o.mode === "live" ? "on" : ""} onClick={() => go("/broker")} title="Live trading is armed on the Brokers & Accounts page">Live…</button>
          </div>
        </div>
        <div className="note">
          {o.mode === "paper" && "Paper: simulated orders and fills at real (or clearly labelled demo) prices. No real money."}
          {o.mode === "shadow" && "Shadow: real data, the full decision pipeline, orders recorded but never sent."}
          {o.mode === "live" && "LIVE: orders go to your broker with real money, within the caps you set when arming."}
        </div>
        <div className="note">START BOT turns the autopilot on and runs every bot. STOP BOT stops every bot and pauses the autopilot.</div>
        <Controls />
        {o.bots.length === 0 && <Empty>{o.autopilot?.enabled
          ? "No bots yet: the autopilot starts paper bots by itself as soon as its research finds strategies that pass the checks."
          : "No bots. Press START BOT to let the autopilot run, or add one yourself."}</Empty>}
        {o.bots.map((b) => (
          <div key={b.bot_id} className="card" style={{ background: "var(--panel-2)" }}>
            <div className="bd col" style={{ gap: 6 }}>
              <div className="spread">
                <b className="small">{b.instrument_id} · {b.tf}</b>
                <Badge kind={b.state === "running" ? "good" : b.state === "paused" || b.state === "retiring" ? "warn" : ""} dot>{b.state}</Badge>
              </div>
              {b.managed_by === "autopilot" && (
                <div className="row wrap">
                  <Badge kind="info">AUTOPILOT</Badge>
                  <Badge kind={b.tier === "qualified" ? "good" : "warn"}>{b.tier === "qualified" ? "QUALIFIED" : "PROBATION"}</Badge>
                </div>
              )}
              {b.note && <div className="tiny dim">{b.note}</div>}
              <div className="small dim mono" style={{ wordBreak: "break-all" }}>{b.strategy_id}{b.kind === "portfolio" ? ` · portfolio · ${Math.round((b.allocation ?? 0) * 100)}% of equity` : ""}</div>
              {b.kind === "portfolio" && b.pending && Object.keys(b.pending).length > 0 && (
                <div className="tiny warn" style={{ color: "var(--warn)" }}>rebalancing: {Object.entries(b.pending).map(([k, v]) => `${k.split(":")[1]} ${Math.round(Number(v) * 100)}%`).join(", ")} (waits for each market to open)</div>
              )}
              <div className="tiny muted">{b.signal_mode} · {b.risk_profile} risk · {b.trades_today}/{b.max_trades_per_day} trades today</div>
              <div className="row">
                {b.state !== "running"
                  ? <button className="btn sm go" disabled={!!o.risk.kill_switch} onClick={() => act(() => api.post(`/api/bots/${b.bot_id}/start`))}>Start</button>
                  : <button className="btn sm" onClick={() => act(() => api.post(`/api/bots/${b.bot_id}/pause`))}>Pause</button>}
                <button className="btn sm" disabled={b.state === "stopped"} onClick={() => act(() => api.post(`/api/bots/${b.bot_id}/stop`))}>Stop</button>
                <span className="grow" />
                <button className="btn sm ghost" disabled={b.state === "running"} onClick={() => act(() => api.post(`/api/bots/${b.bot_id}/delete`), "Bot deleted")}>Delete</button>
              </div>
            </div>
          </div>
        ))}
        <button className="btn" onClick={() => setAdding((v) => !v)}>{adding ? "Cancel" : "+ Add bot"}</button>
        {adding && <NewBot instruments={instruments} iid={iid} tf={tf} done={() => setAdding(false)} />}
      </div>
    </Card>
  );
}

export function StrategyPicker({ market, value, onChange, tf }: { market: string; value: string; onChange: (v: string) => void; tf?: string }) {
  const [q, setQ] = useState("");
  const [list] = usePoll<any[]>(`/api/strategies?market=${market}&q=${encodeURIComponent(q)}&limit=300`, 0, [market, q]);
  const shown = (list ?? []).filter((s) => !tf || !s.timeframes?.length || s.timeframes.includes(tf));
  useEffect(() => {
    if (shown.length && !shown.find((s) => s.strategy_id === value)) onChange(shown[0].strategy_id);
  }, [shown, value, onChange]);
  return (
    <div className="col" style={{ gap: 6 }}>
      <input placeholder="Search strategies (e.g. donchian, rsi, vwap)" value={q} onChange={(e) => setQ(e.target.value)} />
      <select value={value} onChange={(e) => onChange(e.target.value)} size={6} aria-label="Strategy">
        {shown.map((s) => <option key={s.strategy_id} value={s.strategy_id}>{s.strategy_id}{s.status?.status ? ` · ${s.status.status}` : ""}</option>)}
      </select>
      <span className="tiny muted">{shown.length} runnable template(s) shown{list && list.length >= 300 ? " (first 300: refine the search)" : ""}. Status = latest research verdict.</span>
    </div>
  );
}

function NewBot({ instruments, iid, tf, done }: { instruments: Instrument[]; iid: string; tf: string; done: () => void }) {
  const live = useLive();
  const [inst, setInst] = useState(iid);
  const [t, setT] = useState(tf);
  const [sid, setSid] = useState("");
  const [mode, setMode] = useState("strategy+ensemble");
  const [risk, setRisk] = useState("conservative");
  const [cap, setCap] = useState(10);
  const i = instruments.find((x) => x.instrument_id === inst);
  const [busy, setBusy] = useState(false);
  return (
    <div className="col" style={{ gap: 8 }}>
      <label className="field">Instrument<InstrumentSelect value={inst} onChange={setInst} list={instruments} tradableOnly /></label>
      {i && !i.paper_tradable && <div className="callout warn small">{i.why}</div>}
      <label className="field">Timeframe
        <select value={t} onChange={(e) => setT(e.target.value)}>{TF_ORDER.filter((x) => i?.timeframes.includes(x)).map((x) => <option key={x}>{x}</option>)}</select>
      </label>
      <label className="field">Strategy {i && <StrategyPicker market={i.market} value={sid} onChange={setSid} />}</label>
      <label className="field">Signal
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="strategy+ensemble">Strategy, unless the agents lean the other way</option>
          <option value="strategy">Strategy only (agent vetoes still apply)</option>
          <option value="ensemble">Agent ensemble decides</option>
        </select>
      </label>
      <div className="row">
        <label className="field grow">Risk per trade
          <select value={risk} onChange={(e) => setRisk(e.target.value)}>
            <option value="conservative">Conservative (0.25% of equity)</option>
            <option value="moderate">Moderate (0.5%)</option>
            <option value="aggressive">Aggressive (1%)</option>
          </select>
        </label>
        <label className="field" style={{ width: 110 }}>Max trades/day<input type="number" min={1} max={200} value={cap} onChange={(e) => setCap(Number(e.target.value))} /></label>
      </div>
      <button className="btn primary" disabled={!sid || busy} onClick={async () => {
        setBusy(true);
        try {
          await api.post("/api/bots", { instrument_id: inst, tf: t, strategy_id: sid, signal_mode: mode, risk_profile: risk, max_trades_per_day: cap });
          live.toast("Bot added (stopped). Press START BOT to run it.", "ok");
          await live.refresh();
          done();
        } catch (e: any) {
          live.toast(e.message, "error");
        } finally {
          setBusy(false);
        }
      }}>Add bot</button>
    </div>
  );
}

// ---------------------------------------------------------------- positions
function Positions() {
  const live = useLive();
  const a = live.account;
  const ccy = a?.account?.currency ?? "USD";
  return (
    <Card title="Positions" sub={a?.mode === "live" ? "from the broker" : "paper account (simulated)"} flush>
      {!a?.positions?.length ? <Empty>No open positions.</Empty> : (
        <div className="scroll">
          <table className="t">
            <thead><tr><th>Instrument</th><th className="num">Qty</th><th className="num">Avg price</th><th className="num">Last</th><th className="num">Unrealized</th><th className="num">Realized</th><th className="hide-sm">Strategy lots</th></tr></thead>
            <tbody>
              {a.positions.map((p: any) => (
                <tr key={p.instrument_id}>
                  <td><b>{p.instrument_id}</b> {p.simulated && <Badge kind="sim">sim</Badge>}</td>
                  <td className="num mono">{fmt.num(p.qty, 8)}</td>
                  <td className="num mono">{fmt.num(p.avg_price, 6)}</td>
                  <td className="num mono">{p.price ? fmt.num(p.price, 6) : <span className="muted">no fresh price</span>}</td>
                  <td className={`num mono ${tone(p.unrealized)}`}>{fmt.signed(p.unrealized, ccy)}</td>
                  <td className={`num mono ${tone(p.realized)}`}>{fmt.signed(p.realized, ccy)}</td>
                  <td className="hide-sm tiny mono dim">{Object.entries(p.strategy_lots ?? {}).map(([k, v]) => `${k}: ${v}`).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {a?.open_orders?.length > 0 && (
        <div style={{ borderTop: "1px solid var(--line)", padding: "8px 14px" }} className="small">
          <b>{a.open_orders.length}</b> working order(s): {a.open_orders.map((o: any) => `${o.side} ${o.qty} ${o.instrument_id} (${o.status})`).join(" · ")}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- regime and agents
function RegimeAgents({ decision, iid }: { decision: any; iid: string }) {
  if (!decision) {
    return (
      <Card title="Regime & agents" sub={iid}>
        <Empty>No decision for {iid} yet. Decisions appear when a running bot on this instrument sees a new completed bar.</Empty>
      </Card>
    );
  }
  const ens = decision.ensemble ?? {};
  const reg = decision.regime ?? {};
  return (
    <Card title="Regime & agents" sub={`${decision.instrument} · ${decision.tf} · ${fmt.ago(decision.ts)}`} right={<button className="btn sm ghost" onClick={() => go("/intelligence")}>Details</button>}>
      <div className="col" style={{ gap: 8 }}>
        <div className="row wrap">
          <Badge kind="info">{reg.trend ?? "—"}</Badge>
          <Badge>{reg.volatility ?? "—"} vol</Badge>
          <Badge>{reg.character ?? "—"}</Badge>
          {reg.change_point && <Badge kind="warn">change point</Badge>}
          {decision.simulated_data && <Badge kind="sim">simulated data</Badge>}
        </div>
        <div className="kv">
          <div>Outcome</div><div><b>{decision.outcome}</b> <span className="dim">{decision.reason}</span></div>
          <div>Strategy signal</div><div>{decision.signal?.strategy === 1 ? "long" : decision.signal?.strategy === -1 ? "short" : "flat"}</div>
          <div>Ensemble score</div><div className="mono">{ens.score !== undefined ? ens.score.toFixed(3) : "—"} <span className="muted small">(strength, not a probability)</span></div>
          <div>Clusters agreeing</div><div>{ens.agreeing_clusters ?? "—"} of {ens.independent_clusters ?? "—"} · {ens.voters ?? 0} voters · {ens.unavailable ?? 0} need data</div>
        </div>
        {Object.entries(ens.cluster_scores ?? {}).map(([k, v]) => (
          <div key={k} className="col" style={{ gap: 3 }}>
            <div className="spread tiny"><span className="dim">{k.replace(/_/g, " ")}</span><span className="mono">{Number(v).toFixed(2)}</span></div>
            <Diverge value={Number(v)} />
          </div>
        ))}
        {ens.vetoes?.length > 0 && <div className="callout bad small">Vetoes: {ens.vetoes.map((v: any) => `${v.name}: ${v.message}`).join("; ")}</div>}
        {ens.conflicts?.length > 0 && <div className="callout warn small">Conflicts: {ens.conflicts.map((c: any) => typeof c === "string" ? c : JSON.stringify(c)).join("; ")}</div>}
        <div className="tiny muted">{ens.probability_note}</div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- risk
function RiskPanel() {
  const live = useLive();
  const [risk, reload] = usePoll<any>("/api/risk", 5000);
  const [edit, setEdit] = useState<{ key: string; value: string } | null>(null);
  const [raise, setRaise] = useState<{ key: string; value: number } | null>(null);
  if (!risk) return <Card title="Risk"><Empty>Loading…</Empty></Card>;
  const L = risk.limits;
  const u = risk.usage ?? {};
  const rows: [string, string, (v: any) => string][] = [
    ["max_order_pct_equity", "Max order size", fmt.pct], ["max_position_pct_equity", "Max position", fmt.pct],
    ["max_gross_exposure", "Max gross exposure", (v) => `${v}x`], ["max_leverage", "Max leverage", (v) => `${v}x`],
    ["max_daily_loss_pct", "Daily loss lock", fmt.pct], ["max_weekly_loss_pct", "Weekly loss lock", fmt.pct],
    ["max_drawdown_pct", "Drawdown lock", fmt.pct], ["max_open_positions", "Max open positions", String],
    ["max_orders_per_minute", "Max orders / minute", String], ["max_price_deviation_pct", "Fat-finger price band", fmt.pct],
    ["stale_data_bars", "Stale data after (bars)", String], ["max_participation", "Max share of bar volume", fmt.pct],
  ];
  const save = async (key: string, value: number, confirm = "") => {
    await api.post("/api/risk/limits", { changes: { [key]: value }, confirm });
    live.toast("Risk limit updated", "ok");
    reload();
    await live.refresh();
  };
  return (
    <Card title="Risk" right={risk.kill_switch ? <Badge kind="bad">STOP ALL</Badge> : risk.trading_locked ? <Badge kind="bad">LOCKED</Badge> : <Badge kind="good">ARMED</Badge>}>
      <div className="col">
        <Meter label="Daily loss" value={u.daily_loss} />
        <Meter label="Drawdown" value={u.drawdown} />
        <Meter label="Gross exposure" value={u.gross_exposure} />
        <Meter label="Largest position" value={u.position} />
        <div className="note">Deterministic checks on every order: approve, shrink or deny. No agent can raise a limit; raising needs your typed confirmation.</div>
        <table className="t small">
          <tbody>
            {rows.map(([k, label, f]) => (
              <tr key={k}>
                <td className="dim">{label}</td>
                <td className="num mono">
                  {edit?.key === k ? (
                    <span className="row" style={{ justifyContent: "flex-end" }}>
                      <input style={{ width: 80 }} value={edit.value} onChange={(e) => setEdit({ key: k, value: e.target.value })} autoFocus />
                      <button className="btn sm primary" onClick={async () => {
                        const v = Number(edit.value);
                        if (!Number.isFinite(v) || v <= 0) return live.toast("Enter a number above 0", "error");
                        setEdit(null);
                        if (v > Number(L[k])) return setRaise({ key: k, value: v });
                        try { await save(k, v); } catch (e: any) { live.toast(e.message, "error"); }
                      }}>Save</button>
                    </span>
                  ) : <span style={{ cursor: "pointer" }} title="Click to change" onClick={() => setEdit({ key: k, value: String(L[k]) })}>{f(L[k])}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="tiny muted">Counters: {risk.counters.approved} approved · {risk.counters.adjusted} shrunk · {risk.counters.denied} denied · {risk.counters.duplicates_blocked} duplicates blocked</div>
      </div>
      {raise && (
        <PhraseConfirm title="Raise a risk limit" phrase={risk.phrases.raise_limits} action="Raise limit"
          body={<>You are raising <b>{raise.key}</b> from {String(L[raise.key])} to {raise.value}. Larger limits allow larger losses.</>}
          onConfirm={(typed) => save(raise.key, raise.value, typed)} onClose={() => setRaise(null)} />
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- controls (specification section 7)
function Controls() {
  const live = useLive();
  const o = live.overview!;
  const [flat, setFlat] = useState<any>(null);
  const [confirm, setConfirm] = useState(false);
  const paused = !!o.risk?.entries_paused;
  return (
    <div className="col" style={{ gap: 6 }}>
      <div className="row">
        <button className={`btn grow ${paused ? "primary" : ""}`} onClick={async () => {
          try { await api.post("/api/controls/pause-entries", { paused: !paused, reason: "owner" }); live.toast(paused ? "New entries allowed" : "New entries paused: exits keep running", "ok"); } catch (e: any) { live.toast(e.message, "error"); }
          await live.refresh();
        }}>{paused ? "Resume new entries" : "Pause new entries"}</button>
        <button className="btn grow" onClick={() => setConfirm(true)}>Flatten all…</button>
      </div>
      <div className="tiny muted">Pause new entries: nothing new opens; exits and position management continue. Flatten: closes every paper position through the risk service (markets that are closed are reported, not faked). Emergency stop (top right) latches everything.</div>
      {confirm && (
        <Modal title="Flatten every paper position?" onClose={() => setConfirm(false)}>
          <div className="dim">Sends closing orders for all paper positions now. Positions in closed markets cannot be closed until they open; the result lists exactly what happened.</div>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn ghost" onClick={() => setConfirm(false)}>Cancel</button>
            <button className="btn danger" onClick={async () => {
              setConfirm(false);
              try { setFlat(await api.post("/api/controls/flatten")); } catch (e: any) { live.toast(e.message, "error"); }
              await live.refresh();
            }}>Flatten all</button>
          </div>
        </Modal>
      )}
      {flat && (
        <div className={`callout ${flat.complete ? "good" : "warn"} small`}>
          {flat.closed}/{flat.requested} position(s) closed{flat.cancelled_orders ? `, ${flat.cancelled_orders} working order(s) cancelled` : ""}.
          {flat.results.filter((r: any) => r.status !== "FILLED").map((r: any) => <div key={r.instrument + r.strategy}>{r.instrument}: {r.status} — {r.detail}</div>)}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- equity and drawdown, session report
function EquityCard() {
  const [hours, setHours] = useState(168);
  const [eq] = usePoll<any>(`/api/equity?hours=${hours}`, 60000, [hours]);
  const [report, setReport] = useState(false);
  return (
    <Card title="Equity" sub={eq?.simulated ? "paper account (simulated money)" : undefined} right={
      <div className="row">
        <div className="seg">{[[24, "1D"], [168, "1W"], [720, "1M"], [8760, "1Y"]].map(([h, l]) => <button key={h} className={hours === h ? "on" : ""} onClick={() => setHours(Number(h))}>{l}</button>)}</div>
        <button className="btn sm" onClick={() => setReport(true)}>Session report</button>
      </div>
    } flush>
      {!eq || eq.equity.length < 2 ? <Empty>The equity curve is recorded every minute while the program runs; it appears after a few minutes.</Empty> : (
        <>
          <EquityChart points={eq.equity} height={200} />
          <div className="row wrap small" style={{ padding: "6px 14px", borderTop: "1px solid var(--line)" }}>
            <span className="dim">Max drawdown in view</span><b className="mono">{fmt.pct(Math.min(...eq.drawdown.map((d: any) => d[1])))}</b>
            {eq.adjustments.length > 0 && <span className="muted tiny">{eq.adjustments.length} balance adjustment(s) in this period are not trading results</span>}
          </div>
        </>
      )}
      {report && <SessionReport onClose={() => setReport(false)} />}
    </Card>
  );
}

function SessionReport({ onClose }: { onClose: () => void }) {
  const [r] = usePoll<any>("/api/report/session", 0);
  const download = () => {
    const blob = new Blob([JSON.stringify(r, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `trading-ai-session-${r.label.startsWith("PAPER") ? "paper" : "live"}-${new Date().toISOString().slice(0, 16).replace(":", "")}.json`;
    a.click();
  };
  return (
    <Drawer title="Session report" onClose={onClose} right={r && <button className="btn sm" onClick={download}>Export JSON</button>}>
      {!r ? <Empty>Loading…</Empty> : (
        <>
          <div className="row wrap"><Badge kind={r.simulated ? "sim" : "bad"}>{r.label}</Badge><span className="dim small">{fmt.datetime(r.since)} → {fmt.datetime(r.until)}</span></div>
          <div className="stats">
            <Stat k="Fills" v={r.trades} /><Stat k="Fees" v={fmt.money(r.fees)} /><Stat k="Blocked by risk" v={r.decisions.RISK_REJECT ?? 0} />
            <Stat k="Orders" v={r.decisions.ORDER ?? 0} /><Stat k="No-trade decisions" v={r.decisions.NO_TRADE ?? 0} /><Stat k="Equity" v={fmt.money(r.equity)} />
          </div>
          <Card title="Attribution by strategy" sub={r.attribution.note} flush>
            {!r.attribution.by_strategy.length ? <Empty>No fills yet.</Empty> : (
              <table className="t small"><thead><tr><th>Strategy</th><th className="num">Fills</th><th className="num">Net P&amp;L</th><th className="num">Fees</th><th className="num">Slippage</th><th className="num">Open value</th></tr></thead>
                <tbody>{r.attribution.by_strategy.map((x: any) => (
                  <tr key={x.name}><td className="mono tiny">{x.name}</td><td className="num">{x.fills}</td><td className={`num mono ${tone(x.net_pnl)}`}>{fmt.signed(x.net_pnl)}</td><td className="num mono">{fmt.money(x.fees)}</td><td className="num mono">{fmt.money(x.slippage_vs_decision)}</td><td className="num mono">{fmt.money(x.open_value)}{x.unpriced ? " *" : ""}</td></tr>
                ))}</tbody></table>
            )}
          </Card>
          <Card title="Attribution by market" flush>
            {!r.attribution.by_market.length ? <Empty>No fills yet.</Empty> : (
              <table className="t small"><thead><tr><th>Market</th><th className="num">Fills</th><th className="num">Net P&amp;L</th><th className="num">Fees</th></tr></thead>
                <tbody>{r.attribution.by_market.map((x: any) => <tr key={x.name}><td>{x.name}</td><td className="num">{x.fills}</td><td className={`num mono ${tone(x.net_pnl)}`}>{fmt.signed(x.net_pnl)}</td><td className="num mono">{fmt.money(x.fees)}</td></tr>)}</tbody></table>
            )}
          </Card>
          <Card title="Strategy changes"><div className="col" style={{ gap: 4 }}>{r.strategy_changes.length ? r.strategy_changes.map((c: any, i: number) => <div key={i} className="small"><span className="muted mono tiny">{fmt.datetime(c.ts)}</span> {c.message}</div>) : <span className="muted small">None this session.</span>}</div></Card>
          <Card title="Blocked decisions"><div className="col" style={{ gap: 4 }}>{r.blocked.length ? r.blocked.map((b: any, i: number) => <div key={i} className="small"><span className="muted mono tiny">{fmt.datetime(b.ts)}</span> {b.instrument_id}: {b.reason}</div>) : <span className="muted small">None.</span>}</div></Card>
          <Card title="Incidents (warnings and above)"><div className="col" style={{ gap: 4 }}>{r.incidents.length ? r.incidents.map((c: any, i: number) => <div key={i} className="small"><span className="muted mono tiny">{fmt.datetime(c.ts)}</span> [{c.severity}] {c.message}</div>) : <span className="muted small">None.</span>}</div></Card>
          <div className="note">Remaining exposure: {r.remaining_exposure.length} position(s), {r.open_orders.length} working order(s).</div>
        </>
      )}
    </Drawer>
  );
}
