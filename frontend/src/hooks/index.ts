import { useEffect, useRef, useState, useSyncExternalStore } from 'react'

const mq = typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    cb => { mq?.addEventListener('change', cb); return () => mq?.removeEventListener('change', cb) },
    () => !!mq?.matches, () => false)
}
export const prefersReducedMotion = () => !!mq?.matches

/** Adds .in to every .reveal inside the container as it scrolls into view. */
export function useRevealRoot(dep?: unknown) {
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>('.reveal:not(.in)'))
    if (!('IntersectionObserver' in window) || prefersReducedMotion()) { els.forEach(e => e.classList.add('in')); return }
    const io = new IntersectionObserver(entries => entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target) } }), { threshold: 0.12, rootMargin: '0px 0px -2% 0px' })
    els.forEach(e => io.observe(e))
    return () => io.disconnect()
  }, [dep])
}

/** Publishes scrollY to --sy for CSS parallax (one rAF-throttled listener). */
export function useScrollVar() {
  useEffect(() => {
    let raf = 0
    const on = () => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; document.documentElement.style.setProperty('--sy', String(window.scrollY)) }) }
    on(); window.addEventListener('scroll', on, { passive: true })
    return () => { window.removeEventListener('scroll', on); cancelAnimationFrame(raf) }
  }, [])
}

/** Smooth number tween. */
export function useTween(target: number, ms = 900): number {
  const [v, setV] = useState(target)
  const from = useRef(target)
  useEffect(() => {
    if (prefersReducedMotion()) { setV(target); from.current = target; return }
    const a = from.current, t0 = performance.now(); let raf = 0
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 4)
      const val = a + (target - a) * e; from.current = val; setV(val)
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}

/** Live-value change indicator (design brief §6): flags that a value just changed, for a brief
 * highlight — it never interpolates through intermediate numbers (that would fabricate readings
 * the backend never reported), it only marks the instant a REAL new value arrived. Returns false
 * whenever `enabled` is false, so it does nothing while, e.g., playback is paused. */
export function useChangeFlash<T>(value: T, enabled = true, ms = 500): boolean {
  const [flash, setFlash] = useState(false)
  const prev = useRef(value)
  useEffect(() => {
    if (!enabled || prev.current === value) { prev.current = value; return }
    prev.current = value
    if (prefersReducedMotion()) return // state still updates; just no highlight motion
    setFlash(true)
    const id = setTimeout(() => setFlash(false), ms)
    return () => clearTimeout(id)
  }, [value, enabled, ms])
  return flash
}

export function useHashRoute(): [string, (r: string) => void] {
  const get = () => (location.hash.replace(/^#\/?/, '') || 'home').split('?')[0]
  const [r, setR] = useState(get)
  useEffect(() => { const h = () => setR(get()); window.addEventListener('hashchange', h); return () => window.removeEventListener('hashchange', h) }, [])
  return [r, (n: string) => { location.hash = n === 'home' ? '/' : `/${n}` }]
}

/** Throttled subscription for React UI driven by a per-frame external clock. */
export function useThrottledValue<T>(read: () => T, fps = 12): T {
  const [v, setV] = useState<T>(read)
  useEffect(() => { const id = setInterval(() => setV(read()), 1000 / fps); return () => clearInterval(id) }, [read, fps])
  return v
}
