import { Fragment, useMemo, useState } from "react";
import { fmt } from "../api";
import { Badge, Card, Check, Diverge, Empty, Tabs } from "../components/ui";
import { useLive, usePoll } from "../store";
import { ExperimentDrawer, Verdict } from "./StrategyLab";

const OUTCOME_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = { ORDER: "good", HOLD: "info", NO_TRADE: "", RISK_REJECT: "bad" };

export default function LiveIntelligence() {
  const live = useLive();
  const [sel, setSel] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const decisions = live.decisions.filter((d) => !filter || d.instrument === filter);
  const instruments = useMemo(() => Array.from(new Set(live.decisions.map((d) => d.instrument))), [live.decisions]);
  const current = sel ?? decisions[0]?.decision_id ?? null;

  return (
    <>
      <Roles />
      <MarketAnalysis />
      <div className="grid g-main">
        <div className="col" style={{ gap: 14, minWidth: 0 }}>
          <Card title="Decisions" sub="every bar a running bot evaluates, including NO TRADE, with its reasons" right={
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by instrument">
              <option value="">All instruments</option>
              {instruments.map((i) => <option key={i}>{i}</option>)}
            </select>
          } flush>
            <div className="scroll" style={{ maxHeight: 330 }}>
              {!decisions.length ? <Empty>No decisions yet. The autopilot starts bots by itself; you can also add one on the AI Trading System page.</Empty> : (
                <table className="t small">
                  <thead><tr><th>Time</th><th>Instrument</th><th>Mode</th><th>Outcome</th><th>Reason</th><th className="num">Score</th><th className="num">ms</th></tr></thead>
                  <tbody>{decisions.map((d) => (
                    <tr key={d.decision_id} className={`click ${current === d.decision_id ? "sel" : ""}`} onClick={() => setSel(d.decision_id)}>
                      <td className="nowrap">{fmt.time(d.ts)}</td><td className="nowrap">{d.instrument} <span className="muted">{d.tf}</span></td>
                      <td><Badge kind={d.mode === "live" ? "bad" : d.mode === "shadow" ? "info" : "sim"}>{d.mode}</Badge></td>
                      <td><Badge kind={OUTCOME_KIND[d.outcome] ?? ""}>{d.outcome}</Badge></td>
                      <td className="dim" style={{ maxWidth: 360 }}>{d.reason}</td>
                      <td className="num mono">{d.ensemble?.score !== undefined ? d.ensemble.score.toFixed(2) : "—"}</td>
                      <td className="num mono">{d.latency?.total_ms !== undefined ? Math.round(d.latency.total_ms) : "—"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          </Card>
          {current && <DecisionDetail id={current} />}
        </div>
        <div className="col" style={{ gap: 14, minWidth: 0 }}>
          <Health />
          <EventStream />
        </div>
      </div>
      <div className="grid g-2">
        <ResearchCenter />
        <AgentRoster />
      </div>
    </>
  );
}

// ---------------------------------------------------------------- market analysis: latest regime per instrument
function MarketAnalysis() {
  const live = useLive();
  const latest = useMemo(() => {
    const m = new Map<string, any>();
    for (const d of live.decisions) if (!m.has(d.instrument) && d.regime) m.set(d.instrument, d);
    return Array.from(m.values());
  }, [live.decisions]);
  if (!latest.length) return null;
  return (
    <div className="grid g-3">
      {latest.slice(0, 6).map((d) => (
        <Card key={d.instrument} title={d.instrument} sub={`${d.tf} · ${fmt.ago(d.ts)}`} right={d.simulated_data ? <Badge kind="sim">sim</Badge> : null}>
          <div className="row wrap">
            <Badge kind="info">{d.regime.trend}</Badge><Badge>{d.regime.volatility} vol</Badge><Badge>{d.regime.character}</Badge>
            {d.regime.change_point && <Badge kind="warn">change point</Badge>}
          </div>
          <div className="col" style={{ gap: 4, marginTop: 8 }}>
            <div className="spread tiny"><span className="dim">Ensemble score (−1 … +1)</span><span className="mono">{d.ensemble?.score?.toFixed(2) ?? "—"}</span></div>
            <Diverge value={d.ensemble?.score ?? 0} />
            <div className="tiny muted">HMM state “{d.regime.hmm_state}” {d.regime.hmm_state_prob !== undefined ? `(${fmt.pct(d.regime.hmm_state_prob, 0)} model state probability, uncalibrated)` : ""}</div>
          </div>
        </Card>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- one decision
function DecisionDetail({ id }: { id: string }) {
  const [d] = usePoll<any>(`/api/decisions/${id}`, 0, [id]);
  const [tab, setTab] = useState<"agents" | "risk" | "exec" | "audit">("agents");
  if (!d) return <Card title="Decision"><Empty>Loading…</Empty></Card>;
  const votes: any[] = d.votes?.votes ?? [];
  const ens = d.votes?.ensemble ?? {};
  const order = d.order_json;
  return (
    <Card title={`Decision ${d.decision_id}`} sub={`${d.instrument_id} · ${fmt.datetime(d.ts)} · ${d.mode}`} right={<Badge kind={OUTCOME_KIND[d.outcome] ?? ""}>{d.outcome}</Badge>} flush>
      <div style={{ padding: "10px 14px" }} className="col">
        <div><b>Why:</b> {d.reason}</div>
        <div className="row wrap small">
          <span className="dim">Strategy</span><span className="mono">{d.strategy_id}</span>
          <span className="dim">signal</span><b>{d.signal?.strategy === 1 ? "long" : d.signal?.strategy === -1 ? "short" : "flat"}</b>
          <span className="dim">ensemble</span><span className="mono">{ens.score?.toFixed(3) ?? "—"}</span>
          <span className="dim">clusters agreeing</span><span>{ens.agreeing_clusters ?? "—"}/{ens.independent_clusters ?? "—"}</span>
        </div>
        {ens.vetoes?.length > 0 && <div className="callout bad small">Vetoes: {ens.vetoes.map((v: any) => `${v.name}: ${v.message}`).join("; ")}</div>}
        {ens.conflicts?.length > 0 && <div className="callout warn small">Conflicts: {ens.conflicts.map((c: any) => typeof c === "string" ? c : JSON.stringify(c)).join("; ")}</div>}
        {ens.flags?.length > 0 && <div className="row wrap">{ens.flags.map((f: string) => <Badge key={f} kind={f.includes("SIMULATED") ? "sim" : "warn"}>{f}</Badge>)}</div>}
      </div>
      <Tabs tabs={[["agents", `Agents (${votes.length})`], ["risk", "Risk checks"], ["exec", "Execution"], ["audit", "Audit trail"]]} on={tab} set={setTab} />
      {tab === "agents" && (
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="t small">
            <thead><tr><th>Agent</th><th>Group</th><th>Cluster</th><th>Status</th><th className="num">Score</th><th style={{ width: 120 }}></th><th>Says</th></tr></thead>
            <tbody>{votes.map((v) => (
              <tr key={v.agent_id} title={JSON.stringify(v.evidence)}>
                <td className="nowrap"><span className="mono muted">{v.agent_id}</span> {v.name}</td>
                <td className="dim">{v.group}</td><td className="dim">{v.cluster?.replace(/_/g, " ")}</td>
                <td>{v.veto ? <Badge kind="bad">VETO</Badge> : v.status === "ok" ? <Badge kind="good">ok</Badge> : <Badge>{v.status}</Badge>}</td>
                <td className="num mono">{v.score !== null && v.score !== undefined ? Number(v.score).toFixed(2) : "—"}</td>
                <td>{v.direction !== null && v.direction !== undefined ? <Diverge value={Number(v.score ?? 0)} /> : <span className="tiny muted">no vote</span>}</td>
                <td className="dim">{v.message}{v.risk_flags?.length ? <span className="neg"> · {v.risk_flags.join(", ")}</span> : null}</td>
              </tr>
            ))}</tbody>
          </table>
          <div className="note" style={{ padding: "8px 14px" }}>{ens.probability_note} Agents marked "unavailable" need data this installation does not have; they abstain instead of guessing.</div>
        </div>
      )}
      {tab === "risk" && (
        <div style={{ padding: "8px 14px" }}>
          {!d.risk ? <Empty>No order was proposed, so no risk check ran.</Empty> : (
            <>
              <div className={`callout ${d.risk.approved ? "good" : "bad"} small`}>{d.risk.reason}</div>
              {d.risk.checks.map((c: any) => <Check key={c.name} ok={c.passed} name={c.name} detail={c.detail} />)}
            </>
          )}
        </div>
      )}
      {tab === "exec" && (
        <div style={{ padding: "8px 14px" }} className="col">
          {!order ? <Empty>No order for this decision.</Empty> : (
            <div className="kv">
              <div>Side / qty</div><div>{order.side} {order.qty} (target {order.target})</div>
              <div>Status</div><div><Badge kind={order.status === "FILLED" ? "good" : order.status?.includes("BLOCK") ? "bad" : ""}>{order.status}</Badge> {order.note}</div>
              <div>Client order id</div><div className="mono small">{order.client_order_id}</div>
              <div>Filled</div><div className="mono">{order.filled_qty ?? "—"} @ {order.avg_price ?? "—"}</div>
              {order.error && <><div>Error</div><div className="neg">{order.error}</div></>}
            </div>
          )}
          <div className="kv small">
            {Object.entries(d.latency ?? {}).map(([k, v]) => <Fragment key={k}><div>{k.replace(/_/g, " ")}</div><div className="mono">{Number(v).toFixed(1)} ms</div></Fragment>)}
          </div>
        </div>
      )}
      {tab === "audit" && (
        <div style={{ padding: "8px 14px" }}>
          {!d.audit?.length ? <Empty>No audit rows linked to this decision.</Empty> : d.audit.map((a: any) => (
            <div key={a.id} className="check"><span className="ic tiny muted">#{a.id}</span><div className="grow"><div>{a.message}</div><div className="note">{fmt.datetime(a.ts)} · {a.kind} · {a.severity}</div></div></div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- event stream
function EventStream() {
  const live = useLive();
  const [topic, setTopic] = useState("");
  const topics = useMemo(() => Array.from(new Set(live.events.map((e) => e.topic.split(".")[0]))).sort(), [live.events]);
  const shown = live.events.filter((e) => !topic || e.topic.startsWith(topic)).slice(-150).reverse();
  return (
    <Card title="Live event stream" sub={live.ws === "live" ? "WebSocket connected" : live.ws} right={
      <select value={topic} onChange={(e) => setTopic(e.target.value)} aria-label="Filter events"><option value="">All</option>{topics.map((t) => <option key={t}>{t}</option>)}</select>
    } flush>
      <div className="scroll" style={{ maxHeight: 520 }}>
        {!shown.length ? <Empty>Waiting for events…</Empty> : shown.map((e) => (
          <div key={`${e.id}-${e.topic}`} className={`evt ${e.severity}`}>
            <div className="meta"><span className="mono muted">{fmt.time(e.ts)}</span><span className="topic">{e.topic}</span></div>
            <div>{summarize(e)}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function summarize(e: any): string {
  const d = e.data ?? {};
  switch (e.topic) {
    case "decision": return `${d.instrument} ${d.tf}: ${d.outcome} — ${d.reason}`;
    case "audit": return `${d.kind}: ${d.message}`;
    case "state": return `${d.from} → ${d.to} (${d.reason})`;
    case "account": return `equity ${fmt.money(d.account?.equity)} · ${d.positions?.length ?? 0} position(s) · ${d.badge}`;
    case "order.update": return `${d.side} ${d.qty} ${d.instrument}: ${d.status}`;
    case "order.shadow": return `SHADOW (not sent): ${d.side} ${d.qty} ${d.instrument} @ ${d.intended_price}`;
    case "risk.denied": return `${d.instrument}: ${d.reason}`;
    case "research.progress": return `${d.title}: ${d.stage} ${Math.round((d.progress ?? 0) * 100)}%`;
    case "research.done": return `${d.title}: ${d.state}${d.error ? ` — ${d.error}` : ""}`;
    case "agents": return `${d.votes?.length ?? 0} agent outputs for ${d.instrument}`;
    case "autopilot": return `AUTOPILOT: ${d.message}`;
    default: return JSON.stringify(d).slice(0, 180);
  }
}

// ---------------------------------------------------------------- system health
function Health() {
  const [h] = usePoll<any>("/health", 5000);
  if (!h) return <Card title="System health"><Empty>Loading…</Empty></Card>;
  const c = h.components;
  const series = Object.entries(c.market_feed.series ?? {});
  return (
    <Card title="System health" sub={`v${h.version} · up ${Math.round(c.backend.uptime_s / 60)} min`} right={<Badge kind={h.startup_checks.every((x: any) => x.ok) ? "good" : "warn"}>{h.startup_checks.filter((x: any) => x.ok).length}/{h.startup_checks.length} checks</Badge>}>
      <div className="col" style={{ gap: 8 }}>
        <div className="kv small">
          <div>Database</div><div>{c.database.status} · {fmt.num(c.database.bytes / 1e6, 1)} MB</div>
          <div>Risk service</div><div>{c.risk_service.status}</div>
          <div>Strategy engine</div><div>{c.strategy_engine.status} · {c.strategy_engine.bots} bot(s) · last tick {c.strategy_engine.last_tick_s_ago ?? "—"} s ago</div>
          <div>Execution</div><div>risk check p50 {c.execution_engine.latency_ms.risk_ms.p50 ?? "—"} ms · decision→submit p50 {c.execution_engine.latency_ms.decision_to_submit_ms.p50 ?? "—"} ms</div>
          <div>Research</div><div>{c.research.jobs} job(s) this session · {c.research.ledger.experiments} in the ledger</div>
          <div>WebSocket clients</div><div>{c.websocket.clients}</div>
          <div>Machine</div><div>{h.system.cpu_count} CPU · RAM {h.system.ram_used_pct ?? "—"}% used · disk free {h.system.disk_free_gb ?? "—"} GB</div>
          <div>GPU</div><div className="dim">{h.gpu}</div>
        </div>
        <div className="small"><b>Data providers</b></div>
        {Object.keys(c.market_feed.http).length === 0 ? <div className="note">No requests yet{h.mode && c.market_feed.status === "offline" ? " (offline mode)" : ""}.</div> : (
          <div className="scroll">
            <table className="t small"><thead><tr><th>Host</th><th className="num">Requests</th><th className="num">Errors</th><th className="num">429</th><th className="num">p50 ms</th></tr></thead>
              <tbody>{Object.entries(c.market_feed.http).map(([host, s]: any) => (
                <tr key={host}><td className="mono tiny">{host}</td><td className="num mono">{s.requests}</td><td className="num mono">{s.errors}</td><td className="num mono">{s.http_429}</td><td className="num mono">{s.p50_ms ?? "—"}</td></tr>
              ))}</tbody></table>
          </div>
        )}
        {series.length > 0 && (
          <div className="scroll">
            <table className="t small"><thead><tr><th>Series</th><th>Fresh</th><th className="num">Quality</th><th className="num">Age</th></tr></thead>
              <tbody>{series.slice(-10).map(([k, s]: any) => (
                <tr key={k}><td className="mono tiny">{k}</td><td>{s.simulated ? <Badge kind="sim">sim</Badge> : s.fresh ? <Badge kind="good">yes</Badge> : <Badge kind="warn">no</Badge>}</td>
                  <td className="num mono">{fmt.num(s.quality, 0)}</td><td className="num mono">{s.age_s !== null && s.age_s !== undefined ? `${Math.round(s.age_s)}s` : "—"}</td></tr>
              ))}</tbody></table>
          </div>
        )}
        <details>
          <summary className="small dim" style={{ cursor: "pointer" }}>Start-up checks</summary>
          {h.startup_checks.map((x: any) => <Check key={x.name} ok={x.ok} name={x.name} detail={`${x.detail} · ${x.ms} ms`} />)}
        </details>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- research and agents
function ResearchCenter() {
  const [exps] = usePoll<any>("/api/research/experiments?limit=20", 10000);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Card title="Research center" sub="the experiment ledger: every backtest, kept with its data hash and trial count" flush>
      {!exps?.experiments?.length ? <Empty>No research yet. Run a backtest from the Strategy lab on the AI Trading System page, or let the autopilot research.</Empty> : (
        <div className="scroll" style={{ maxHeight: 380 }}>
          <table className="t small">
            <thead><tr><th>When</th><th>Strategy</th><th>Data</th><th>Verdict</th><th className="num">Quality</th></tr></thead>
            <tbody>{exps.experiments.map((e: any) => (
              <tr key={e.experiment_id} className="click" onClick={() => setOpen(e.experiment_id)}>
                <td className="nowrap">{fmt.datetime(e.created)}</td><td className="mono tiny" style={{ wordBreak: "break-all" }}>{e.strategy_id}</td>
                <td>{e.dataset?.instrument} {e.dataset?.tf}</td><td>{e.verdict ? <Verdict v={e.verdict} /> : <Badge>{e.status}</Badge>}</td>
                <td className="num mono">{e.quality ?? "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {open && <ExperimentDrawer eid={open} onClose={() => setOpen(null)} />}
    </Card>
  );
}

function AgentRoster() {
  const [a] = usePoll<any>("/api/agents", 0);
  const [group, setGroup] = useState("");
  if (!a) return <Card title="Agents"><Empty>Loading…</Empty></Card>;
  const groups = Object.keys(a.summary.by_group);
  const shown = a.agents.filter((x: any) => !group || x.group === group);
  return (
    <Card title="Agents" sub={`${a.summary.agents} agents · ${a.summary.voting} vote · ${a.summary.need_external_data} need data not connected`} right={
      <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Agent group"><option value="">All groups</option>{groups.map((g) => <option key={g}>{g} ({a.summary.by_group[g]})</option>)}</select>
    } flush>
      <div className="scroll" style={{ maxHeight: 380 }}>
        <table className="t small">
          <thead><tr><th>Agent</th><th>Group</th><th>Role</th><th>Needs</th></tr></thead>
          <tbody>{shown.map((x: any) => (
            <tr key={x.agent_id}><td className="nowrap"><span className="mono muted">{x.agent_id}</span> {x.name}</td><td className="dim">{x.group}</td>
              <td>{x.votes ? <Badge kind="info">votes</Badge> : <Badge>advises</Badge>}</td>
              <td className="tiny">{x.requires.length ? <Badge kind="warn">REQUIRES CONNECTION: {x.requires.join(", ")}</Badge> : <span className="muted">built-in data</span>}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- the 25 logical roles (specification section 4)
const ROLE_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  running: "good", completed: "info", idle: "", "waiting for data": "warn", paused: "warn", blocked: "bad", degraded: "warn",
  failed: "bad", unavailable: "",
};

function Roles() {
  const [r] = usePoll<any>("/api/roles", 5000);
  const [open, setOpen] = useState(false);
  if (!r) return null;
  const c = r.counts;
  return (
    <Card title="Agents and roles" sub={r.model} right={<button className="btn sm" onClick={() => setOpen((v) => !v)}>{open ? "Hide roles" : "Show all 25 roles"}</button>}>
      <div className="stats">
        <div className="stat"><div className="k">Configured roles</div><div className="v">{c.configured_roles}</div><div className="s">{c.agent_functions} agent functions</div></div>
        <div className="stat"><div className="k">Running jobs</div><div className="v">{c.running_jobs}</div><div className="s">loop, autopilot, research queue</div></div>
        <div className="stat"><div className="k">Active model calls</div><div className="v">{c.active_model_calls}</div><div className="s">no cloud AI connected</div></div>
        <div className="stat"><div className="k">Stale feeds</div><div className="v">{r.stale_feeds}</div><div className="s">queue depth {r.queue_depth}</div></div>
      </div>
      {open && (
        <div className="scroll" style={{ marginTop: 10 }}>
          <table className="t small">
            <thead><tr><th>#</th><th>Role</th><th>Implementation</th><th>State</th><th>Latest</th></tr></thead>
            <tbody>{r.roles.map((x: any) => (
              <tr key={x.id}>
                <td className="mono muted">{x.id}</td>
                <td><b>{x.name}</b><div className="tiny muted">{x.component}</div></td>
                <td className="tiny">{x.implementation}{x.agent_functions ? ` · ${x.agent_functions} agents` : ""}</td>
                <td><Badge kind={ROLE_KIND[x.state] ?? ""}>{x.state}</Badge></td>
                <td className="tiny dim">{x.latest}{x.latest_ts ? ` · ${fmt.ago(x.latest_ts)}` : ""}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
