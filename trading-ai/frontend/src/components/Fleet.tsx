import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, fmt, tone } from "../api";
import { useLive, usePoll } from "../store";
import { Badge, Card, Drawer, Empty, Tabs } from "./ui";

// The master system agent and its 100 trading agents A001-A100 (page 2). Every number here comes from /api/fleet and
// /api/learning; nothing is animated unless the server reported a change.

type Agent = {
  id: string; group: string; partition: string[]; runtime: string; job: string; detail: string; venue: string | null;
  market: string | null; consumed_version: number | null; last_input_ts: number | null; last_price: string | null;
  heartbeat: number | null; job_ms: number | null; eligible: number; errors: number; assignment_version: number;
  budget: string; next_action: string | null; fresh: boolean; meme?: boolean; strategies?: string[]; position?: string | null; unrealized?: string | null;
  realized?: string | null; fees?: string | null; open_orders?: number; last_decision?: { ts: number; outcome: string; reason: string } | null;
  role_label?: string; family?: string; tf?: string; permission?: boolean; permission_reason?: string;
  version?: { version: number; strategy_id: string } | null; versions?: number; mistakes?: number;
};

const RUNTIME_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  available: "good", degraded: "warn", blocked: "", stopped: "", starting: "info",
};
const DOT: Record<string, string> = {
  available: "var(--good)", degraded: "var(--warn)", blocked: "#33445f", stopped: "#33445f", starting: "var(--accent)",
};
const GROUP_LABEL: Record<string, string> = {
  crypto_major: "Crypto majors", crypto_trend: "Crypto trend", crypto_reversion: "Crypto reversion",
  etf_intraday: "ETF intraday", stock_breakout: "Stock breakouts", stock_reversion: "Stock reversion",
  fx_trend: "Forex", index_futures: "Index futures",
};
const VERSION_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  active: "good", shadow: "info", superseded: "", rejected: "bad", rolled_back: "warn",
};

export function FleetPanel() {
  const [f] = usePoll<any>("/api/fleet", 5000);
  const [tab, setTab] = useState<"network" | "grid" | "learning" | "caps">("network");
  const [open, setOpen] = useState<string | null>(null);
  const pulses = usePulses(f?.agents);
  if (!f) return <Card title="Master agent"><Empty>Loading the 100 agents…</Empty></Card>;
  const c = f.counts;
  const b = f.brain;
  return (
    <Card title="Master agent and 100 trading agents" sub={`${b.kind} · ${b.model}`} flush>
      <div className="brain-row">
        <BrainCore plan={b.plan_version} owned={b.owned_instruments} />
        <div className="col" style={{ gap: 8, minWidth: 0, flex: 1 }}>
          <div className="small"><b>Now:</b> <span className="dim">{b.doing}</span></div>
          <div className="small"><b>Plan:</b> <span className="dim">{b.plan}</span></div>
          <div className="tiny muted">Controls: {(b.controls ?? []).join(" · ")}</div>
          <div className="kv small">
            <div>Plan version</div><div className="mono">{b.plan_version}</div>
            <div>Market-state version</div><div className="mono">{b.market_state_version ?? "— (discovery off)"}</div>
            <div>Last fleet cycle</div><div className="mono">{b.metrics.last_cycle_ms !== null ? `${b.metrics.last_cycle_ms} ms` : "—"} · {fmt.ago(b.metrics.last_cycle)} · {b.metrics.cycles} cycles</div>
            <div>Missed deadlines</div><div className="mono">{b.metrics.missed_deadlines}</div>
          </div>
        </div>
      </div>
      <div className="stats" style={{ margin: "0 14px 12px" }}>
        <Num k="Trading agents" v={c.registered} s={`exactly ${c.target} · ${c.assigned} with a distinct market`} />
        <Num k="Fresh data now" v={c.data_ready} s={`${c.market_closed} more in closed markets`} />
        <Num k="Validated version" v={c.validated} s={`${c.trained} trained · ${c.training_jobs} training now`} />
        <Num k="May open trades now" v={c.execution_eligible} s="master's permission (paper)" />
        <Num k="Holding positions" v={c.with_positions} s="exits always allowed" />
        <Num k="Suspended / blocked" v={c.suspended + c.blocked} s={`${c.suspended} suspended · ${c.blocked} no market`} />
      </div>
      <Tabs tabs={[["network", "Network"], ["grid", `Agent grid (${f.agents.length})`],
        ["learning", `Learning (${f.learning?.lessons ?? 0} lessons)`], ["caps", "Support services C01–C50"]]} on={tab} set={setTab} />
      {tab === "network" && <><MarketMap m={f.market_map} /><Network groups={f.groups} agents={f.agents} pulses={pulses} onOpen={setOpen} /><MasterActivity items={f.activity} /></>}
      {tab === "grid" && <AgentGrid agents={f.agents} groups={f.groups} onOpen={setOpen} />}
      {tab === "learning" && <LearningPanel />}
      {tab === "caps" && <Capabilities />}
      {open && <AgentDrawer id={open} onClose={() => setOpen(null)} />}
    </Card>
  );
}

