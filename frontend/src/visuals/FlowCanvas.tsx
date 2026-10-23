import { useEffect, useRef, type MutableRefObject } from 'react'
import type { TrafficClass } from '../api/types'
import { hideTip, showTip } from '../components/ui'
import { CLASS_LABEL, packetAlias } from '../lib/format'
import { prefersReducedMotion } from '../hooks'
import { PlaybackModel, type Clock, type Snap } from './playback'
import { glyph, hexA, readPalette, rr, type Palette } from './sceneEngine'

interface Spr {
  id: number; cls: TrafficClass; x: number; y: number; tx: number; ty: number; a: number; ta: number
  enter: number; state: 'in' | 'q' | 'tx' | 'out' | 'drop'; late: boolean; sx: number; sy: number; stale: number; hidden: boolean
  hist: { x: number; y: number }[] // short position history for the transmission trail (tx/out only)
}
const CLASSES: TrafficClass[] = ['emergency', 'video', 'gps', 'normal']
const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x))

interface Props {
  model: PlaybackModel; clock: Clock; snapRef: MutableRefObject<Snap | null>
  selectedId: number | null; onSelect: (id: number | null) => void; queueCapacity: number; label: string
}

/** Renders the real recorded run as a packet flow: traffic -> queue -> scheduler -> link -> delivered. */
export function FlowCanvas({ model, clock, snapRef, selectedId, onSelect, queueCapacity, label }: Props) {
  const box = useRef<HTMLDivElement>(null), cv = useRef<HTMLCanvasElement>(null)
  const sel = useRef(selectedId); sel.current = selectedId
  const onSel = useRef(onSelect); onSel.current = onSelect
  const cap = useRef(queueCapacity); cap.current = queueCapacity
  // Sprite positions and the simulation-time cursor persist ACROSS scheduler switches (a new
  // `model` is created per scheduler, which re-runs the effect below). Without this, every
  // scheduler switch would tear down and rebuild the sprite map, forcing an instant snap instead
  // of the packets visibly sliding to their new queue order — see the reorder-animation note below.
  // They are cleared only when the underlying run itself changes (a genuinely new workload).
  const sprRef = useRef<Map<number, Spr>>(new Map())
  const lastTRef = useRef(-1)
  const lastViewRef = useRef<typeof model.view | null>(null)

  useEffect(() => {
    const canvas = cv.current!, wrap = box.current!, ctx = canvas.getContext('2d')!
    let pal: Palette = readPalette(), W = 0, H = 0, raf = 0, last = performance.now(), visible = true
    const reduced = prefersReducedMotion()
    const spr = sprRef.current
    if (lastViewRef.current !== model.view) { spr.clear(); lastTRef.current = -1; lastViewRef.current = model.view }
    let flash = 0, lastDecT = -1, lastDecId: number | null = null, hoverId: number | null = null, dirty = true
    const size = () => { const r = wrap.getBoundingClientRect(), d = Math.min(2, devicePixelRatio || 1); W = r.width; H = r.height; canvas.width = Math.round(W * d); canvas.height = Math.round(H * d); ctx.setTransform(d, 0, 0, d, 0, 0); dirty = true }
    size()
    const ro = new ResizeObserver(size); ro.observe(wrap)
    const mo = new MutationObserver(() => { pal = readPalette(); dirty = true }); mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const io = new IntersectionObserver(e => { visible = e[0].isIntersecting; if (visible) { last = performance.now(); dirty = true } }, { threshold: 0 }); io.observe(wrap)

    const L = () => {
      const u = Math.min(W / 1000, H / 400), cy = H * 0.57
      const qTail = W * 0.3, qHead = W * 0.66
      const r = clamp(Math.min(W, H * 2.4) / 90, 5, 11)
      const nSlot = Math.max(10, Math.min(36, Math.floor((qHead - qTail) / (r * 2.5))))
      const g = (qHead - qTail) / (nSlot - 1)
      const gap = Math.min(H * 0.15, 66 * u)
      return { u, cy, qTail, qHead, r, nSlot, g, srcX: W * 0.085, sx: W * 0.77, sr: 40 * u, sink: W * 0.95, srcY: [0, 1, 2, 3].map(i => cy + (i - 1.5) * gap) }
    }
    const slot = (i: number, l: ReturnType<typeof L>) => ({ x: l.qHead - i * l.g, y: l.cy })

    function frame(now: number) {
      raf = requestAnimationFrame(frame)
      if (!visible) return
      const dtReal = Math.min(0.06, (now - last) / 1000); last = now
      const before = clock.t; clock.advance(dtReal)
      const moved = clock.t !== before
      const l = L()
      // "recent" window in sim µs: about 0.9 s of real time at the current speed (visual trail only)
      const winUs = Math.max(20_000, clock.speed * 1e6 * 0.9)
      const jump = lastTRef.current < 0 || clock.t < lastTRef.current || clock.t - lastTRef.current > winUs * 2
      const instant = jump || reduced
      if (jump) spr.clear()
      lastTRef.current = clock.t
      const snap = model.snapshot(clock.t, winUs)
      snapRef.current = snap
      if (snap.decision && snap.decision.timeUs !== lastDecT) { lastDecT = snap.decision.timeUs; lastDecId = snap.decision.chosenPacketId; flash = 1 }
      flash = Math.max(0, flash - dtReal * 2.2)

      // ---- decide target state for each id ----
      const want = new Map<number, Spr['state']>()
      snap.recentArr.forEach(id => want.set(id, 'in'))
      snap.recentDep.forEach(id => want.set(id, 'out'))
      snap.recentDrop.forEach(id => want.set(id, 'drop'))
      snap.waiting.forEach(id => want.set(id, 'q'))
      if (snap.tx != null) want.set(snap.tx, 'tx')
      const waitIdx = new Map(snap.waiting.map((id, i) => [id, i]))
      let moving = flash > 0

      for (const [id, st] of want) {
        const p = model.view.pkt.get(id); if (!p) continue
        let s = spr.get(id)
        const src = l.srcY[CLASSES.indexOf(p.trafficClass)]
        if (!s) {
          s = { id, cls: p.trafficClass, x: l.srcX, y: src, tx: l.srcX, ty: src, a: 0, ta: 1, enter: instant ? 1 : 0, state: st, late: false, sx: l.srcX, sy: src, stale: 0, hidden: false, hist: [] }
          if (st === 'drop') { s.x = l.qTail - l.g * 0.6; s.y = l.cy; s.a = 1; s.enter = 1 }          // rejected at the queue entrance
          else if (st === 'out') { s.x = l.sx; s.y = l.cy; s.a = 1; s.enter = 1 }                       // already on the link
          spr.set(id, s)
        }
        s.stale = 0
        // an arriving packet that is already queued keeps flying in until its entry animation ends
        const prev = s.state; s.state = st
        s.late = model.sv.rec.get(id)?.outcome === 'LATE'
        if (st === 'q') {
          const i = waitIdx.get(id)!; const sl = slot(i, l); s.hidden = i >= l.nSlot
          s.tx = s.hidden ? l.qTail - l.g : sl.x; s.ty = sl.y; s.ta = s.hidden ? 0 : 1
        } else if (st === 'tx') { s.tx = l.sx; s.ty = l.cy; s.ta = 1; s.hidden = false }
        else if (st === 'out') {
          // spread departures along the link by how long ago they finished, so the stream is evenly spaced
          const end = model.sv.rec.get(id)?.txEndUs ?? clock.t; const age = clamp((clock.t - end) / winUs)
          s.tx = l.sx + l.sr + (l.sink - l.sx - l.sr) * age; s.ty = l.cy; s.ta = 0; s.hidden = false
        }
        else if (st === 'drop') { s.tx = l.qTail - l.g * 0.9; s.ty = l.cy + 64 * l.u; s.ta = 0 }
        else { s.tx = l.qTail - l.g * 0.6; s.ty = l.cy; s.ta = 1 }
        if (prev !== st && instant) { s.x = s.tx; s.y = s.ty; s.a = s.ta || 1 }
      }
      // ---- integrate ----
      const kq = instant ? 1 : 1 - Math.exp(-dtReal * 7), ka = instant ? 1 : 1 - Math.exp(-dtReal * 5)
      for (const [id, s] of spr) {
        if (!want.has(id)) { s.stale += dtReal; s.ta = 0; if (s.stale > 0.5 || instant) { spr.delete(id); continue } }
        if (s.enter < 1) {
          s.enter = Math.min(1, s.enter + dtReal / 0.85)
          const t = s.enter * s.enter * (3 - 2 * s.enter), x0 = s.sx + 14, y0 = s.sy
          const x3 = s.tx, y3 = s.ty, x1 = x0 + (x3 - x0) * 0.55, x2 = x3 - (x3 - x0) * 0.35, it = 1 - t
          s.x = it ** 3 * x0 + 3 * it * it * t * x1 + 3 * it * t * t * x2 + t ** 3 * x3
          s.y = it ** 3 * y0 + 3 * it * it * t * y0 + 3 * it * t * t * y3 + t ** 3 * y3
          s.a = Math.min(1, s.a + dtReal * 5); moving = true
        } else {
          const dx = s.tx - s.x, dy = s.ty - s.y
          const k = s.state === 'tx' ? 1 - Math.exp(-dtReal * 11) : kq
          s.x += dx * k; s.y += dy * k
          if (s.state === 'out') s.a = clamp((l.sink - s.x) / (90 * l.u) + 0.05)
          else if (s.state === 'drop') s.a = Math.max(0, s.a - dtReal * 1.1)
          else s.a += (s.ta - s.a) * ka
          if (Math.abs(dx) + Math.abs(dy) > 0.4) moving = true
          // Packet trail: only while actually moving through the link (transmitting or just
          // delivered), never in the queue — a short, fading history of real positions, not a
          // particle effect. Skipped under reduced motion (rule: reduce or remove the trail).
          if (!reduced && (s.state === 'tx' || s.state === 'out')) {
            s.hist.push({ x: s.x, y: s.y })
            if (s.hist.length > 7) s.hist.shift()
          } else if (s.hist.length) s.hist.length = 0
        }
      }
      if (!(moved || moving || dirty || clock.playing)) return
      dirty = false
      draw(l, snap)
    }

    function draw(l: ReturnType<typeof L>, snap: Snap) {
      const { u, cy } = l; const t = clock.t / 1e6
      ctx.clearRect(0, 0, W, H)
      ctx.font = `600 ${Math.max(9, 10.5 * u)}px 'Inter Variable', system-ui, sans-serif`
      const setLS = (v: number) => { (ctx as CanvasRenderingContext2D & { letterSpacing?: string }).letterSpacing = `${v * u}px` }
      // backdrop glow tied to congestion
      const cong = snap.point?.congestionLevel ?? 'LOW'
      const cc = cong === 'HIGH' ? pal.bad : cong === 'MEDIUM' ? pal.warn : pal.accent
      const gl = ctx.createRadialGradient((l.qTail + l.qHead) / 2, cy, 0, (l.qTail + l.qHead) / 2, cy, W * 0.4); gl.addColorStop(0, hexA(cc, cong === 'LOW' ? 0.05 : 0.1)); gl.addColorStop(1, hexA(cc, 0)); ctx.fillStyle = gl; ctx.fillRect(0, 0, W, H)

      // traffic sources + stream lines
      for (let i = 0; i < 4; i++) {
        const y = l.srcY[i], c = pal.cls[CLASSES[i]], x0 = l.srcX + 14, x3 = l.qTail - l.g * 0.6
        const gr = ctx.createLinearGradient(x0, 0, x3, 0); gr.addColorStop(0, hexA(c, 0.28)); gr.addColorStop(1, hexA(c, 0.03))
        ctx.strokeStyle = gr; ctx.lineWidth = 1.2 * u; ctx.beginPath(); ctx.moveTo(x0, y); ctx.bezierCurveTo(x0 + (x3 - x0) * 0.55, y, x3 - (x3 - x0) * 0.35, cy, x3, cy); ctx.stroke()
        ctx.fillStyle = hexA(c, 0.14); ctx.beginPath(); ctx.arc(l.srcX, y, 15 * u, 0, 7); ctx.fill(); ctx.strokeStyle = hexA(c, 0.7); ctx.lineWidth = 1.2 * u; ctx.stroke()
        glyph(ctx, CLASSES[i], l.srcX, y, 5 * u, c)
        ctx.fillStyle = hexA(pal.ink, 0.5); ctx.textAlign = 'left'; setLS(0.8); ctx.fillText(CLASS_LABEL[CLASSES[i]].toUpperCase(), l.srcX - 12 * u, y + 30 * u)
      }
      // queue channel
      const qh = 42 * u, qx = l.qTail - l.g * 0.9, qw = l.qHead - l.qTail + l.g * 1.8
      rr(ctx, qx, cy - qh / 2, qw, qh, qh / 2); ctx.fillStyle = hexA(pal.ink, 0.04); ctx.fill(); ctx.strokeStyle = hexA(pal.ink, 0.16); ctx.lineWidth = u; ctx.stroke()
      const occ = snap.point?.occupancy ?? 0
      const ty = cy + qh / 2 + 16 * u
      rr(ctx, qx + qh / 2, ty, qw - qh, 4 * u, 2 * u); ctx.fillStyle = hexA(pal.ink, 0.08); ctx.fill()
      const fw = (qw - qh) * clamp(occ)
      if (fw > 1) { rr(ctx, qx + qw - qh / 2 - fw, ty, fw, 4 * u, 2 * u); ctx.fillStyle = cc; ctx.fill() }
      // labels
      ctx.textAlign = 'center'; ctx.fillStyle = hexA(pal.ink, 0.6); setLS(1.6)
      const ql = snap.point?.queueLength ?? 0
      ctx.fillText(`QUEUE  ${ql} / ${cap.current}`, (l.qTail + l.qHead) / 2, cy - qh / 2 - 20 * u)
      setLS(1.2); ctx.fillStyle = hexA(cc, 0.95); ctx.fillText(`CONGESTION ${cong}`, (l.qTail + l.qHead) / 2, ty + 20 * u)
      if (snap.waiting.length > l.nSlot) { ctx.textAlign = 'right'; ctx.fillStyle = hexA(pal.ink, 0.7); ctx.fillText(`+${snap.waiting.length - l.nSlot} more`, qx + 2 * u, cy - qh / 2 - 6 * u) }

      // scheduler
      const R = l.sr
      ctx.strokeStyle = hexA(pal.accent, 0.35 + 0.5 * flash); ctx.lineWidth = 1.3 * u; ctx.beginPath(); ctx.arc(l.sx, cy, R, 0, 7); ctx.stroke()
      ctx.fillStyle = hexA(pal.accent, 0.06 + 0.12 * flash); ctx.fill()
      ctx.setLineDash([3 * u, 7 * u]); ctx.strokeStyle = hexA(pal.accent, 0.45); ctx.beginPath(); ctx.arc(l.sx, cy, R * 1.28, t * 0.6, t * 0.6 + 6.28); ctx.stroke(); ctx.setLineDash([])
      if (flash > 0) { ctx.strokeStyle = hexA(pal.accent, 0.5 * flash); ctx.lineWidth = 1.6 * u; ctx.beginPath(); ctx.arc(l.sx, cy, R * (1 + (1 - flash) * 0.9), 0, 7); ctx.stroke() }
      ctx.fillStyle = pal.accent; ctx.beginPath(); ctx.arc(l.sx, cy, 4 * u, 0, 7); ctx.fill()
      ctx.textAlign = 'center'; ctx.fillStyle = hexA(pal.ink, 0.6); setLS(1.6)
      const sname = model.id === 'ACAPS' ? 'ACAPS' : model.id === 'FIFO' ? 'FIFO' : 'STATIC PRIORITY'
      ctx.fillText(sname, l.sx, cy + R * 1.28 + 26 * u)
      // link
      const busy = snap.tx != null
      ctx.strokeStyle = hexA(pal.accent, busy ? 0.2 : 0.08); ctx.lineWidth = 9 * u; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(l.sx + R, cy); ctx.lineTo(l.sink, cy); ctx.stroke()
      ctx.strokeStyle = hexA(pal.accent, busy ? 0.6 : 0.25); ctx.lineWidth = 2.4 * u; ctx.setLineDash([10 * u, 10 * u]); ctx.lineDashOffset = -t * 220 * u * Math.max(0.2, clock.speed * 4); ctx.beginPath(); ctx.moveTo(l.sx + R, cy); ctx.lineTo(l.sink, cy); ctx.stroke(); ctx.setLineDash([])
      ctx.fillStyle = hexA(pal.ok, 0.14); ctx.beginPath(); ctx.arc(l.sink + 4 * u, cy, 14 * u, 0, 7); ctx.fill(); ctx.strokeStyle = hexA(pal.ok, 0.7); ctx.lineWidth = 1.2 * u; ctx.stroke()
      ctx.fillStyle = hexA(pal.ink, 0.6); setLS(1.6); ctx.textAlign = 'center'
      ctx.fillText('LINK', (l.sx + l.sink) / 2 + 10 * u, cy + 34 * u)
      ctx.textAlign = 'right'; ctx.fillText(`DELIVERED ${snap.delivered + snap.late}`, l.sink + 18 * u, cy - 30 * u)
      if (snap.late > 0) { ctx.fillStyle = hexA(pal.warn, 0.95); ctx.fillText(`LATE ${snap.late}`, l.sink + 18 * u, cy - 44 * u) }
      ctx.fillStyle = hexA(snap.dropped ? pal.bad : pal.ink, snap.dropped ? 0.9 : 0.5); ctx.fillText(`DROPPED ${snap.dropped}`, l.sink + 18 * u, cy + 50 * u)

      // packets: draw in-flight first, queue next, tx on top
      const order = [...spr.values()].sort((a, b) => (a.state === 'tx' ? 2 : a.state === 'q' ? 1 : 0) - (b.state === 'tx' ? 2 : b.state === 'q' ? 1 : 0))
      for (const s of order) {
        if (s.a < 0.02) continue
        const p = model.view.pkt.get(s.id)!; const c = pal.cls[s.cls]
        // Decision Pulse (design brief §2): exactly the packet the backend's most recent decision
        // actually chose (`lastDecId`, keyed by the packet's own stable id — never invented) gets a
        // brief lift and glow while `flash` decays; every other still-queued packet dims slightly
        // at the same time, so the choice reads as a single, deliberate event, not continuous motion.
        const pulseScale = reduced ? 0.3 : 1
        const isPulse = s.id === lastDecId && flash > 0
        const r = l.r * (s.state === 'tx' ? 1.3 : isPulse ? 1 + 0.22 * flash * pulseScale : 1)
        ctx.save(); ctx.globalAlpha = clamp(s.a * (s.state === 'q' && !isPulse && flash > 0 ? 1 - 0.35 * flash * pulseScale : 1))
        // Trail: a short, fading polyline through the packet's own recent real positions — only
        // while it is actually moving through the link (never in the queue), never under reduced motion.
        if (s.hist.length > 1) {
          for (let i = 1; i < s.hist.length; i++) {
            const a0 = s.hist[i - 1], a1 = s.hist[i], fa = (i / s.hist.length) * 0.3
            ctx.strokeStyle = hexA(c, fa); ctx.lineWidth = Math.max(1, r * 0.5 * (i / s.hist.length)); ctx.lineCap = 'round'
            ctx.beginPath(); ctx.moveTo(a0.x, a0.y); ctx.lineTo(a1.x, a1.y); ctx.stroke()
          }
        }
        if (s.state === 'q' && !s.hidden && s.enter >= 1) {
          // remaining share of the packet's delay budget, from recorded deadline and the playback clock
          const frac = (p.deadlineUs - clock.t) / p.delayBudgetUs
          const col = frac <= 0 ? pal.bad : frac < 0.25 ? pal.warn : pal.accent
          ctx.lineWidth = 1.7 * u; ctx.strokeStyle = hexA(pal.ink, 0.1); ctx.beginPath(); ctx.arc(s.x, s.y, r + 4.5 * u, 0, 7); ctx.stroke()
          ctx.strokeStyle = hexA(col, 0.95); ctx.lineCap = 'round'; if (frac <= 0) ctx.setLineDash([2.4 * u, 3 * u])
          ctx.beginPath(); ctx.arc(s.x, s.y, r + 4.5 * u, -Math.PI / 2, -Math.PI / 2 + clamp(frac, 0.04, 1) * 6.283); ctx.stroke(); ctx.setLineDash([])
        }
        if (s.state === 'tx') { const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, r * 3.4); g.addColorStop(0, hexA(c, 0.5)); g.addColorStop(1, hexA(c, 0)); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(s.x, s.y, r * 3.4, 0, 7); ctx.fill() }
        if (isPulse && s.state !== 'tx') { const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, r * 3 * pulseScale); g.addColorStop(0, hexA(c, 0.4 * flash * pulseScale)); g.addColorStop(1, hexA(c, 0)); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(s.x, s.y, r * 3 * pulseScale, 0, 7); ctx.fill() }
        glyph(ctx, s.cls, s.x, s.y, r, c)
        if (s.state === 'out' && s.late) { ctx.strokeStyle = pal.warn; ctx.lineWidth = 1.6 * u; ctx.beginPath(); ctx.arc(s.x, s.y, r + 3 * u, 0, 7); ctx.stroke() }
        if (s.state === 'drop') { ctx.strokeStyle = pal.bad; ctx.lineWidth = 1.7 * u; ctx.beginPath(); ctx.moveTo(s.x - r, s.y - r); ctx.lineTo(s.x + r, s.y + r); ctx.moveTo(s.x + r, s.y - r); ctx.lineTo(s.x - r, s.y + r); ctx.stroke() }
        if (s.id === sel.current || s.id === hoverId) { ctx.strokeStyle = pal.ink; ctx.lineWidth = 1.6 * u; ctx.beginPath(); ctx.arc(s.x, s.y, r + 8 * u, 0, 7); ctx.stroke() }
        if (s.state === 'tx' || isPulse) { ctx.fillStyle = pal.ink; ctx.textAlign = 'center'; setLS(0.6); ctx.font = `600 ${11 * u}px 'JetBrains Mono Variable', monospace`; ctx.fillText(packetAlias(s.cls, s.id), s.x, s.y - r - 12 * u); ctx.font = `600 ${Math.max(9, 10.5 * u)}px 'Inter Variable', sans-serif` }
        ctx.restore()
      }
    }

    const pick = (mx: number, my: number): Spr | null => {
      let best: Spr | null = null, bd = 1e9
      for (const s of spr.values()) { if (s.a < 0.3 || s.hidden) continue; const d = Math.hypot(s.x - mx, s.y - my); if (d < bd && d < 20) { bd = d; best = s } }
      return best
    }
    const onMove = (e: PointerEvent) => {
      const r = wrap.getBoundingClientRect(); const s = pick(e.clientX - r.left, e.clientY - r.top)
      const nid = s?.id ?? null
      if (nid !== hoverId) { hoverId = nid; dirty = true }
      canvas.style.cursor = s ? 'pointer' : 'default'
      if (s) { const p = model.view.pkt.get(s.id)!; showTip({ title: packetAlias(p.trafficClass, s.id), rows: [{ k: 'Type', v: CLASS_LABEL[p.trafficClass] }, { k: 'Size', v: `${p.sizeBytes} B` }, { k: 'Click', v: 'Inspect' }] }, e.clientX, e.clientY) } else hideTip()
    }
    const onClick = (e: MouseEvent) => { const r = wrap.getBoundingClientRect(); const s = pick(e.clientX - r.left, e.clientY - r.top); onSel.current(s ? s.id : null); dirty = true }
    const onLeave = () => { hoverId = null; hideTip(); dirty = true }
    canvas.addEventListener('pointermove', onMove); canvas.addEventListener('click', onClick); canvas.addEventListener('pointerleave', onLeave)
    raf = requestAnimationFrame(frame)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); mo.disconnect(); io.disconnect(); canvas.removeEventListener('pointermove', onMove); canvas.removeEventListener('click', onClick); canvas.removeEventListener('pointerleave', onLeave); hideTip() }
  }, [model, clock, snapRef])

  return <div ref={box} className="flow-box"><canvas ref={cv} role="img" aria-label={label} /></div>
}
