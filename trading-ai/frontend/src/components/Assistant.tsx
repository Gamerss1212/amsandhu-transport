import { useEffect, useRef, useState } from "react";
import { api, fmt } from "../api";
import { useLive } from "../store";
import { go } from "../App";

// The persistent assistant: text chat on every page, optional speech (browser voices, British English preferred),
// optional listening (the browser's own recognizer, where available) and proactive announcements of verified events.
// Settings are per-viewer conveniences kept in localStorage; trading permissions never depend on them.

type Line = { who: "you" | "ai" | "event"; text: string; ts: number; severity?: string };
const SPEAK_MIN = { info: 0, warning: 1, error: 2, critical: 3 } as Record<string, number>;

function load<T>(k: string, d: T): T {
  try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; }
}
function save(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private window */ } }

export default function Assistant() {
  const live = useLive();
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<Line[]>([{ who: "ai", ts: Date.now(), text: "Good day. Ask me what the bots are doing, why you are or aren't trading, today's fees, or say \"pause new entries\"." }]);
  const [text, setText] = useState("");
  const [voiceOn, setVoiceOn] = useState<boolean>(() => load("ai.voice", false));
  const [proactive, setProactive] = useState<boolean>(() => load("ai.proactive", false));
  const [minSev, setMinSev] = useState<string>(() => load("ai.minsev", "warning"));
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const seen = useRef(new Set<string>());
  const recog = useRef<any>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
  const Recog: any = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

  useEffect(() => { save("ai.voice", voiceOn); save("ai.proactive", proactive); save("ai.minsev", minSev); }, [voiceOn, proactive, minSev]);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [lines, open]);

  const pickVoice = () => {
    const vs = synth?.getVoices() ?? [];
    return vs.find((v) => /en-GB/i.test(v.lang) && /(George|Ryan|Daniel|Arthur|Male)/i.test(v.name))
      ?? vs.find((v) => /en-GB/i.test(v.lang)) ?? vs.find((v) => /^en/i.test(v.lang));
  };
  const speak = (t: string, urgent = false) => {
    if (!voiceOn || !synth) return;
    if (urgent) synth.cancel();
    const u = new SpeechSynthesisUtterance(t);
    const v = pickVoice();
    if (v) u.voice = v;
    u.rate = 1.02; u.pitch = 0.95;
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    synth.speak(u);
  };

  // proactive announcements: structured backend events, spoken only while still current
  useEffect(() => {
    const last = live.events[live.events.length - 1];
    if (!last || last.topic !== "voice") return;
    const ev = last.data;
    if (seen.current.has(ev.id)) return;
    seen.current.add(ev.id);
    setLines((l) => [...l.slice(-80), { who: "event", text: ev.text, ts: ev.created, severity: ev.severity }]);
    if (proactive && Date.now() < ev.expires && (SPEAK_MIN[ev.severity] ?? 0) >= (SPEAK_MIN[minSev] ?? 1)) {
      speak(ev.text, ev.severity === "critical");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live.events]);

  const ask = async (q: string) => {
    if (!q.trim()) return;
    synth?.cancel();                                  // the owner is talking: stop speaking
    setLines((l) => [...l.slice(-80), { who: "you", text: q, ts: Date.now() }]);
    setText("");
    try {
      const r = await api.post("/api/assistant/ask", { text: q });
      setLines((l) => [...l.slice(-80), { who: "ai", text: r.answer, ts: r.ts }]);
      speak(r.answer);
      if (r.navigate) go(r.navigate);
      if (r.action) await live.refresh();
    } catch (e: any) {
      setLines((l) => [...l.slice(-80), { who: "ai", text: `I couldn't reach the local server: ${e.message}`, ts: Date.now() }]);
    }
  };

  const listen = () => {
    if (!Recog) return;
    if (listening) { recog.current?.stop(); return; }
    synth?.cancel();
    const r = new Recog();
    r.lang = "en-GB"; r.interimResults = false; r.maxAlternatives = 1;
    r.onresult = (e: any) => ask(e.results[0][0].transcript);
    r.onend = () => setListening(false);
    r.onerror = (e: any) => { setListening(false); setLines((l) => [...l, { who: "ai", ts: Date.now(), text: `Microphone unavailable (${e.error}). You can type instead.` }]); };
    recog.current = r;
    setListening(true);
    r.start();
  };

  const state = listening ? "listening" : speaking ? "speaking" : !voiceOn ? "muted" : "ready";
  return (
    <div className="assistant">
      {open && (
        <div className="assistant-panel card" role="dialog" aria-label="Assistant">
          <div className="hd">
            <h2>Assistant</h2><span className="sub">{state}</span><div className="grow" />
            <button className="btn sm ghost" onClick={() => setOpen(false)}>Close</button>
          </div>
          <div className="assistant-log">
            {lines.map((l, i) => (
              <div key={i} className={`al ${l.who} ${l.severity ?? ""}`}>
                <span className="tiny muted mono">{fmt.time(l.ts)}</span> {l.who === "event" ? "◆ " : l.who === "you" ? "You: " : ""}{l.text}
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <form className="row" style={{ padding: 10, borderTop: "1px solid var(--line)" }} onSubmit={(e) => { e.preventDefault(); ask(text); }}>
            <input className="grow" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask, or type a command…" aria-label="Ask the assistant" />
            {Recog && <button type="button" className={`btn sm ${listening ? "danger" : ""}`} onClick={listen} title="Speak a question">{listening ? "Stop" : "Mic"}</button>}
            <button className="btn sm primary" type="submit">Ask</button>
          </form>
          <div className="row wrap tiny" style={{ padding: "0 10px 10px" }}>
            <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={voiceOn} onChange={(e) => { setVoiceOn(e.target.checked); if (!e.target.checked) synth?.cancel(); }} />voice</label>
            <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={proactive} onChange={(e) => setProactive(e.target.checked)} />speak events</label>
            <select value={minSev} onChange={(e) => setMinSev(e.target.value)} aria-label="Announce from severity" style={{ padding: "2px 4px" }}>
              <option value="info">all events</option><option value="warning">warnings and up</option><option value="critical">critical only</option>
            </select>
            {!synth && <span className="muted">this browser has no speech output</span>}
            <span className="muted">No cloud AI: answers come from verified system state.</span>
          </div>
        </div>
      )}
      <button className={`assistant-btn ${state}`} onClick={() => setOpen((v) => !v)} aria-expanded={open} title="Assistant">
        <span className="dot" /> Assistant
      </button>
    </div>
  );
}