function Num({ k, v, s }: { k: string; v: number; s: string }) {
  return <div className="stat"><div className="k">{k}</div><div className="v">{v}</div><div className="s">{s}</div></div>;
}

function BrainCore({ plan, owned }: { plan: number; owned: number }) {
  return (
    <svg className="brain-core" viewBox="0 0 120 120" role="img" aria-label={`Master plan version ${plan}, ${owned} instruments owned`}>
      <defs>
        <radialGradient id="bc" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#a78bfa" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="60" cy="60" r="56" fill="url(#bc)" />
      <g className="ring"><circle cx="60" cy="60" r="44" fill="none" stroke="#3dd9ff" strokeOpacity="0.5" strokeDasharray="4 7" /></g>
      <circle cx="60" cy="60" r="32" fill="#101a2b" stroke="#a78bfa" strokeWidth="2" />
      <text x="60" y="60" textAnchor="middle" fontSize="18" fontWeight="700" fill="#f2f6ff">{owned}</text>
      <text x="60" y="73" textAnchor="middle" fontSize="8" fill="#a9b8ce">owned</text>
    </svg>
  );
}

// An agent pulses once when the server reports that it received new market data since the previous refresh.
function usePulses(agents: Agent[] | undefined): Set<string> {
  const prev = useRef<Map<string, number | null>>(new Map());
  const [on, setOn] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!agents) return;
    const next = new Set<string>();
    for (const a of agents) {
      const p = prev.current.get(a.id);
      if (p !== undefined && a.last_input_ts && a.last_input_ts !== p) next.add(a.id);
      prev.current.set(a.id, a.last_input_ts);
    }
    setOn(next);
    if (!next.size) return;
    const t = window.setTimeout(() => setOn(new Set()), 1600);
    return () => window.clearTimeout(t);
  }, [agents]);
  return on;
}

