import { accentFor, useStore } from '../store'

/** The one button for talking to JARVIS. Added for the Trading AI project.
 *  Press once: he answers and keeps listening after every reply, like a phone call.
 *  While he talks or thinks, a press interrupts him; while he listens, a press ends the conversation.
 *  Space does the same. */
export function TalkButton({ talking, onPress }: { talking: boolean; onPress: () => void }) {
  const phase = useStore((s) => s.phase)
  const accent = useStore((s) => accentFor(s.phase, s.ui))
  if (phase === 'offline' || phase === 'boot') return null

  const busy = phase === 'thinking' || phase === 'tooling' || phase === 'speaking'
  const label = !talking
    ? 'Talk'
    : busy
      ? (phase === 'speaking' ? 'Speaking · press to interrupt' : 'Thinking · press to interrupt')
      : 'Listening · press to end'

  return (
    <div className="talk" style={{ ['--talk' as string]: accent }}>
      <button
        type="button"
        className={`talk-btn${talking ? ' on' : ''}${talking && !busy ? ' listening' : ''}`}
        onClick={onPress}
        aria-pressed={talking}
        aria-label={talking ? label : 'Talk to JARVIS'}
      >
        <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
          {talking && !busy ? (
            <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" />
          ) : (
            <path
              fill="currentColor"
              d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"
            />
          )}
        </svg>
      </button>
      <div className="talk-label">{label}</div>
    </div>
  )
}
