import { useEffect, useState } from "react";
import { api } from "./api";
import { Modal, PhraseConfirm } from "./components/ui";
import { useLive } from "./store";
import CommandCenter from "./pages/CommandCenter";
import BrokerMoney from "./pages/BrokerMoney";
import LiveIntelligence from "./pages/LiveIntelligence";
import Assistant from "./components/Assistant";
import Desk from "./desk/Desk";
import "./desk/desk.css";

// Two pages (owner's instruction of 2026-10-14): the JARVIS desk and Brokers. Agents and the control room open as
// full-screen overlays inside them, not as pages.
type Overlay = null | "agents" | "control";

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
  const [busy, setBusy] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>(() => (location.pathname === "/intelligence" ? "agents" : null));

  useEffect(() => {
    const on = () => setPath(location.pathname);
    window.addEventListener("popstate", on);
    if (location.pathname === "/intelligence") { history.replaceState(null, "", "/"); setPath("/"); }
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOverlay(null); };
    window.addEventListener("keydown", esc);
    return () => { window.removeEventListener("popstate", on); window.removeEventListener("keydown", esc); };
  }, []);

  const o = live.overview;
  const page = path === "/broker" ? "/broker" : "/";
  const kill = o?.risk?.kill_switch;
  const locked = o?.risk?.trading_locked;
  const running = !!o?.autopilot?.enabled;
  const paused = !!o?.risk?.entries_paused;
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try { await fn(); live.toast(ok, "ok"); } catch (e: any) { live.toast(e.message, "error"); }
    setBusy(false);
    await live.refresh();
  };
  const tab = (label: string, on: boolean, click: () => void) => <button className={on ? "on" : ""} onClick={click}>{label}</button>;

  return (
    <div className="desk">
      <header className="dk-head">
        <div className="dk-brand">
          <div className="dk-logo" aria-hidden><svg viewBox="0 0 24 24"><path d="M13 2L4 14h6l-1 8 9-12h-6z" /></svg></div>
          <div>
            <h1>JARVIS DESK</h1>
            <div className="sub">BRAIN · RISK · EXECUTION / AUTONOMOUS SESSION</div>
          </div>
        </div>
        <div className="dk-right">
          <nav className="dk-tabs" aria-label="Pages">
            {tab("DESK", page === "/" && !overlay, () => { setOverlay(null); go("/"); })}
            {tab("BROKERS", page === "/broker" && !overlay, () => { setOverlay(null); go("/broker"); })}
            {tab("AGENTS", overlay === "agents", () => setOverlay(overlay === "agents" ? null : "agents"))}
            {tab("CONTROL ROOM", overlay === "control", () => setOverlay(overlay === "control" ? null : "control"))}
          </nav>
          {o && <>
            <button className={`dk-btn ${running ? "on" : ""}`} disabled={busy || !!kill} onClick={() => act(() => api.post(running ? "/api/bot/stop" : "/api/bot/start"), running ? "System stopped" : "System started")}>{running ? "Stop" : "Start"}</button>
            <button className={`dk-btn ${paused ? "warn" : ""}`} disabled={busy} onClick={() => act(() => api.post("/api/controls/pause-entries", { paused: !paused, reason: "owner" }), paused ? "New entries allowed" : "New entries paused")}>{paused ? "Resume" : "Pause"}</button>
            {kill || locked
              ? <button className="dk-btn warn" onClick={() => setRearm(true)}>Re-arm…</button>
              : <button className="dk-estop" onClick={() => setEstop(true)} title="Stops every agent, cancels working orders, blocks new orders">E-STOP</button>}
          </>}
          <div className="dk-sess">
            {o ? (o.mode === "live" ? "LIVE · REAL MONEY" : `${o.mode.toUpperCase()} · SIMULATED`) : "—"}
            <small><i className={live.ws === "live" ? "live" : ""} />{live.ws === "live" ? "LIVE SESSION" : live.ws === "offline" ? "SERVER OFFLINE" : "CONNECTING"}{o?.offline ? " · OFFLINE DATA" : ""}</small>
          </div>
        </div>
      </header>

      {!o && live.ws !== "offline" && <div className="page"><div className="empty">Connecting to the local server…</div></div>}
      {live.ws === "offline" && (
        <div className="page"><div className="callout bad">The local server is not answering. If you closed the Trading AI window, double-click START_TRADING_AI.exe again.</div></div>
      )}
      {o && (kill || locked || o.state.state === "RECONCILIATION_REQUIRED") && (
        <div className="page" style={{ paddingBottom: 0 }}>
          {kill && <div className="callout bad"><b>STOP ALL TRADING is engaged</b> ({kill.reason}, by {kill.by}). No new orders can be sent. Re-arm when you have reviewed what happened.</div>}
          {!kill && locked && <div className="callout bad"><b>Trading is locked</b>: {locked.reason}. Only orders that reduce positions are allowed until you re-arm.</div>}
          {o.state.state === "RECONCILIATION_REQUIRED" && <div className="callout bad"><b>Reconciliation required.</b> New entries are blocked. Open Brokers → Reconcile now.</div>}
        </div>
      )}
      {o && page === "/" && <Desk />}
      {o && page === "/broker" && <main className="page"><BrokerMoney /></main>}

      {o && overlay && (
        <div className="dk-overlay" role="dialog" aria-modal="true" aria-label={overlay === "agents" ? "Agents" : "Control room"}>
          <header>
            <span>{overlay === "agents" ? "Supercomputer Brain · 100 agents" : "Control room · charts, decisions, risk, strategies"}</span>
            <button className="dk-btn" onClick={() => setOverlay(null)}>Close (Esc)</button>
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