// ---------------------------------------------------------------- market map: sessions, venue health, blind spots
function MarketMap({ m }: { m: any }) {
  if (!m) return null;
  return (
    <div className="grid g-3" style={{ padding: "12px 14px 0" }}>
      <div className="col" style={{ gap: 6 }}>
        <div className="tiny muted">SESSIONS (now)</div>
        {Object.entries(m.sessions).map(([k, s]: any) => (
          <div key={k} className="spread small"><span>{s.label}</span><Badge kind={s.open ? "good" : ""} dot>{s.open ? (s.session ?? "open") : (s.session ?? "closed")}</Badge></div>
        ))}
      </div>
      <div className="col" style={{ gap: 6 }}>
        <div className="tiny muted">CRYPTO VENUES (shared snapshot)</div>
        {m.offline ? <div className="small dim">Offline mode: venue discovery is off.</div> : Object.entries(m.venues).map(([v, x]: any) => (
          <div key={v} className="col" style={{ gap: 2 }}>
            <div className="spread small"><b>{v}</b><Badge kind={x.received && Date.now() - x.received < 150000 ? "good" : "warn"} dot>{x.received ? `snapshot ${fmt.ago(x.received)}` : "no snapshot yet"}</Badge></div>
            <div className="tiny dim">{x.listed} listed · {x.snapshot_fresh} with a fresh price · {x.execution_eligible} paper-tradable · {x.delisted} delisted</div>
          </div>
        ))}
      </div>
      <div className="col" style={{ gap: 6 }}>
        <div className="tiny muted">CANNOT OBSERVE</div>
        {(m.uncovered ?? []).map((u: any) => <div key={u.market} className="tiny"><b>{u.market}</b> <span className="dim">— {u.reason}</span></div>)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- network: the brain and one cluster per group
function Network({ groups, agents, pulses, onOpen }: { groups: any[]; agents: Agent[]; pulses: Set<string>; onOpen: (id: string) => void }) {
  const W = 1000, H = 560, cx = W / 2, cy = H / 2;
  const layout = useMemo(() => {
    const gs = groups.filter((g) => g.target > 0);
    return gs.map((g, i) => {
      const ang = -Math.PI / 2 + (i * 2 * Math.PI) / gs.length;
      const x = cx + Math.cos(ang) * 360, y = cy + Math.sin(ang) * 205;
      const members = agents.filter((a) => a.group === g.group);
      const pts = members.map((a, k) => {
        const r = 6.2 * Math.sqrt(k + 0.5), t = k * 2.39996;          // sunflower packing
        return { a, x: x + Math.cos(t) * r, y: y + Math.sin(t) * r };
      });
      const rad = 6.2 * Math.sqrt(members.length + 0.5) + 8;
      return { g, x, y, pts, rad };
    });
  }, [groups, agents, cx, cy]);
  const blocked = agents.filter((a) => a.runtime === "blocked").length;
  return (
    <div style={{ padding: "8px 14px 12px" }}>
      <svg className="net" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`${agents.length} trading agents in ${layout.length} roles around the master agent; ${blocked} blocked. Use the Agent grid tab for a table.`}>
        {layout.map(({ g, x, y }) => (
          <line key={`l-${g.group}`} x1={cx} y1={cy} x2={x} y2={y} stroke="#2a3b55" strokeWidth={g.assigned ? 1.6 : 1} strokeDasharray={g.assigned ? "" : "4 6"} />
        ))}
        <circle cx={cx} cy={cy} r={34} fill="#101a2b" stroke="#a78bfa" strokeWidth={2} />
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize="12" fontWeight="700" fill="#f2f6ff">MASTER</text>
        <text x={cx} y={cy + 13} textAnchor="middle" fontSize="9.5" fill="#a9b8ce">agent</text>
        {layout.map(({ g, x, y, pts, rad }) => (
          <g key={g.group}>
            <circle cx={x} cy={y} r={rad} fill="rgba(23,36,58,0.55)" stroke="#2a3b55" />
            {pts.map(({ a, x: px, y: py }) => (
              <circle key={a.id} cx={px} cy={py} r={pulses.has(a.id) ? 4.2 : 2.6} fill={DOT[a.runtime] ?? "#33445f"}
                stroke={a.position ? "#f2f6ff" : "none"} strokeWidth={a.position ? 1.2 : 0}
                className={`dot-agent ${pulses.has(a.id) ? "pulse" : ""}`} onClick={() => onOpen(a.id)}>
                <title>{`${a.id} · ${a.partition[0] ?? "no market"} · ${a.runtime} · ${a.job}`}</title>
              </circle>
            ))}
            <text x={x} y={y + rad + 15} textAnchor="middle" fontSize="12.5" fontWeight="650" fill="#f2f6ff">{GROUP_LABEL[g.group] ?? g.group} <tspan fill="#a9b8ce" fontWeight="400">{g.assigned}/{g.target}</tspan></text>
            <text x={x} y={y + rad + 29} textAnchor="middle" fontSize="10.5" fill={g.validated ? "#7ee2a8" : "#a9b8ce"}>{g.validated} validated · {g.tf}</text>
          </g>
        ))}
      </svg>
      <div className="row wrap tiny dim" style={{ gap: 14 }}>
        <Legend c="var(--good)" t="available" /><Legend c="var(--warn)" t="degraded (data late)" />
        <Legend c="#33445f" t="blocked (no distinct market)" /><Legend c="var(--accent)" t="starting" />
        <span className="row" style={{ gap: 6 }}><svg width="12" height="12"><circle cx="6" cy="6" r="4" fill="var(--good)" stroke="#f2f6ff" strokeWidth="1.2" /></svg>holds a position</span>
        <span>A dot grows briefly only when that agent received new market data since the last refresh.</span>
      </div>
      <div className="scroll" style={{ marginTop: 10 }}>
        <table className="t small">
          <thead><tr><th>Role</th><th>IDs</th><th>Bar</th><th>Candidate templates</th><th className="num">Assigned</th><th className="num">Fresh data</th><th className="num">Validated</th><th>Gap</th></tr></thead>
          <tbody>{groups.map((g) => (
            <tr key={g.group}><td><b>{g.label}</b><div className="tiny muted">{g.why}</div></td><td className="mono tiny">{g.ids}</td>
              <td className="mono tiny">{g.tf}</td><td className="mono tiny">{(g.candidates ?? []).join(", ")}</td>
              <td className="num mono">{g.assigned}/{g.target}</td><td className="num mono">{g.ready}</td><td className="num mono">{g.validated}</td>
              <td className="tiny dim">{g.gap ?? "none"}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function Legend({ c, t }: { c: string; t: string }) {
  return <span className="row" style={{ gap: 6 }}><span style={{ width: 9, height: 9, borderRadius: 9, background: c, display: "inline-block" }} />{t}</span>;
}

// ---------------------------------------------------------------- agent grid: searchable, filterable, virtualized
const ROW_H = 156, HEAD_H = 34, MIN_W = 260;
type Row = { kind: "head"; label: string; n: number } | { kind: "cards"; items: Agent[] };

function AgentGrid({ agents, groups, onOpen }: { agents: Agent[]; groups: any[]; onOpen: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [state, setState] = useState("");
  const [market, setMarket] = useState("");
  const [memeOnly, setMemeOnly] = useState(false);
  const [by, setBy] = useState<"group" | "market" | "venue" | "job">("group");
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  const [top, setTop] = useState(0);
  const viewH = 600;

  useLayoutEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const markets = useMemo(() => Array.from(new Set(agents.map((a) => a.market).filter(Boolean))).sort() as string[], [agents]);
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return agents.filter((a) => (!group || a.group === group) && (!state || a.runtime === state) && (!market || a.market === market) &&
      (!memeOnly || a.meme) &&
      (!s || a.id.toLowerCase().includes(s) || a.partition.some((p) => p.toLowerCase().includes(s)) || a.job.includes(s) ||
        (a.strategies ?? []).some((x) => x.toLowerCase().includes(s))));
  }, [agents, q, group, state, market, memeOnly]);

  const cols = Math.max(1, Math.floor(width / MIN_W));
  const rows = useMemo(() => {
    const key = (a: Agent) => by === "group" ? (GROUP_LABEL[a.group] ?? a.group) : by === "market" ? (a.market ?? "no market")
      : by === "venue" ? (a.venue ?? "no venue") : a.job;
    const buckets = new Map<string, Agent[]>();
    for (const a of shown) {
      const k = key(a);
      if (!buckets.has(k)) buckets.set(k, []);
      buckets.get(k)!.push(a);
    }
    const out: Row[] = [];
    for (const [label, items] of buckets) {
      out.push({ kind: "head", label, n: items.length });
      for (let i = 0; i < items.length; i += cols) out.push({ kind: "cards", items: items.slice(i, i + cols) });
    }
    return out;
  }, [shown, by, cols]);

  const offsets = useMemo(() => {
    let y = 0;
    return rows.map((r) => { const o = y; y += r.kind === "head" ? HEAD_H : ROW_H; return o; });
  }, [rows]);
  const total = rows.length ? offsets[offsets.length - 1] + (rows[rows.length - 1].kind === "head" ? HEAD_H : ROW_H) : 0;
  const first = Math.max(0, offsets.findIndex((o, i) => o + (rows[i].kind === "head" ? HEAD_H : ROW_H) >= top) - 2);
  let last = first;
  while (last < rows.length && offsets[last] < top + viewH + ROW_H * 2) last++;

  return (
    <div style={{ padding: "10px 14px 12px" }} className="col">
      <div className="row wrap">
        <input placeholder="Search agent, market or strategy" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search agents" style={{ flex: "1 1 220px" }} />
        <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Coverage group">
          <option value="">All roles</option>{groups.map((g) => <option key={g.group} value={g.group}>{GROUP_LABEL[g.group] ?? g.group}</option>)}
        </select>
        <select value={state} onChange={(e) => setState(e.target.value)} aria-label="State">
          <option value="">All states</option>{["available", "degraded", "blocked", "starting", "stopped"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={market} onChange={(e) => setMarket(e.target.value)} aria-label="Market">
          <option value="">All markets</option>{markets.map((m) => <option key={m}>{m}</option>)}
        </select>
        <select value={by} onChange={(e) => setBy(e.target.value as any)} aria-label="Group by">
          <option value="group">Group by role</option><option value="market">Group by asset class</option>
          <option value="venue">Group by venue</option><option value="job">Group by current job</option>
        </select>
        <label className="row small" style={{ gap: 5 }} title="Seed-list tags: unverified classification"><input type="checkbox" checked={memeOnly} onChange={(e) => setMemeOnly(e.target.checked)} />Meme coins</label>
        <span className="tiny muted">{shown.length} of {agents.length}</span>
      </div>
      <div ref={box} className="vgrid" style={{ height: viewH }} onScroll={(e) => setTop((e.target as HTMLDivElement).scrollTop)}>
        {!rows.length ? <Empty>No agent matches.</Empty> : (
          <div style={{ height: total, position: "relative" }}>
            {rows.slice(first, last).map((r, k) => {
              const i = first + k;
              return r.kind === "head"
                ? <div key={`h-${r.label}-${i}`} className="vhead" style={{ top: offsets[i], height: HEAD_H }}>{r.label} <span className="muted">· {r.n}</span></div>
                : <div key={`r-${i}`} className="vrow" style={{ top: offsets[i], height: ROW_H, gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
                  {r.items.map((a) => <AgentCard key={a.id} a={a} onOpen={onOpen} />)}
                </div>;
            })}
          </div>
        )}
      </div>
      <div className="note">Only the visible cards are drawn (the list is virtualized). Blocked agents have no distinct market yet and are never counted as ready.</div>
    </div>
  );
}

function AgentCard({ a, onOpen }: { a: Agent; onOpen: (id: string) => void }) {
  const iid = a.partition[0];
  const d = a.last_decision;
  return (
    <button className={`agent-card ${a.runtime}`} onClick={() => onOpen(a.id)} title={a.detail}>
      <div className="spread"><span><b className="mono">{a.id}</b> <span className="tiny muted">{GROUP_LABEL[a.group] ?? a.group}{a.meme ? " · meme" : ""}</span></span><Badge kind={RUNTIME_KIND[a.runtime] ?? ""}>{a.runtime}</Badge></div>
      <div className="tiny ell">{iid ? <><span className="mono">{iid}</span>{a.last_price && <span className="dim"> · {fmt.price(a.last_price)} · {fmt.ago(a.last_input_ts)}</span>}</> : <span className="muted">no distinct market</span>}</div>
      <div className="tiny ell dim"><b style={{ color: "var(--text)" }}>{a.job}</b>{a.version ? ` · v${a.version.version} ${a.version.strategy_id}` : ""}</div>
      <div className="tiny ell" title={a.permission_reason}>{a.permission ? <span className="pos">may open trades</span> : <span className="muted">entries off: {a.permission_reason}</span>}</div>
      <div className="tiny ell muted">budget {fmt.money(a.budget)} · pos {a.position ?? "—"} · orders {a.open_orders ?? 0} · fees {a.fees ? fmt.money(a.fees) : "—"}</div>
      <div className="tiny ell muted">{d ? <>last decision <b className="dim">{d.outcome}</b> {fmt.ago(d.ts)}</> : "no decision yet"}{a.unrealized ? <> · <span className={tone(a.unrealized)}>{fmt.signed(a.unrealized)}</span> open</> : null}{a.mistakes ? <span className="warn"> · {a.mistakes} mistake(s)</span> : null}{a.errors ? <span className="neg"> · {a.errors} error(s)</span> : null}</div>
    </button>
  );
}

// ---------------------------------------------------------------- one agent
function AgentDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const live = useLive();
  const [d, , err] = usePoll<any>(`/api/fleet/${id}`, 5000, [id]);
  const [probe, setProbe] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const runProbe = async () => {
    setBusy(true);
    try {
      setProbe(await api.post(`/api/fleet/${id}/probe`));
    } catch (e: any) {
      live.toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Trading agent ${id}`} right={d ? <Badge kind={RUNTIME_KIND[d.runtime] ?? ""} dot>{d.runtime}</Badge> : null} onClose={onClose}>
      {err && <div className="callout bad">{err}</div>}
      {!d ? <Empty>Loading…</Empty> : (
        <>
          <div className={`callout ${d.permission ? "good" : ""} small`}>
            <b>{d.permission ? "May open paper trades. " : "Entries off. "}</b>{d.permission_reason}
            {d.suspended && d.suspended.until > Date.now() && <div className="tiny">Suspended until {fmt.datetime(d.suspended.until)}: {d.suspended.why}</div>}
            {d.day_stopped && <div className="tiny">Daily loss limit reached on {d.day_stopped} (UTC).</div>}
            <div className="tiny muted">Exits are always allowed. The risk service still checks every order.</div>
          </div>
          <div className="grid g-2">
            <Card title="Role (set by the master)">
              <div className="kv small">
                <div>Role</div><div><b>{d.role.label}</b></div>
                <div>Family</div><div>{d.role.family}</div>
                <div>Bar size</div><div className="mono">{d.role.tf}</div>
                <div>Candidates</div><div className="mono tiny">{d.role.candidates.join(", ")}</div>
                <div>Evidence</div><div className="dim tiny">{d.role.why}</div>
              </div>
            </Card>
            <Card title="Assignment and state">
              <div className="kv small">
                <div>Market</div><div className="mono">{d.partition.length ? d.partition.join(", ") : "none (blocked)"}</div>
                <div>Asset class</div><div>{d.market ?? "—"}</div>
                <div>Job</div><div><b>{d.job}</b></div>
                <div>Detail</div><div className="dim">{d.detail}</div>
                <div>Next action</div><div className="dim">{d.next_action ?? "—"}</div>
                <div>Last data</div><div className="mono">{fmt.price(d.last_price)} · {fmt.ago(d.last_input_ts)}{d.fresh ? "" : " (not fresh)"}</div>
                <div>Heartbeat</div><div className="mono">{fmt.ago(d.heartbeat)} · job {d.job_ms ?? "—"} ms</div>
                <div>Virtual budget</div><div className="mono">{fmt.money(d.budget)} <span className="tiny muted">(zero without the master's permission)</span></div>
              </div>
            </Card>
          </div>
          <Card title="Versions" sub="every trained policy; chosen on validation data, never on the held-out test" flush>
            {!d.versions.length ? <Empty>No version yet: the master is training this agent, or its market has no data. It stays in cash.</Empty> : (
              <div className="scroll">
                <table className="t small"><thead><tr><th>Version</th><th>Status</th><th>Strategy</th><th className="num">Val. Sharpe</th><th className="num">Test Sharpe</th><th className="num">Test trades</th><th>Verdict</th><th>Why</th></tr></thead>
                  <tbody>{[...d.versions].reverse().map((v: any) => (
                    <tr key={v.version}><td className="mono">v{v.version}<div className="tiny muted">{fmt.datetime(v.created)}</div></td>
                      <td><Badge kind={VERSION_KIND[v.status] ?? ""}>{v.status}</Badge></td><td className="mono tiny">{v.strategy_id}<div className="muted">{v.tf} · {v.experiment_id}</div></td>
                      <td className="num mono">{fmt.num(v.training?.validation?.sharpe, 2)}</td><td className="num mono">{fmt.num(v.training?.test?.sharpe, 2)}</td>
                      <td className="num mono">{v.training?.test?.trades ?? "—"}</td><td className="tiny">{v.training?.verdict ?? "—"}</td>
                      <td className="tiny dim">{v.reason}{v.paper ? ` · paper: ${v.paper.trips} trip(s), P&L ${fmt.signed(v.paper.pnl)}` : ""}</td></tr>
                  ))}</tbody></table>
              </div>
            )}
          </Card>
          <Card title="Shadow check" sub="runs this agent's full decision pipeline once; nothing is sent" right={<button className="btn sm" disabled={busy || !d.partition.length} onClick={runProbe}>{busy ? "Running…" : "Run check"}</button>}>
            {!probe ? <div className="small dim">Press Run check to see what this agent would decide on the latest completed bar.</div> : (
              <div className="small"><Badge>{probe.outcome}</Badge> <span className="mono tiny">{probe.strategy_id} {probe.tf}{probe.version ? ` v${probe.version}` : " (no version: first candidate)"}</span><div className="dim">{probe.reason}</div></div>
            )}
          </Card>
          <Card title="Positions and orders" flush>
            {!d.positions.length ? <Empty>No position. {d.open_orders ? `${d.open_orders} working order(s).` : "No working orders."}</Empty> : (
              <table className="t small"><thead><tr><th>Instrument</th><th className="num">Qty</th><th className="num">Avg</th><th className="num">Unrealized</th><th className="num">Realized</th></tr></thead>
                <tbody>{d.positions.map((p: any) => (
                  <tr key={p.instrument_id}><td className="mono">{p.instrument_id}</td><td className="num mono">{p.qty}</td><td className="num mono">{fmt.num(p.avg_price, 6)}</td>
                    <td className={`num mono ${tone(p.unrealized)}`}>{fmt.signed(p.unrealized)}</td><td className={`num mono ${tone(p.realized)}`}>{fmt.signed(p.realized)}</td></tr>
                ))}</tbody></table>
            )}
          </Card>
          <Card title="Recent decisions on this market" flush>
            {!d.decisions.length ? <Empty>No decision yet: decisions start when this agent's validated version runs.</Empty> : (
              <table className="t small"><thead><tr><th>Time</th><th>Strategy</th><th>Outcome</th><th>Reason</th></tr></thead>
                <tbody>{d.decisions.map((x: any, i: number) => (
                  <tr key={i}><td className="nowrap">{fmt.datetime(x.ts)}</td><td className="mono tiny">{x.strategy_id}</td><td><Badge>{x.outcome}</Badge></td><td className="tiny dim">{x.reason}</td></tr>
                ))}</tbody></table>
            )}
          </Card>
          <Card title="Mistakes and lessons" sub="each mistake has a root cause; the first one becomes a lesson shared by all agents" flush>
            {!d.mistakes.length ? <Empty>No mistakes recorded for this agent.</Empty> : (
              <table className="t small"><thead><tr><th>Time</th><th>Root cause</th><th>Repeat</th><th>Detail</th></tr></thead>
                <tbody>{d.mistakes.map((m: any) => (
                  <tr key={m.mistake_id}><td className="nowrap">{fmt.datetime(m.ts)}</td><td className="mono tiny">{m.root_cause}</td>
                    <td>{m.repeat ? <Badge kind="warn">repeat</Badge> : <Badge kind="info">new lesson</Badge>}</td>
                    <td className="tiny dim" style={{ wordBreak: "break-word" }}>{JSON.stringify(m.detail).slice(0, 160)}</td></tr>
                ))}</tbody></table>
            )}
          </Card>
          <div className="grid g-2">
            <Card title="Errors (isolated to this agent)">
              {!d.errors.length ? <Empty>None.</Empty> : d.errors.map((e: any, i: number) => <div key={i} className="small"><span className="mono muted">{fmt.time(e.ts)}</span> <span className="neg">{e.error}</span></div>)}
            </Card>
            <Card title="Dependencies and tools">
              <div className="kv small">
                {Object.entries(d.dependencies).map(([k, v]: any) => <Fragment key={k}><div>{k}</div><div>{v === true ? "yes" : v === false ? "no" : v ?? "—"}</div></Fragment>)}
              </div>
              <ul className="small dim" style={{ margin: "10px 0 0", paddingLeft: 18 }}>{d.tools.map((t: string) => <li key={t}>{t}</li>)}</ul>
            </Card>
          </div>
        </>
      )}
    </Drawer>
  );
}

// ---------------------------------------------------------------- the master's recent actions
function MasterActivity({ items }: { items: any[] }) {
  if (!items?.length) return null;
  return (
    <div style={{ padding: "0 14px 12px" }} className="col">
      <div className="tiny muted">MASTER AGENT: RECENT ACTIONS</div>
      <div className="scroll" style={{ maxHeight: 220 }}>
        {items.map((a: any, i: number) => <div key={i} className="tiny"><span className="muted mono">{fmt.time(a.ts)}</span> {a.message}</div>)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- continuous learning: lessons, mistakes, regression
function LearningPanel() {
  const live = useLive();
  const [l, reload] = usePoll<any>("/api/learning", 6000);
  const [busy, setBusy] = useState(false);
  if (!l) return <Empty>Loading…</Empty>;
  const m = l.metrics;
  const reg = m.regression;
  const replay = async () => {
    setBusy(true);
    try {
      const r: any = await api.post("/api/learning/replay");
      live.toast(r.failed.length ? `${r.failed.length} scenario(s) FAILED` : `Regression replay: ${r.passed}/${r.scenarios} passed`, r.failed.length ? "error" : "ok");
    } catch (e: any) {
      live.toast(e.message, "error");
    } finally {
      setBusy(false);
      reload();
    }
  };
  const rate = (w: any) => w.per_100_decisions === null ? "—" : `${w.per_100_decisions}`;
  return (
    <div style={{ padding: "10px 14px 12px" }} className="col">
      <div className="note">{l.note}</div>
      <div className="stats">
        <Num k="Lessons (safeguards on)" v={m.lessons} s="shared by all 100 agents" />
        <Num k="Mistakes this week" v={m.this_week.mistakes} s={`${m.this_week.repeats} repeat(s) · ${rate(m.this_week)} per 100 decisions`} />
        <Num k="Mistakes last week" v={m.last_week.mistakes} s={`${m.last_week.repeats} repeat(s) · ${rate(m.last_week)} per 100 decisions`} />
        <div className="stat"><div className="k">Regression replay</div><div className="v">{reg ? `${reg.passed}/${reg.scenarios}` : "—"}</div>
          <div className="s">{reg ? `${reg.failed.length ? "FAILED" : "passed"} · ${fmt.ago(reg.ts)} · ${reg.trigger}` : "not run yet"}</div></div>
      </div>
      <div className="row"><button className="btn sm" disabled={busy} onClick={replay}>{busy ? "Replaying…" : "Run regression replay now"}</button>
        <span className="tiny muted">Replays every stored mistake through its safeguard; each must now be blocked or shrunk.</span></div>
      <Card title="Lessons" flush>
        {!l.lessons.length ? <Empty>No lessons yet: no mistake has been recorded.</Empty> : (
          <div className="scroll"><table className="t small"><thead><tr><th>Root cause</th><th>Safeguard (all agents)</th><th>First seen</th><th className="num">Occurrences</th><th className="num">Repeats</th></tr></thead>
            <tbody>{l.lessons.map((x: any) => (
              <tr key={x.lesson_id}><td className="mono tiny">{x.root_cause}<div className="muted">{x.kind}</div></td><td className="tiny"><b>{x.safeguard}</b><div className="dim">{x.description}</div></td>
                <td className="tiny nowrap">{fmt.datetime(x.created)}<div className="muted">{x.first_agent ?? "system"}</div></td>
                <td className="num mono">{x.occurrences}</td><td className={`num mono ${x.repeats ? "warn" : ""}`}>{x.repeats}</td></tr>
            ))}</tbody></table></div>
        )}
      </Card>
      <Card title="Recent mistakes" flush>
        {!l.mistakes.length ? <Empty>None recorded.</Empty> : (
          <div className="scroll" style={{ maxHeight: 360 }}><table className="t small"><thead><tr><th>Time</th><th>Agent</th><th>Market</th><th>Root cause</th><th>Repeat</th><th>Detail</th></tr></thead>
            <tbody>{l.mistakes.map((x: any) => (
              <tr key={x.mistake_id}><td className="nowrap tiny">{fmt.datetime(x.ts)}</td><td className="mono">{x.agent_id ?? "—"}</td><td className="mono tiny">{x.instrument_id ?? "—"}</td>
                <td className="mono tiny">{x.root_cause}</td><td>{x.repeat ? <Badge kind="warn">repeat</Badge> : <Badge kind="info">new</Badge>}</td>
                <td className="tiny dim" style={{ wordBreak: "break-word" }}>{JSON.stringify(x.detail).slice(0, 140)}</td></tr>
            ))}</tbody></table></div>
        )}
      </Card>
      <Card title="Regression runs" flush>
        {!l.regression_runs.length ? <Empty>None yet.</Empty> : (
          <table className="t small"><thead><tr><th>Time</th><th>Trigger</th><th className="num">Passed</th><th>Failed</th></tr></thead>
            <tbody>{l.regression_runs.map((r: any) => (
              <tr key={r.run_id}><td className="nowrap tiny">{fmt.datetime(r.ts)}</td><td className="tiny">{r.trigger}</td><td className="num mono">{r.passed}/{r.scenarios}</td>
                <td className="tiny">{r.failed.length ? <span className="neg">{r.failed.map((f: any) => `${f.root_cause}: ${f.why}`).join("; ")}</span> : "none"}</td></tr>
            ))}</tbody></table>
        )}
      </Card>
      <Card title="Root causes the system recognises">
        <div className="kv small">{Object.entries(l.root_causes).map(([k, v]: any) => <Fragment key={k}><div className="mono tiny">{k}</div><div className="tiny"><span className="dim">{v.what}.</span> Safeguard: <b>{v.safeguard}</b>: {v.does}.</div></Fragment>)}</div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- shared operational capabilities C01-C50
const CAP_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  running: "good", completed: "info", idle: "", "waiting for data": "warn", paused: "warn", blocked: "bad", degraded: "warn",
  failed: "bad", unavailable: "",
};

function Capabilities() {
  const [r] = usePoll<any>("/api/roles", 5000);
  const [q, setQ] = useState("");
  if (!r) return <Empty>Loading…</Empty>;
  const c = r.counts;
  const s = q.trim().toLowerCase();
  const rows = r.roles.filter((x: any) => !s || `${x.id} ${x.name} ${x.component} ${x.state}`.toLowerCase().includes(s));
  return (
    <div style={{ padding: "10px 14px 12px" }} className="col">
      <div className="note">Support services are not trading agents and are not counted in the fleet. {r.model}.</div>
      <div className="stats">
        <Num k="Capabilities" v={c.configured_roles} s="C01–C50" />
        <Num k="Unavailable" v={c.unavailable} s="need a feed or product not connected" />
        <Num k="Signal agent functions" v={c.agent_functions} s="vote or advise inside decisions" />
        <Num k="Active model calls" v={c.active_model_calls} s="no cloud AI connected" />
      </div>
      <input placeholder="Search capabilities" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search capabilities" />
      <div className="scroll" style={{ maxHeight: 520 }}>
        <table className="t small">
          <thead><tr><th>ID</th><th>Capability</th><th>Implementation</th><th>State</th><th>Latest</th></tr></thead>
          <tbody>{rows.map((x: any) => (
            <tr key={x.id}>
              <td className="mono muted">{x.id}</td>
              <td><b>{x.name}</b><div className="tiny muted">{x.component}</div></td>
              <td className="tiny">{x.implementation}{x.agent_functions ? ` · ${x.agent_functions} functions` : ""}</td>
              <td><Badge kind={CAP_KIND[x.state] ?? ""}>{x.state}</Badge></td>
              <td className="tiny dim">{x.latest}{x.latest_ts ? ` · ${fmt.ago(x.latest_ts)}` : ""}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
