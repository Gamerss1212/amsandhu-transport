import { useState, type ReactNode } from "react";

export function Card({ title, sub, right, children, flush, className }: {
  title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; flush?: boolean; className?: string;
}) {
  return (
    <section className={`card ${className ?? ""}`}>
      {(title || right) && (
        <div className="hd">
          <h2>{title}</h2>
          {sub && <span className="sub">{sub}</span>}
          <div className="grow" />
          {right}
        </div>
      )}
      <div className={`bd ${flush ? "flush" : ""}`}>{children}</div>
    </section>
  );
}

export function Stat({ k, v, s, cls }: { k: ReactNode; v: ReactNode; s?: ReactNode; cls?: string }) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className={`v ${cls ?? ""}`}>{v}</div>
      {s !== undefined && <div className="s">{s}</div>}
    </div>
  );
}

export function Badge({ kind, children, dot }: { kind?: "good" | "warn" | "bad" | "info" | "sim" | ""; children: ReactNode; dot?: boolean }) {
  return <span className={`badge ${kind ?? ""}`}>{dot && <span className="dot" />}{children}</span>;
}

export function ModeBadge({ mode }: { mode: string }) {
  if (mode === "live") return <Badge kind="bad" dot>LIVE · REAL MONEY</Badge>;
  if (mode === "shadow") return <Badge kind="info" dot>SHADOW · NOT SENT</Badge>;
  return <Badge kind="sim" dot>PAPER · SIMULATED</Badge>;
}

const STATE_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  READY: "", PAPER_RUNNING: "good", SHADOW_RUNNING: "info", LIVE_RUNNING: "bad", LIVE_ARMED: "warn", LIVE_LOCKED: "",
  PAUSED: "warn", RECONCILIATION_REQUIRED: "bad", ERROR: "bad", BOOTING: "info", RESEARCHING: "info", SHUTTING_DOWN: "warn",
};

export function StateBadge({ state }: { state: string }) {
  return <Badge kind={STATE_KIND[state] ?? ""} dot>{state.replace(/_/g, " ")}</Badge>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Meter({ value, label }: { value: number | null | undefined; label: ReactNode }) {
  // value = share of a limit used (1.0 = at the limit). Unknown stays unknown.
  const v = value === null || value === undefined || !Number.isFinite(value) ? null : value;
  const kind = v === null ? "" : v >= 1 ? "bad" : v >= 0.7 ? "warn" : "good";
  return (
    <div className="col" style={{ gap: 4 }}>
      <div className="spread small"><span className="dim">{label}</span><span className="mono">{v === null ? "—" : `${Math.round(v * 100)}% of limit`}</span></div>
      <div className={`bar ${kind}`}><i style={{ width: `${v === null ? 0 : Math.min(100, v * 100)}%` }} /></div>
    </div>
  );
}

export function Diverge({ value, max = 1 }: { value: number; max?: number }) {
  const v = Math.max(-1, Math.min(1, value / max));
  const w = Math.abs(v) * 50;
  return (
    <div className="diverge" title={value.toFixed(3)}>
      <i style={{ left: v >= 0 ? "50%" : `${50 - w}%`, width: `${w}%`, background: v >= 0 ? "var(--good)" : "var(--bad)" }} />
    </div>
  );
}

export function Modal({ title, children, onClose }: { title: ReactNode; children: ReactNode; onClose: () => void }) {
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true">
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  );
}

export function Drawer({ title, right, children, onClose }: { title: ReactNode; right?: ReactNode; children: ReactNode; onClose: () => void }) {
  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="hd">
          <h2>{title}</h2>
          <div className="grow" />
          {right}
          <button className="btn ghost sm" onClick={onClose}>Close</button>
        </div>
        <div className="bd">{children}</div>
      </aside>
    </>
  );
}

// Asks the owner to type an exact phrase before a consequential action. The phrase is checked again by the server.
export function PhraseConfirm({ title, phrase, body, action, danger, onConfirm, onClose }: {
  title: string; phrase: string; body: ReactNode; action: string; danger?: boolean;
  onConfirm: (typed: string) => Promise<unknown>; onClose: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title={title} onClose={onClose}>
      <div className="dim">{body}</div>
      <label className="field">Type <b className="mono" style={{ color: "var(--text)" }}>{phrase}</b> to continue
        <input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} spellCheck={false} />
      </label>
      {err && <div className="callout bad">{err}</div>}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className={`btn ${danger ? "danger" : "primary"}`} disabled={typed.trim() !== phrase || busy}
          onClick={async () => {
            setBusy(true);
            setErr(null);
            try {
              await onConfirm(typed.trim());
              onClose();
            } catch (e: any) {
              setErr(String(e.message ?? e));
            } finally {
              setBusy(false);
            }
          }}>{action}</button>
      </div>
    </Modal>
  );
}

export function Tabs<T extends string>({ tabs, on, set }: { tabs: [T, string][]; on: T; set: (t: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={on === k} className={on === k ? "on" : ""} onClick={() => set(k)}>{label}</button>
      ))}
    </div>
  );
}

export function Check({ ok, name, detail }: { ok: boolean | null; name: ReactNode; detail?: ReactNode }) {
  return (
    <div className="check">
      <span className="ic" style={{ color: ok === null ? "var(--muted)" : ok ? "var(--good)" : "var(--bad)" }}>
        {ok === null ? "•" : ok ? "✓" : "✕"}
      </span>
      <div className="grow">
        <div>{name}</div>
        {detail && <div className="note">{detail}</div>}
      </div>
    </div>
  );
}
