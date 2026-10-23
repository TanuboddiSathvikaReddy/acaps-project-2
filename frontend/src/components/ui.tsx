import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { prefersReducedMotion, useTween } from '../hooks'
import { Chevron, Info, Warn } from './Icons'
import { TERM_EXPLAIN } from '../lib/format'

/* ---------- Reveal ---------- */
export function Reveal({ children, d = 0, className = '', as: Tag = 'div', style }: { children: ReactNode; d?: number; className?: string; as?: 'div' | 'section' | 'li'; style?: CSSProperties }) {
  const ref = useRef<HTMLElement>(null)
  useEffect(() => {
    const el = ref.current; if (!el) return
    if (!('IntersectionObserver' in window) || prefersReducedMotion()) { el.classList.add('in'); return }
    const io = new IntersectionObserver(en => { if (en[0].isIntersecting) { el.classList.add('in'); io.disconnect() } }, { threshold: 0.08, rootMargin: '0px 0px -2% 0px' })
    io.observe(el); return () => io.disconnect()
  }, [])
  return <Tag ref={ref as never} className={`reveal ${className}`} style={{ '--d': d, ...style } as CSSProperties}>{children}</Tag>
}

/* ---------- Segmented control with a sliding thumb ---------- */
export interface SegOption<T extends string> { value: T; label: ReactNode; swatch?: string; disabled?: boolean }
export function Segmented<T extends string>({ value, options, onChange, label, role = 'tablist' }: { value: T; options: SegOption<T>[]; onChange: (v: T) => void; label: string; role?: 'tablist' | 'group' }) {
  const wrap = useRef<HTMLDivElement>(null)
  const [thumb, setThumb] = useState<{ x: number; w: number } | null>(null)
  useLayoutEffect(() => {
    const measure = () => {
      const el = wrap.current?.querySelector<HTMLElement>('[data-active="true"]')
      if (el) setThumb({ x: el.offsetLeft, w: el.offsetWidth })
    }
    measure()
    const ro = new ResizeObserver(measure); if (wrap.current) ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [value, options.length])
  const onKey = (e: React.KeyboardEvent) => {
    const i = options.findIndex(o => o.value === value)
    if (e.key === 'ArrowRight') { e.preventDefault(); const n = options[(i + 1) % options.length]; if (!n.disabled) onChange(n.value) }
    if (e.key === 'ArrowLeft') { e.preventDefault(); const n = options[(i - 1 + options.length) % options.length]; if (!n.disabled) onChange(n.value) }
  }
  return (
    <div className="seg" ref={wrap} role={role} aria-label={label} onKeyDown={onKey}>
      {thumb && <span className="thumb" style={{ width: thumb.w, transform: `translateX(${thumb.x - 4}px)`, left: 4 }} />}
      {options.map(o => (
        <button key={o.value} role={role === 'tablist' ? 'tab' : undefined} aria-selected={role === 'tablist' ? o.value === value : undefined} aria-pressed={role === 'group' ? o.value === value : undefined}
          data-active={o.value === value} tabIndex={o.value === value ? 0 : -1} disabled={o.disabled} onClick={() => onChange(o.value)}>
          {o.swatch && <span className="swatch" style={{ background: o.swatch }} />}{o.label}
        </button>
      ))}
    </div>
  )
}

/* ---------- Slider ---------- */
export function Slider({ value, min, max, step = 1, onChange, label, id }: { value: number; min: number; max: number; step?: number; onChange: (v: number) => void; label: string; id?: string }) {
  const p = ((value - min) / (max - min)) * 100
  return (
    <div className="slider" style={{ '--p': `${Math.min(100, Math.max(0, p))}%` } as CSSProperties}>
      <input id={id} type="range" min={min} max={max} step={step} value={Math.min(max, Math.max(min, value))} aria-label={label} onChange={e => onChange(Number(e.target.value))} />
    </div>
  )
}

/* ---------- Animated number ---------- */
export function AnimNum({ value, digits = 0, unit, className }: { value: number | null | undefined; digits?: number; unit?: string; className?: string }) {
  const v = useTween(value ?? 0)
  if (value == null) return <span className={className}>—</span>
  return <span className={`num ${className ?? ''}`}>{v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}{unit && <small>{unit}</small>}</span>
}

export function Stat({ label, value, unit, hint, xl, digits = 0, raw }: { label: string; value?: number | null; unit?: string; hint?: ReactNode; xl?: boolean; digits?: number; raw?: ReactNode }) {
  return (
    <div className={`stat ${xl ? 'xl' : ''}`}>
      <span className="label">{label}</span>
      <span className="value">{raw ?? <AnimNum value={value} digits={digits} unit={unit} />}</span>
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}

/* ---------- Term with explanation ---------- */
/** A short label with a technical explanation attached. Uses the existing global tooltip (same
 * glass styling as the canvas's hover tooltip, see TipHost below) rather than the browser's bare
 * native `title`, because `title` never appears on keyboard focus and is unreliable on touch —
 * this shows on hover (desktop), focus (keyboard) and tap (mobile/tablet), satisfying all three
 * input modes with one consistent, already-approved visual design. */
export function Term({ k, children }: { k: keyof typeof TERM_EXPLAIN | string; children: ReactNode }) {
  const text = TERM_EXPLAIN[k]
  const open = (el: HTMLElement) => { const r = el.getBoundingClientRect(); showTip({ body: text }, r.left + r.width / 2, r.bottom) }
  return (
    <span
      className="term" tabIndex={0}
      aria-label={`${typeof children === 'string' ? children : k}: ${text}`}
      onMouseEnter={e => open(e.currentTarget)} onMouseLeave={hideTip}
      onFocus={e => open(e.currentTarget)} onBlur={hideTip}
      onClick={e => open(e.currentTarget)}
    >{children}</span>
  )
}

/* ---------- Global tooltip ---------- */
export interface TipData { title?: ReactNode; body?: ReactNode; rows?: { k: ReactNode; v: ReactNode }[] }
type Listener = (t: { data: TipData; x: number; y: number } | null) => void
let listener: Listener | null = null
export const showTip = (data: TipData, x: number, y: number) => listener?.({ data, x, y })
export const hideTip = () => listener?.(null)
export function TipHost() {
  const [t, setT] = useState<{ data: TipData; x: number; y: number } | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { listener = setT; return () => { listener = null } }, [])
  const [pos, setPos] = useState({ x: 0, y: 0 })
  useLayoutEffect(() => {
    if (!t || !ref.current) return
    const w = ref.current.offsetWidth, h = ref.current.offsetHeight
    let x = t.x + 16, y = t.y + 16
    if (x + w > window.innerWidth - 8) x = t.x - w - 16
    if (y + h > window.innerHeight - 8) y = t.y - h - 16
    setPos({ x: Math.max(8, x), y: Math.max(8, y) })
  }, [t])
  return (
    // A mouse-hover-only visual aid (not wired to a specific control via aria-describedby, so it
    // has no benefit for assistive tech regardless of content) — hidden from the accessibility
    // tree so it is never exposed as an empty, unnamed "tooltip" role when nothing is showing.
    <div ref={ref} className={`tip ${t ? 'on' : ''}`} role="tooltip" aria-hidden="true" style={{ left: 0, top: 0, transform: `translate3d(${pos.x}px, ${pos.y}px, 0)` }}>
      {t?.data.title && <div className="t-title">{t.data.title}</div>}
      {t?.data.body && <div style={{ color: 'var(--ink-1)', lineHeight: 1.45 }}>{t.data.body}</div>}
      {t?.data.rows?.map((r, i) => <div className="t-row" key={i}><span className="k">{r.k}</span><b>{r.v}</b></div>)}
    </div>
  )
}

/* ---------- Expandable ---------- */
export function Expand({ title, children, defaultOpen }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return <details className="expand" open={defaultOpen}><summary>{title}<Chevron /></summary><div className="x-body">{children}</div></details>
}

/* ---------- Banners ---------- */
export function DemoBadge({ note }: { note?: string }) {
  return <span className="badge warn" title={note}><Warn /> Demo data</span>
}
export function Banner({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'bad'; children: ReactNode }) {
  return <div className={`banner ${tone === 'info' ? '' : tone}`} role={tone === 'bad' ? 'alert' : 'status'}>{tone === 'info' ? <Info /> : <Warn />}<div>{children}</div></div>
}
