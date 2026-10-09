import { useState } from "react";
import { api, fmt, tone } from "../api";
import { Badge, Card, Check, Empty, Modal, Stat } from "../components/ui";
import { useLive, usePoll } from "../store";

const CRED_LABEL: Record<string, string> = {
  key_id: "API key ID", secret: "API secret", token: "Access token", account_id: "Account ID", key: "API key",
  key_name: "API key name", private_key: "EC private key (PEM)",
};
const CAPS = ["stocks", "etfs", "crypto", "forex", "futures", "paper_mode", "fractional", "shorting", "bracket_orders", "websocket", "historical_data"];

function statusBadge(c: any) {
  if (c.broker === "paper") return <Badge kind="sim" dot>SIMULATED · CONNECTED</Badge>;
  if (c.status === "connected") return <Badge kind="good" dot>CONNECTED</Badge>;
  if (c.saved_status === "requires connection" || c.badge === "REQUIRES CONNECTION") return <Badge kind="warn" dot>REQUIRES CONNECTION</Badge>;
  if (c.saved_status === "error") return <Badge kind="bad" dot>ERROR</Badge>;
  return <Badge dot>{(c.status ?? "disconnected").toUpperCase()}</Badge>;
}

export default function BrokerMoney() {
  const live = useLive();
  const [conns, reload] = usePoll<any[]>("/api/connections", 10000);
  const [brokers] = usePoll<any>("/api/brokers", 0);
  const [adding, setAdding] = useState(false);
  const [balance, setBalance] = useState(false);
  const [recon, setRecon] = useState<any>(null);
  const [readyFor, setReadyFor] = useState<string | null>(null);
  const o = live.overview!;
  const a = live.account;
  const paper = conns?.find((c) => c.connection_id === "paper");
  const act = async (fn: () => Promise<any>, ok?: string) => {
    try {
      const r = await fn();
      if (ok) live.toast(ok, "ok");
      reload();
      await live.refresh();
      return r;
    } catch (e: any) {
      live.toast(e.message, "error");
    }
  };

  return (
    <>
      <div className="grid g-2">
        <Card title="Trading account in use" right={<Badge kind={o.mode === "live" ? "bad" : "sim"}>{o.mode === "live" ? "LIVE BROKER DATA" : "SIMULATED"}</Badge>}>
          <div className="stats">
            <Stat k="Equity" v={fmt.money(a?.account?.equity, a?.account?.currency)} />
            <Stat k="Cash" v={fmt.money(a?.account?.cash, a?.account?.currency)} />
            <Stat k="Buying power" v={fmt.money(a?.account?.buying_power, a?.account?.currency)} />
            <Stat k="Margin used" v={fmt.money(a?.account?.margin_used, a?.account?.currency)} />
          </div>
          <div className="row wrap" style={{ marginTop: 10 }}>
            <span className="small dim">Account <b className="mono">{a?.account?.account}</b> · {a?.account?.environment} · updated {fmt.time(a?.account?.as_of)}</span>
            <span className="grow" />
            {o.mode !== "live" && <button className="btn sm" onClick={() => setBalance(true)}>Set paper balance…</button>}
            <button className="btn sm" onClick={async () => setRecon(await act(() => api.post("/api/reconcile")))}>Reconcile now</button>
          </div>
          <div className="note" style={{ marginTop: 8 }}>
            Permissions: {Object.entries(a?.account?.permissions ?? {}).map(([k, v]) => `${k}: ${String(v)}`).join(" · ") || "—"}.
            This software never requests withdrawal permission.
          </div>
          {recon && (
            <div className={`callout ${recon.ok ? "good" : "bad"}`} style={{ marginTop: 10 }}>
              {recon.ok ? "Reconciliation clean: positions rebuilt from fills match the stored positions, and the ledger balances." :
                <>Differences found:<ul style={{ margin: "6px 0 0 18px" }}>{recon.problems.map((p: string) => <li key={p}>{p}</li>)}</ul></>}
            </div>
          )}
        </Card>

        <LivePanel o={o} conns={conns ?? []} onReadiness={setReadyFor} act={act} />
      </div>

      <Card title="Broker connections" sub={`credentials go into this computer's vault (${o.vault ?? "—"}) and are never shown again`} right={<button className="btn sm primary" onClick={() => setAdding(true)}>+ Add connection</button>} flush>
        {!conns ? <Empty>Loading…</Empty> : (
          <div className="scroll">
            <table className="t">
              <thead><tr><th>Connection</th><th>Environment</th><th>Status</th><th>Adapter</th><th className="num">Equity</th><th>Credential</th><th></th></tr></thead>
              <tbody>
                {conns.map((c) => (
                  <tr key={c.connection_id}>
                    <td><b>{c.label ?? c.broker}</b><div className="tiny muted mono">{c.connection_id}</div></td>
                    <td><Badge kind={c.environment === "live" ? "bad" : "info"}>{c.environment}</Badge></td>
                    <td>{statusBadge(c)}{c.last_error && <div className="tiny neg">{c.last_error}</div>}</td>
                    <td>{c.verified ? <Badge kind="good">verified</Badge> : <Badge kind="warn">UNVERIFIED</Badge>}</td>
                    <td className="num mono">{c.balance ? fmt.money(c.balance.equity, c.balance.currency) : "—"}</td>
                    <td className="mono small">{c.masked ? Object.entries(c.masked).map(([k, v]) => `${k}: ${v}`).join(" · ") : c.broker === "paper" ? "none needed" : "—"}</td>
                    <td className="nowrap">
                      {c.connection_id !== "paper" && <>
                        <button className="btn sm" onClick={() => act(() => api.post(`/api/connections/${c.connection_id}/test`), "Connection tested")}>Test</button>{" "}
                        <button className="btn sm" onClick={() => setReadyFor(c.connection_id)}>Readiness</button>{" "}
                        <button className="btn sm ghost" onClick={() => confirm("Remove this connection and delete its stored credentials?") && act(() => api.del(`/api/connections/${c.connection_id}`), "Connection removed")}>Remove</button>
                      </>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {paper && <div className="note" style={{ padding: "8px 14px", borderTop: "1px solid var(--line)" }}>{paper.setup}</div>}
      </Card>

      <Card title="What each broker supports" sub="from each adapter's declared capabilities; a connection must pass an acceptance test before it counts as verified" flush>
        {!brokers ? <Empty>Loading…</Empty> : (
          <div className="scroll">
            <table className="t small">
              <thead><tr><th>Broker</th><th>Environments</th>{CAPS.map((c) => <th key={c} className="center">{c.replace(/_/g, " ")}</th>)}</tr></thead>
              <tbody>{brokers.matrix.map((r: any) => (
                <tr key={r.broker}><td><b>{r.label}</b></td><td>{r.environments.join(", ")}</td>
                  {CAPS.map((c) => <td key={c} className="center">{r[c] === true ? "✓" : r[c] === false || r[c] === undefined ? <span className="muted">—</span> : <span className="tiny">{String(r[c])}</span>}</td>)}
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>

      <Coverage />
      <OrdersFills />

      {adding && brokers && <AddConnection adapters={brokers.adapters} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload(); }} />}
      {balance && <PaperBalance onClose={() => setBalance(false)} />}
      {readyFor && <Readiness cid={readyFor} onClose={() => setReadyFor(null)} />}
    </>
  );
}

function LivePanel({ o, conns, onReadiness, act }: { o: any; conns: any[]; onReadiness: (c: string) => void; act: (fn: () => Promise<any>, ok?: string) => Promise<any> }) {
  const liveConns = conns.filter((c) => c.environment === "live");
  const [cid, setCid] = useState("");
  const [ack, setAck] = useState("");
  const [cap, setCap] = useState("");
  const [loss, setLoss] = useState("");
  if (o.live?.armed) {
    return (
      <Card title="Live trading" right={<Badge kind="bad" dot>ARMED</Badge>}>
        <div className="callout bad">LIVE is armed on <b className="mono">{o.live.connection_id}</b>. Orders from running bots go to your broker with real money.
          Caps: maximum capital {fmt.money(o.live.max_capital)}, daily loss {fmt.money(o.live.daily_loss)}. Live never resumes by itself after a restart.</div>
        <div className="row" style={{ marginTop: 10 }}><button className="btn danger" onClick={() => act(() => api.post("/api/live/disarm"), "Live disarmed: back to paper")}>Disarm live → paper</button></div>
      </Card>
    );
  }
  return (
    <Card title="Live trading" right={<Badge kind="good" dot>OFF · PAPER</Badge>}>
      <div className="col">
        <div className="note">The system starts and stays in PAPER. Real-money trading needs: a LIVE connection that is connected, an adapter verified by an
          acceptance test with your account, every readiness check passing, your typed acknowledgement and caps. Your broker's own eligibility,
          jurisdiction and permission rules always apply; this software cannot bypass them.</div>
        {liveConns.length === 0 ? <div className="callout">No live connections saved. Add one below (it stays disconnected until you test it).</div> : (
          <>
            <label className="field">Live connection
              <select value={cid} onChange={(e) => setCid(e.target.value)}>
                <option value="">Choose…</option>
                {liveConns.map((c) => <option key={c.connection_id} value={c.connection_id}>{c.label} ({c.connection_id})</option>)}
              </select>
            </label>
            {cid && <button className="btn sm" onClick={() => onReadiness(cid)}>Show readiness checklist</button>}
            <div className="row">
              <label className="field grow">Maximum capital (USD)<input inputMode="decimal" value={cap} onChange={(e) => setCap(e.target.value)} /></label>
              <label className="field grow">Daily loss cap (USD)<input inputMode="decimal" value={loss} onChange={(e) => setLoss(e.target.value)} /></label>
            </div>
            <label className="field">Type <b className="mono" style={{ color: "var(--text)" }}>{o.live_ack}</b>
              <input value={ack} onChange={(e) => setAck(e.target.value)} spellCheck={false} />
            </label>
            <button className="btn danger" disabled={!cid || ack.trim() !== o.live_ack || !(Number(cap) > 0) || !(Number(loss) > 0)}
              onClick={() => act(() => api.post("/api/live/arm", { connection_id: cid, ack: ack.trim(), max_capital: cap, daily_loss: loss }), "LIVE ARMED")}>
              Arm live trading
            </button>
          </>
        )}
      </div>
    </Card>
  );
}

function AddConnection({ adapters, onClose, onSaved }: { adapters: Record<string, any>; onClose: () => void; onSaved: () => void }) {
  const live = useLive();
  const names = Object.keys(adapters);
  const [broker, setBroker] = useState(names[0]);
  const ad = adapters[broker];
  const [env, setEnv] = useState<string>(ad.environments[0]);
  const [label, setLabel] = useState("");
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  return (
    <Modal title="Add a broker connection" onClose={onClose}>
      <label className="field">Broker
        <select value={broker} onChange={(e) => { setBroker(e.target.value); setEnv(adapters[e.target.value].environments[0]); setCreds({}); }}>
          {names.map((n) => <option key={n} value={n}>{adapters[n].label}</option>)}
        </select>
      </label>
      <div className="note">{ad.setup}</div>
      <label className="field">Environment
        <select value={env} onChange={(e) => setEnv(e.target.value)}>{ad.environments.map((e: string) => <option key={e} value={e}>{e === "live" ? "LIVE (real money)" : "paper / practice"}</option>)}</select>
      </label>
      <label className="field">Name<input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={ad.label} /></label>
      {ad.needs.map((k: string) => (
        <label key={k} className="field">{CRED_LABEL[k] ?? k}
          {k === "private_key"
            ? <textarea rows={4} value={creds[k] ?? ""} onChange={(e) => setCreds({ ...creds, [k]: e.target.value })} spellCheck={false} autoComplete="off" />
            : <input type={k.includes("secret") || k.includes("token") || k === "key" ? "password" : "text"} value={creds[k] ?? ""} autoComplete="off" spellCheck={false}
                onChange={(e) => setCreds({ ...creds, [k]: e.target.value })} />}
        </label>
      ))}
      {!ad.verified && <div className="callout warn small">This adapter is UNVERIFIED: it was written against the broker's documentation but has not passed an acceptance test with a real account. It can be connected and tested, but live trading stays locked until it is verified.</div>}
      <div className="note">Use keys with trading permission only. Never enable withdrawals.</div>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={busy || ad.needs.some((k: string) => !creds[k]?.trim())} onClick={async () => {
          setBusy(true);
          try {
            await api.post("/api/connections", { broker, environment: env, label, credentials: creds });
            live.toast("Saved to the vault. Press Test to connect.", "ok");
            setCreds({});
            onSaved();
          } catch (e: any) {
            live.toast(e.message, "error");
          } finally {
            setBusy(false);
          }
        }}>Save to vault</button>
      </div>
    </Modal>
  );
}

function PaperBalance({ onClose }: { onClose: () => void }) {
  const live = useLive();
  const [v, setV] = useState("100000");
  return (
    <Modal title="Set the paper balance" onClose={onClose}>
      <div className="dim">Sets the SIMULATED account equity to this amount. It is recorded as an adjustment in the ledger, never as profit or loss.</div>
      <label className="field">New equity (USD)<input inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} autoFocus /></label>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={!(Number(v) > 0)} onClick={async () => {
          try {
            await api.post("/api/paper/balance", { amount: v });
            live.toast("Paper balance set", "ok");
            await live.refresh();
            onClose();
          } catch (e: any) {
            live.toast(e.message, "error");
          }
        }}>Set balance</button>
      </div>
    </Modal>
  );
}

function Readiness({ cid, onClose }: { cid: string; onClose: () => void }) {
  const [r] = usePoll<any>(`/api/live/readiness/${cid}`, 0, [cid]);
  return (
    <Modal title={`Live readiness · ${cid}`} onClose={onClose}>
      {!r ? <Empty>Checking…</Empty> : (
        <>
          {r.items.map((i: any) => <Check key={i.check} ok={i.passed} name={i.check} detail={i.detail} />)}
          <div className={`callout ${r.items.every((i: any) => i.passed) ? "good" : "bad"}`}>
            {r.items.every((i: any) => i.passed) ? "All checks pass: live trading can be armed." : "LIVE NOT READY: every item must pass before arming."}
          </div>
        </>
      )}
      <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

function OrdersFills() {
  const [orders] = usePoll<any[]>("/api/orders?limit=100", 6000);
  const [fills] = usePoll<any[]>("/api/fills?limit=100", 6000);
  const [tab, setTab] = useState<"orders" | "fills">("orders");
  return (
    <Card title="Orders & fills" right={
      <div className="seg"><button className={tab === "orders" ? "on" : ""} onClick={() => setTab("orders")}>Orders</button><button className={tab === "fills" ? "on" : ""} onClick={() => setTab("fills")}>Fills</button></div>
    } flush>
      <div className="scroll" style={{ maxHeight: 420 }}>
        {tab === "orders" && (!orders?.length ? <Empty>No orders yet.</Empty> : (
          <table className="t small">
            <thead><tr><th>Time</th><th>Client id</th><th>Env</th><th>Instrument</th><th>Side</th><th className="num">Qty</th><th className="num">Filled</th><th className="num">Avg price</th><th>Status</th><th>Reason</th></tr></thead>
            <tbody>{orders.map((r) => (
              <tr key={r.client_order_id}><td className="nowrap">{fmt.datetime(r.created)}</td><td className="mono tiny">{r.client_order_id}</td>
                <td><Badge kind={r.environment === "live" ? "bad" : "sim"}>{r.environment}</Badge></td><td>{r.instrument_id}</td><td>{r.side}</td>
                <td className="num mono">{fmt.num(r.qty, 8)}</td><td className="num mono">{fmt.num(r.filled_qty, 8)}</td><td className="num mono">{fmt.num(r.avg_fill_price, 6)}</td>
                <td><Badge kind={r.status === "FILLED" ? "good" : r.status === "REJECTED" || r.status === "UNKNOWN" ? "bad" : ""}>{r.status}</Badge></td><td className="tiny dim">{r.reason}</td></tr>
            ))}</tbody>
          </table>
        ))}
        {tab === "fills" && (!fills?.length ? <Empty>No fills yet.</Empty> : (
          <table className="t small">
            <thead><tr><th>Time</th><th>Instrument</th><th>Side</th><th className="num">Qty</th><th className="num">Price</th><th className="num">Fee</th><th className="num">Decision price</th><th className="num">Slippage</th><th>Env</th></tr></thead>
            <tbody>{fills.map((f) => {
              const slip = f.decision_price ? (Number(f.price) / Number(f.decision_price) - 1) * (f.side === "buy" ? 1 : -1) : null;
              return (
                <tr key={f.fill_id}><td className="nowrap">{fmt.datetime(f.ts)}</td><td>{f.instrument_id}</td><td>{f.side}</td>
                  <td className="num mono">{fmt.num(f.qty, 8)}</td><td className="num mono">{fmt.num(f.price, 6)}</td><td className="num mono">{fmt.money(f.fee)}</td>
                  <td className="num mono">{fmt.num(f.decision_price, 6)}</td><td className={`num mono ${tone(slip === null ? null : -slip)}`}>{slip === null ? "—" : `${(slip * 1e4).toFixed(1)} bp`}</td>
                  <td><Badge kind={f.environment === "live" ? "bad" : "sim"}>{f.environment}</Badge></td></tr>
              );
            })}</tbody>
          </table>
        ))}
      </div>
    </Card>
  );
}

function Coverage() {
  const [rows] = usePoll<any[]>("/api/coverage", 0);
  return (
    <Card title="Market coverage" sub="research, data, paper and live execution are separate states" flush>
      {!rows ? <Empty>Loading…</Empty> : (
        <div className="scroll">
          <table className="t small">
            <thead><tr><th>Market</th><th className="num">Instruments</th><th>Research</th><th>Historical data</th><th>Live data</th><th>Paper execution</th><th>Live execution</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.market}><td><b>{r.market}</b></td><td className="num">{r.instruments}</td><td>{r.research}</td><td>{r.historical_data}</td>
                <td className="tiny">{r.live_data}</td><td className="tiny">{r.paper_execution}</td>
                <td className="tiny">{String(r.live_execution).startsWith("adapter verified") ? <Badge kind="good">verified</Badge> : <span className="dim">{r.live_execution}</span>}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
