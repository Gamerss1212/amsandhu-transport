import { useEffect } from 'react'
import { accentFor, useStore } from '../store'

/** "May I?" — one action JARVIS wants to take, waiting for the user. Added for the Trading AI project.
 *  Allow / Deny buttons, or the Y and N keys. No answer within 90 seconds means no (the bridge decides that). */
export function Confirm({ what, onAnswer }: { what: string; onAnswer: (allow: boolean) => void }) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'y' || e.key === 'Y') onAnswer(true)
      if (e.key === 'n' || e.key === 'N' || e.key === 'Escape') onAnswer(false)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onAnswer])
  const warn = what.includes('WARNING')
  const accent = useStore((s) => accentFor(s.phase, s.ui))   // the same colour the HUD is showing right now
  const tint = warn ? '#ff6b7d' : accent
  return (
    <div role="dialog" aria-modal="true" aria-label="Allow this action?" style={{
      position: 'fixed', left: '50%', bottom: '9vh', transform: 'translateX(-50%)', zIndex: 50, width: 'min(560px, 92vw)',
      background: 'rgba(1, 6, 12, 0.97)', backdropFilter: 'blur(6px)', border: `1px solid ${tint}`, borderRadius: 8,
      boxShadow: `0 0 28px color-mix(in srgb, ${tint} 35%, transparent)`, padding: '16px 18px', color: '#dff7ff',
      fontFamily: 'Bahnschrift, "Segoe UI", system-ui, sans-serif',
    }}>
      <div style={{ fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: tint }}>May I?</div>
      <div style={{ margin: '8px 0 14px', fontFamily: 'Consolas, ui-monospace, monospace', fontSize: 13, lineHeight: 1.5, wordBreak: 'break-word' }}>{what}</div>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button onClick={() => onAnswer(false)} style={{ padding: '8px 16px', background: 'transparent', color: '#cfefff', border: `1px solid color-mix(in srgb, ${tint} 40%, transparent)`, borderRadius: 4, cursor: 'pointer' }}>Deny (N)</button>
        <button autoFocus onClick={() => onAnswer(true)} style={{ padding: '8px 16px', background: `color-mix(in srgb, ${tint} 30%, #01060c)`, color: '#fff', border: `1px solid ${tint}`, borderRadius: 4, cursor: 'pointer' }}>Allow (Y)</button>
      </div>
    </div>
  )
}
