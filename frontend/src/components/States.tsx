import type { ReactNode } from 'react'
import { Arrow, Warn } from './Icons'

export function LoadingState({ title, note }: { title: string; note?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <svg className="glyph" viewBox="0 0 84 84" aria-hidden>
        <circle className="pulse-ring" cx="42" cy="42" r="30" fill="none" stroke="var(--accent)" strokeWidth="1.5" />
        <circle className="pulse-ring" style={{ animationDelay: '1.2s' }} cx="42" cy="42" r="30" fill="none" stroke="var(--accent)" strokeWidth="1.5" />
        <circle cx="42" cy="42" r="5" fill="var(--accent)" />
      </svg>
      <h2>{title}</h2>{note && <p>{note}</p>}
    </div>
  )
}
export function EmptyState({ title, note, action, glyph }: { title: string; note?: string; action?: ReactNode; glyph?: ReactNode }) {
  return (
    <div className="state">
      {glyph ?? (
        <svg className="glyph" viewBox="0 0 84 84" aria-hidden fill="none" stroke="var(--ink-3)" strokeWidth="1.5">
          <rect x="10" y="32" width="64" height="20" rx="10" /><circle cx="24" cy="42" r="4" fill="var(--c-normal)" stroke="none" opacity=".7" /><circle cx="38" cy="42" r="4" stroke="var(--ink-3)" strokeDasharray="2 3" />
          <circle cx="52" cy="42" r="4" stroke="var(--ink-3)" strokeDasharray="2 3" /><path d="M42 60v10M36 66l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      <h2>{title}</h2>{note && <p>{note}</p>}{action}
    </div>
  )
}
export function ErrorState({ title, note, fields, action }: { title: string; note?: string; fields?: { path: string; msg: string }[]; action?: ReactNode }) {
  return (
    <div className="state" role="alert">
      <svg className="glyph" viewBox="0 0 84 84" aria-hidden fill="none" stroke="var(--bad)" strokeWidth="1.6"><circle cx="42" cy="42" r="28" opacity=".35" /><path d="M42 26v20M42 55h.01" strokeLinecap="round" /></svg>
      <h2>{title}</h2>{note && <p>{note}</p>}
      {fields && fields.length > 0 && (
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 6, textAlign: 'left', maxWidth: 480 }}>
          {fields.slice(0, 6).map((f, i) => <li key={i} className="banner bad"><Warn /><div>{f.path && <code>{f.path}</code>} {f.msg}</div></li>)}
        </ul>
      )}
      {action}
    </div>
  )
}
export const ArrowIcon = Arrow
