import { useEffect, useRef } from "react";

/** The rotating dotted dome in the middle of the desk (canvas). Animation only: the tags it carries are real agent and
 *  market names passed in by the page. Stops drawing while the tab is hidden; still image with reduced motion. */
export function Dome({ tags, tint }: { tags: string[]; tint: string }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const tagsRef = useRef(tags);
  tagsRef.current = tags;

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const N = 620;
    const pts: [number, number, number][] = [];
    for (let i = 0; i < N; i++) {                       // Fibonacci points on the upper hemisphere
      const y = i / (N - 1);
      const r = Math.sqrt(1 - y * y);
      const a = i * 2.399963229728653;
      pts.push([Math.cos(a) * r, y, Math.sin(a) * r]);
    }
    const anchors = [0.55, 1.7, 2.6, 3.9, 4.8, 5.7].map((a, i) => [Math.cos(a) * 0.72, 0.42 + (i % 3) * 0.13, Math.sin(a) * 0.72]);
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let t0 = performance.now();

    const draw = (now: number) => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = cv.clientWidth, h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const R = Math.min(w * 0.36, h * 0.62);
      const cx = w / 2, cy = h * 0.68;
      const rot = still ? 0.6 : (now - t0) / 9000;
      const tilt = 0.32;
      const proj = (x: number, y: number, z: number) => {
        const xr = x * Math.cos(rot) - z * Math.sin(rot);
        const zr = x * Math.sin(rot) + z * Math.cos(rot);
        const yt = y * Math.cos(tilt) - zr * Math.sin(tilt);
        const zt = y * Math.sin(tilt) + zr * Math.cos(tilt);
        const s = 2.6 / (2.6 + zt);
        return [cx + xr * R * s, cy - yt * R * s, zt] as const;
      };
      // glow under the dome
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.1);
      g.addColorStop(0, `${tint}55`);
      g.addColorStop(1, "transparent");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
      // rays
      ctx.strokeStyle = `${tint}22`;
      ctx.lineWidth = 1;
      for (let k = 0; k < 14; k++) {
        const a = (k / 14) * Math.PI * 2 + rot * 0.3;
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(a) * R * 1.6, cy + Math.sin(a) * R * 0.5); ctx.stroke();
      }
      // base ring
      ctx.strokeStyle = tint;
      ctx.lineWidth = 1.6;
      ctx.shadowColor = tint; ctx.shadowBlur = 12;
      ctx.beginPath();
      for (let k = 0; k <= 64; k++) { const [x, y] = proj(Math.cos((k / 64) * Math.PI * 2), 0, Math.sin((k / 64) * Math.PI * 2)); if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y); }
      ctx.stroke();
      ctx.shadowBlur = 0;
      // dots
      for (const [x, y, z] of pts) {
        const [px, py, d] = proj(x, y, z);
        const a = 0.25 + 0.75 * (1 - (d + 1) / 2);
        ctx.fillStyle = `rgba(255,255,255,${(a * 0.85).toFixed(3)})`;
        ctx.fillRect(px, py, 1.6, 1.6);
      }
      // tags: real agent / market names
      ctx.font = "10px Consolas, ui-monospace, monospace";
      tagsRef.current.slice(0, anchors.length).forEach((tag, i) => {
        const [x, y, z] = anchors[i];
        const [px, py, d] = proj(x, y, z);
        if (d > 0.45) return;                            // behind the dome
        const tw = ctx.measureText(tag).width + 10;
        ctx.strokeStyle = tint; ctx.lineWidth = 1;
        ctx.fillStyle = "rgba(11,11,15,0.75)";
        ctx.fillRect(px - tw / 2, py - 18, tw, 15); ctx.strokeRect(px - tw / 2, py - 18, tw, 15);
        ctx.fillStyle = "#f3d7da"; ctx.fillText(tag, px - tw / 2 + 5, py - 7);
        ctx.fillStyle = tint; ctx.beginPath(); ctx.arc(px, py, 2.4, 0, Math.PI * 2); ctx.fill();
      });
      if (!still && !document.hidden) raf = requestAnimationFrame(draw);
    };
    const vis = () => { if (!document.hidden && !still) { cancelAnimationFrame(raf); t0 = performance.now() - 1; raf = requestAnimationFrame(draw); } };
    raf = requestAnimationFrame(draw);
    document.addEventListener("visibilitychange", vis);
    return () => { cancelAnimationFrame(raf); document.removeEventListener("visibilitychange", vis); };
  }, [tint]);

  return <canvas ref={ref} aria-label="Agent matrix (animation)" />;
}
