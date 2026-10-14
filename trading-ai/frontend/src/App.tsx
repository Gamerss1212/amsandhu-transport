import { useEffect, useState } from "react";
import { api } from "./api";
import { Modal, PhraseConfirm } from "./components/ui";
import { useLive } from "./store";
import CommandCenter from "./pages/CommandCenter";
import BrokerMoney from "./pages/BrokerMoney";
import LiveIntelligence from "./pages/LiveIntelligence";
import Assistant from "./components/Assistant";
import Hud from "./hud/Hud";
import "./hud/hud.css";

// Two pages (owner's instruction of 2026-10-14): the JARVIS trading panel and Brokers & Accounts. The agent grid and
// the detailed control room open as full-screen overlays inside them, not as pages.
const PAGES = [
  ["/", "Trading"],
  ["/broker", "Brokers"],
] as const;
type Overlay = null | "agents" | "control";

export function go(path: string) {
  if (location.pathname !== path) {
    history.pushState(null, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
}

function HudClock() {
  const [t, setT] = useState(() => new Date());
  useEffect(() => { const i = setInterval(() => setT(new Date()), 1000); return () => clearInterval(i); }, []);
  return (
    <>
      <span>Date <b>{t.toLocaleDateString(undefined, { year: "numeric", month: "2-digit", day: "2-digit" })}</b></span>
      <span>Time <b className="mono">{t.toLocaleTimeString(undefined, { hour12: false })}</b></span>
    </>
  );
}

const ICONS: Record<string, JSX.Element> = {
  trading: <svg viewBox="0 0 24 24"><path d="M3 17l5-6 4 3 8-9" /><path d="M14 5h6v6" /></svg>,
  broker: <svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M3 10h18M7 15h4" /></svg>,
  agents: <svg viewBox="0 0 24 24"><circle cx="12" cy="6" r="3" /><circle cx="5" cy="18" r="2.5" /><circle cx="12" cy="18" r="2.5" /><circle cx="19" cy="18" r="2.5" /><path d="M12 9v6.5M10 8l-4 7.6M14 8l4 7.6" /></svg>,
  control: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>,
};

export default function App() {
  const [path, setPath] = useState(location.pathname);
  const live = useLive();
  const [estop, setEstop] = useState(false);
  const [rearm, setRearm] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>(() => (location.pathname === "/intelligence" ? "agents" : null));

  useEffect(() => {
    const on = () => setPath(location.pathname);
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  useEffect(() => {                                  // the old page-2 address opens the agents overlay on page 1
    if (location.pathname === "/intelligence") { history.replaceState(null, "", "/"); setPath("/"); }
  }, []);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOverlay(null); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  const o = live.overview;
  const page = PAGES.find(([p]) => p === path)?.[0] ?? "/";
  const kill = o?.risk?.kill_switch;
  const locked = o?.risk?.trading_locked;
  const online = live.ws === "live";

  return (
    <div className="hud">
      <header className="hud-head">
        <div className="l">
          <span>JARVIS OS <b>v{o?.version ?? "—"}</b></span>
          <span>Status <b className={online ? "up" : "down"}>{online ? "Online" : live.ws === "offline" ? "Offline" : "Connecting"}</b></span>
          {o && <span className={`hud-chip ${o.mode === "live" ? "bad" : "sim"}`}><i />{o.mode === "live" ? "LIVE · REAL MONEY" : `${o.mode.toUpperCase()} · SIMULATED`}</span>}
          {o && <span className="hud-chip">{o.state.state.replace(/_/g, " ")}</span>}
          {o?.offline && <span className="hud-chip warn">OFFLINE DATA</span>}
        </div>
        <div className="hud-title">
          <h1>JARVIS</h1>
          <small>Just a rather very intelligent system · AI trading</small>
        </div>
        <div className="r">
          <HudClock />
          <nav className="hud-tabs" aria-label="Pages">
            {PAGES.map(([p, label]) => (
              <a key={p} href={p} className={page === p ? "on" : ""} onClick={(e) => { e.preventDefault(); setOverlay(null); go(p); }}>{label}</a>
            ))}
          </nav>
          {kill || locked
            ? <button className="hud-btn warn" style={{ minWidth: 0 }} onClick={() => setRearm(true)}>Re-arm…</button>
            : <button className="hud-estop" onClick={() => setEstop(true)} title="Stops every agent, cancels working orders, blocks new orders">Emergency stop</button>}
        </div>
      </header>

      {!o && live.ws !== "offline" && <div className="page"><div className="empty">Connecting to the local server…</div></div>}
      {live.ws === "offline" && (
        <div className="page"><div className="callout bad">The local server is not answering. If you closed the Trading AI window, double-click START_TRADING_AI.exe again.</div></div>
      )}
      {o && (kill || locked || o.state.state === "RECONCILIATION_REQUIRED") && (
        <div className="page" style={{ paddingBottom: 0 }}>
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
            <div className="callout bad"><b>Reconciliation required.</b> Local records and the broker disagree. New entries are blocked. Open Brokers → Reconcile now to see the differences.</div>
          )}
        </div>
      )}
      {o && page === "/" && <Hud />}
      {o && page === "/broker" && <main className="page"><BrokerMoney /></main>}

      {o && (
        <nav className="hud-dock" aria-label="JARVIS">
          <button className={page === "/" && !overlay ? "on" : ""} onClick={() => { setOverlay(null); go("/"); }}>{ICONS.trading}Trading</button>
          <button className={page === "/broker" && !overlay ? "on" : ""} onClick={() => { setOverlay(null); go("/broker"); }}>{ICONS.broker}Brokers</button>
          <button className={overlay === "agents" ? "on" : ""} onClick={() => setOverlay(overlay === "agents" ? null : "agents")}>{ICONS.agents}Agents</button>
          <button className={overlay === "control" ? "on" : ""} onClick={() => setOverlay(overlay === "control" ? null : "control")}>{ICONS.control}Control room</button>
        </nav>
      )}
      {o && overlay && (
        <div className="hud-overlay" role="dialog" aria-modal="true" aria-label={overlay === "agents" ? "Agents" : "Control room"}>
          <header>
            <span>{overlay === "agents" ? "Supercomputer Brain · 100 agents" : "Control room · charts, decisions, risk, strategies"}</span>
            <button className="hud-btn" style={{ minWidth: 0 }} onClick={() => setOverlay(null)}>Close (Esc)</button>
          </header>
          <div className="body"><div className="page">{overlay === "agents" ? <LiveIntelligence /> : <CommandCenter />}</div></div>
        </div>
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
      {o && <Assistant />}
      <div className="toasts" aria-live="polite">
        {live.toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
      </div>
    </div>
  );
}
