import { useEffect } from 'react'

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
  return (
    <div role="dialog" aria-modal="true" aria-label="Allow this action?" style={{
      position: 'fixed', left: '50%', bottom: '9vh', transform: 'translateX(-50%)', zIndex: 50, width: 'min(560px, 92vw)',
      background: 'rgba(4, 18, 34, 0.92)', border: `1px solid ${warn ? '#ff6b7d' : '#39c6ff'}`, borderRadius: 8,
      boxShadow: `0 0 28px ${warn ? 'rgba(255,90,110,.35)' : 'rgba(57,198,255,.35)'}`, padding: '16px 18px', color: '#dff7ff',
      fontFamily: 'Bahnschrift, "Segoe UI", system-ui, sans-serif',
    }}>
      <div style={{ fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: warn ? '#ffb3bd' : '#7fcff5' }}>May I?</div>
      <div style={{ margin: '8px 0 14px', fontFamily: 'Consolas, ui-monospace, monospace', fontSize: 13, lineHeight: 1.5, wordBreak: 'break-word' }}>{what}</div>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button onClick={() => onAnswer(false)} style={{ padding: '8px 16px', background: 'transparent', color: '#cfefff', border: '1px solid #3a5a78', borderRadius: 4, cursor: 'pointer' }}>Deny (N)</button>
        <button autoFocus onClick={() => onAnswer(true)} style={{ padding: '8px 16px', background: '#0f5d8f', color: '#fff', border: '1px solid #39c6ff', borderRadius: 4, cursor: 'pointer' }}>Allow (Y)</button>
      </div>
    </div>
  )
}
