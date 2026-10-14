import type { ReactNode } from "react";

/** The arc reactor in the centre of the HUD. Pure decoration: the numbers are the children laid over it. */
export function Reactor({ children, level }: { children: ReactNode; level: "ok" | "wait" | "bad" }) {
  const tint = "#39c6ff";                                  // the reactor stays blue; only the status ring changes colour
  const ring = level === "bad" ? "#ff6b7d" : level === "wait" ? "#ffc861" : "#3ef0b4";
  const segs = Array.from({ length: 12 }, (_, i) => i * 30);
  const ticks = Array.from({ length: 72 }, (_, i) => i * 5);
  return (
    <div className="reactor" aria-hidden={false}>
      <svg viewBox="-220 -220 440 440" role="img" aria-label="Arc reactor (animation only)">
        <defs>
          <radialGradient id="core" r="0.5">
            <stop offset="0" stopColor="#031a33" stopOpacity="0.95" />
            <stop offset="0.62" stopColor="#06305a" stopOpacity="0.9" />
            <stop offset="0.82" stopColor="#7fe0ff" stopOpacity="0.85" />
            <stop offset="0.9" stopColor="#ffffff" stopOpacity="0.9" />
            <stop offset="1" stopColor={tint} stopOpacity="0" />
          </radialGradient>
          <radialGradient id="halo" r="0.5">
            <stop offset="0.55" stopColor={tint} stopOpacity="0" />
            <stop offset="0.8" stopColor={tint} stopOpacity="0.16" />
            <stop offset="1" stopColor={tint} stopOpacity="0" />
          </radialGradient>
          <linearGradient id="seg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#e8fbff" />
            <stop offset="1" stopColor={tint} />
          </linearGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <circle r="215" fill="url(#halo)" />
        {/* outer tick ring */}
        <g className="r-spin" stroke={tint} strokeOpacity="0.7">
          {ticks.map((a) => (
            <line key={a} x1="0" y1={a % 30 === 0 ? -206 : -201} x2="0" y2="-196" strokeWidth={a % 30 === 0 ? 2.2 : 1}
              transform={`rotate(${a})`} />
          ))}
          <circle r="208" fill="none" strokeWidth="1" strokeOpacity="0.35" />
        </g>
        {/* cardinal nodes */}
        <g className="r-spin-mid">
          {[0, 90, 180, 270].map((a) => (
            <g key={a} transform={`rotate(${a}) translate(0 -182)`}>
              <circle r="7" fill="#02101f" stroke={tint} strokeWidth="1.5" filter="url(#glow)" />
              <circle r="2.5" fill="#e8fbff" />
            </g>
          ))}
          <circle r="182" fill="none" stroke={tint} strokeOpacity="0.25" strokeWidth="1" strokeDasharray="2 10" />
        </g>
        {/* broken arcs */}
        <g className="r-spin-fast" fill="none" stroke={tint} filter="url(#glow)">
          <circle r="166" strokeWidth="3" strokeDasharray="140 210 60 135 30 168" strokeOpacity="0.9" />
        </g>
        <g className="r-spin-rev" fill="none" stroke="#bff1ff">
          <circle r="152" strokeWidth="1.2" strokeDasharray="4 6" strokeOpacity="0.55" />
          <circle r="142" strokeWidth="6" strokeDasharray="60 40" strokeOpacity="0.18" stroke={tint} />
        </g>
        {/* flowing energy ring */}
        <circle r="128" fill="none" stroke={tint} strokeWidth="2" className="r-flow" strokeOpacity="0.8" />
        {/* the twelve reactor segments */}
        <g filter="url(#glow)">
          {segs.map((a, i) => (
            <path key={a} className="r-seg" style={{ animationDelay: `${(i % 6) * 0.22}s` }}
              d="M -24 -118 L 24 -118 L 18 -86 L -18 -86 Z" fill="url(#seg)" fillOpacity="0.7"
              stroke="#e8fbff" strokeOpacity="0.6" strokeWidth="0.8" transform={`rotate(${a})`} />
          ))}
        </g>
        <circle r="82" fill="#021426" fillOpacity="0.9" stroke={tint} strokeWidth="2" filter="url(#glow)" />
        <circle r="78" fill="url(#core)" className="r-core" />
        <circle r="64" fill="none" stroke="#bff1ff" strokeOpacity="0.3" strokeWidth="1" strokeDasharray="3 5" className="r-spin-fast" />
        {/* status ring: green when trading is permitted, amber while waiting, red when stopped */}
        <circle r="196" fill="none" stroke={ring} strokeOpacity="0.55" strokeWidth="1.5" strokeDasharray="2 4" />
      </svg>
      <div className="reactor-read">{children}</div>
    </div>
  );
}
