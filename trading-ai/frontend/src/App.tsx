import { useEffect, useState } from "react";
import { api } from "./api";
import { Badge, Modal, ModeBadge, PhraseConfirm, StateBadge } from "./components/ui";
import { useLive } from "./store";
import CommandCenter from "./pages/CommandCenter";
import BrokerMoney from "./pages/BrokerMoney";
import LiveIntelligence from "./pages/LiveIntelligence";

const PAGES = [
  ["/", "Command Center"],
  ["/broker", "Broker & Money"],
  ["/intelligence", "Live Intelligence"],
] as const;

export function go(path: string) {
  if (location.pathname !== path) {
    history.pushState(null, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
}

export default function App() {
  const [path, setPath] = useState(location.pathname);
  const live = useLive();
  const [estop, setEstop] = useState(false);
  const [rearm, setRearm] = useState(false);

  useEffect(() => {
    const on = () => setPath(location.pathname);
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);

  const o = live.overview;
  const page = PAGES.find(([p]) => p === path)?.[0] ?? "/";
  const kill = o?.risk?.kill_switch;
  const locked = o?.risk?.trading_locked;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" aria-hidden><rect width="32" height="32" rx="7" fill="#161e2d" /><path d="M6 22l6-7 5 4 9-11" fill="none" stroke="#4cc2ff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
          Trading AI
        </div>
        <nav className="nav">
          {PAGES.map(([p, label]) => (
            <a key={p} href={p} className={page === p ? "on" : ""} onClick={(e) => { e.preventDefault(); go(p); }}>{label}</a>
          ))}
        </nav>
        <div className="statusline">
          {o && <ModeBadge mode={o.mode} />}
          {o && <StateBadge state={o.state.state} />}
          {kill ? <Badge kind="bad" dot>STOP ALL ENGAGED</Badge> : locked ? <Badge kind="bad" dot>TRADING LOCKED</Badge> : null}
          <Badge kind={live.ws === "live" ? "good" : live.ws === "offline" ? "bad" : "warn"} dot>
            {live.ws === "live" ? "LIVE FEED" : live.ws === "offline" ? "SERVER UNREACHABLE" : "CONNECTING"}
          </Badge>
          {o?.offline && <Badge kind="warn">OFFLINE DATA</Badge>}
          {kill || locked
            ? <button className="btn sm" onClick={() => setRearm(true)}>Re-arm…</button>
            : <button className="estop" onClick={() => setEstop(true)} title="Stops every bot, cancels working orders, blocks new orders">EMERGENCY STOP</button>}
        </div>
      </header>

      {!o && live.ws !== "offline" && <div className="page"><div className="empty">Connecting to the local server…</div></div>}
      {live.ws === "offline" && (
        <div className="page"><div className="callout bad">The local server is not answering. If you closed the Trading AI window, double-click START_TRADING_AI.exe again.</div></div>
      )}
      {o && (
        <main className="page">
          {kill && (
            <div className="callout bad">
              <b>STOP ALL TRADING is engaged</b> ({kill.reason}, by {kill.by}). No new orders can be sent. Positions were kept
              unless emergency flattening is turned on. Re-arm when you have reviewed what happened.
            </div>
          )}
          {!kill && locked && (
            <div className="callout bad"><b>Trading is locked</b>: {locked.reason}. Only orders that reduce positions are allowed until you re-arm.</div>
          )}
          {o.state.state === "RECONCILIATION_REQUIRED" && (
            <div className="callout bad"><b>Reconciliation required.</b> Local records and the broker disagree. New entries are blocked. Open Broker &amp; Money → Reconcile to see the differences.</div>
          )}
          {page === "/" && <CommandCenter />}
          {page === "/broker" && <BrokerMoney />}
          {page === "/intelligence" && <LiveIntelligence />}
        </main>
      )}

      {estop && (
        <Modal title="Stop all trading now?" onClose={() => setEstop(false)}>
          <div className="dim">Stops every bot, cancels working orders and blocks all new orders until you re-arm. Open positions are
            kept (exits stay allowed) unless emergency flattening is turned on in the risk limits.</div>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn ghost" onClick={() => setEstop(false)}>Cancel</button>
            <button className="estop" autoFocus onClick={async () => {
              setEstop(false);
              try {
                await api.post("/api/emergency-stop", { reason: "owner pressed EMERGENCY STOP" });
                live.toast("STOP ALL TRADING engaged", "error");
              } catch (e: any) {
                live.toast(`Emergency stop failed: ${e.message}`, "error");
              }
              await live.refresh();
            }}>STOP ALL TRADING</button>
          </div>
        </Modal>
      )}
      {rearm && (
        <PhraseConfirm title="Re-arm trading" phrase={o?.risk?.phrases?.rearm ?? "RE-ARM TRADING"} action="Re-arm"
          body={<>Clears the kill switch and loss locks. Bots stay stopped until you start them. The day's loss reference resets to the current equity.</>}
          onConfirm={async (typed) => {
            await api.post("/api/rearm", { phrase: typed });
            live.toast("Trading re-armed", "ok");
            await live.refresh();
          }}
          onClose={() => setRearm(false)} />
      )}
      <div className="toasts" aria-live="polite">
        {live.toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
      </div>
    </div>
  );
}
