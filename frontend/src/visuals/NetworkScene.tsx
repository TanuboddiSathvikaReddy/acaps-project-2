import { useEffect, useRef, type MutableRefObject } from 'react'
import { prefersReducedMotion } from '../hooks'
import { hideTip, showTip } from '../components/ui'
import { readPalette, SceneEngine, type Hit, type Palette } from './sceneEngine'

/** DPR-aware canvas that hosts the conceptual scene. Pauses when off-screen, freezes for reduced motion. */
export function NetworkScene({ stepRef, autoScan, className, label }: { stepRef: MutableRefObject<number>; autoScan?: boolean; className?: string; label: string }) {
  const wrap = useRef<HTMLDivElement>(null)
  const cv = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = cv.current!, box = wrap.current!
    const ctx = canvas.getContext('2d')!
    const eng = new SceneEngine()
    let pal: Palette = readPalette()
    let visible = true, raf = 0, last = performance.now(), hover: Hit['key'] | null = null
    const pointer = { x: 0, y: 0 }
    const reduced = prefersReducedMotion()
    const size = () => {
      const r = box.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1)
      canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); eng.setSize(r.width, r.height)
    }
    size()
    const ro = new ResizeObserver(() => { size(); if (reduced) paint() }); ro.observe(box)
    const mo = new MutationObserver(() => { pal = readPalette(); if (reduced) paint() }); mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const io = new IntersectionObserver(e => { visible = e[0].isIntersecting; if (visible && !reduced) { last = performance.now(); loop(last) } }, { threshold: 0.01 }); io.observe(box)
    const params = () => ({ step: stepRef.current, autoScan, pointer })
    const paint = () => { eng.render(ctx, pal, params(), hover) }
    // warm start: the scene never appears empty on first paint
    for (let i = 0; i < (reduced ? 260 : 200); i++) eng.update(1 / 30, params())
    if (reduced) paint()
    function loop(now: number) {
      cancelAnimationFrame(raf)
      if (!visible || reduced) return
      const dt = Math.min(0.05, (now - last) / 1000); last = now
      eng.update(dt, params()); paint()
      raf = requestAnimationFrame(loop)
    }
    if (!reduced) raf = requestAnimationFrame(loop)
    const move = (e: PointerEvent) => {
      const r = box.getBoundingClientRect()
      pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1; pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1
      const h = eng.hit(e.clientX - r.left, e.clientY - r.top)
      hover = h?.key ?? null; canvas.style.cursor = h ? 'help' : 'default'
      if (h) showTip({ title: h.title, body: h.body }, e.clientX, e.clientY); else hideTip()
      if (reduced) paint()
    }
    const leave = () => { pointer.x = 0; pointer.y = 0; hover = null; hideTip() }
    box.addEventListener('pointermove', move); box.addEventListener('pointerleave', leave)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); mo.disconnect(); io.disconnect(); box.removeEventListener('pointermove', move); box.removeEventListener('pointerleave', leave); hideTip() }
  }, [stepRef, autoScan])
  return <div ref={wrap} className={className}><canvas ref={cv} role="img" aria-label={label} style={{ width: '100%', height: '100%', display: 'block' }} /></div>
}
