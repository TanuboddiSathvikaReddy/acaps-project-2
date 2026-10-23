/**
 * Conceptual network scene used on the landing page (hero + scroll story).
 *
 * IMPORTANT: this is an ILLUSTRATION of the idea behind ACAPS, not a simulation and not backend data.
 * It never displays numbers and is labelled "Illustration" wherever it appears. Real behaviour is only ever
 * shown from API responses (see visuals/FlowCanvas.tsx).
 */
import type { TrafficClass } from '../api/types'

export interface Palette {
  bg: string; ink: string; dim: string; accent: string; accent2: string; violet: string; ok: string; warn: string; bad: string
  cls: Record<TrafficClass, string>; line: string
}
export const readPalette = (): Palette => {
  const s = getComputedStyle(document.documentElement)
  const g = (n: string) => s.getPropertyValue(n).trim()
  return {
    bg: g('--canvas-bg'), ink: g('--canvas-ink'), dim: g('--canvas-dim'), accent: g('--accent'), accent2: g('--accent-2'), violet: g('--accent-3'),
    ok: g('--ok'), warn: g('--warn'), bad: g('--bad'), line: g('--line-strong'),
    cls: { emergency: g('--c-emergency'), video: g('--c-video'), gps: g('--c-gps'), normal: g('--c-normal') },
  }
}

const CAP = 14
const CLASSES: TrafficClass[] = ['emergency', 'video', 'gps', 'normal']
const MIXW = [0.2, 0.3, 0.2, 0.3]
const BUDGET: Record<TrafficClass, number> = { emergency: 4.2, video: 6.5, gps: 5.2, normal: 10 }

type Phase = 'stream' | 'queued' | 'sel' | 'tx' | 'done' | 'drop'
interface Pkt {
  id: number; cls: TrafficClass; phase: Phase; t: number; x: number; y: number; sx: number; sy: number; age: number
  srcIdx: number; fx: number; fy: number; life: number; chosen: boolean; reason: string
}

function rng(seed: number) { let s = seed >>> 0; return () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 } }
const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x))
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const smooth = (t: number) => t * t * (3 - 2 * t)
/** piecewise-linear over integer steps with smoothing */
function interp(a: number[], s: number) { const i = clamp(Math.floor(s), 0, a.length - 1), j = Math.min(a.length - 1, i + 1); return lerp(a[i], a[j], smooth(clamp(s - i))) }
const ramp = (s: number, a: number, b: number) => smooth(clamp((s - a) / (b - a)))

export interface SceneParams { step: number; autoScan?: boolean; pointer?: { x: number; y: number } }
export interface Hit { key: 'source' | 'queue' | 'scheduler' | 'link'; title: string; body: string }

export class SceneEngine {
  pk: Pkt[] = []; q: Pkt[] = []
  private r = rng(7); private nid = 1; private spawnAcc = 0
  private busy = 0; private serving: Pkt | null = null; private time = 0
  private scan = 0; private scanClock = 0
  private px = 0; private py = 0
  private layout = { w: 0, h: 0, u: 1, srcX: 0, qTail: 0, qHead: 0, g: 0, cy: 0, sx: 0, sr: 0, sink: 0, srcY: [0, 0, 0, 0] as number[] }
  lastChosenAt = -10; lastReason = ''

  setSize(w: number, h: number) {
    const u = Math.min(w / 1000, h / 420)
    const cy = h * 0.5
    const qTail = w * 0.3, qHead = w * 0.65
    this.layout = { w, h, u, srcX: w * 0.085, qTail, qHead, g: (qHead - qTail) / (CAP - 1), cy, sx: w * 0.765, sr: 44 * u, sink: w * 0.95, srcY: [0, 1, 2, 3].map(i => cy + (i - 1.5) * Math.min(h * 0.14, 70 * u)) }
  }

  private pickClass() { let x = this.r(), a = 0; for (let i = 0; i < 4; i++) { a += MIXW[i]; if (x <= a) return i } return 3 }
  private frac(p: Pkt) { return 1 - p.age / BUDGET[p.cls] }
  tier(p: Pkt): 'SAFE' | 'AT_RISK' | 'INFEASIBLE' { const f = this.frac(p); return f <= 0 ? 'INFEASIBLE' : f < 0.34 ? 'AT_RISK' : 'SAFE' }

  private slot(i: number) { const L = this.layout; return { x: L.qHead - i * L.g, y: L.cy } }

  update(dtReal: number, P: SceneParams) {
    const L = this.layout; if (!L.w) return
    const s = P.step
    // cinematic slow-motion while a decision is being made / shown
    let slow = 1 - 0.72 * ramp(s, 4.5, 4.9) * (1 - ramp(s, 5.8, 6.2))
    if (P.autoScan) { this.scanClock += dtReal; const ph = (this.scanClock % 9) / 9; slow = 1 - 0.6 * (ph > 0.55 && ph < 0.72 ? 1 : 0) }
    const dt = dtReal * slow; this.time += dt
    this.px += ((P.pointer?.x ?? 0) - this.px) * Math.min(1, dtReal * 3); this.py += ((P.pointer?.y ?? 0) - this.py) * Math.min(1, dtReal * 3)

    const rate = interp([1.7, 2.4, 3.6, 3.6, 3.3, 3.1, 2.5, 2.2], s) * (P.autoScan ? 1.35 : 1)
    const svc = interp([0.52, 0.95, 1.6, 1.55, 1.4, 1.2, 0.85, 0.7], s) * (P.autoScan ? 1.15 : 1)
    const acaps = ramp(s, 3.7, 4.3) > 0.5 || !!P.autoScan
    this.scan = P.autoScan ? (() => { const ph = (this.scanClock % 9) / 9; return ph > 0.5 && ph < 0.75 ? Math.sin(((ph - 0.5) / 0.25) * Math.PI) : 0 })() : ramp(s, 3.9, 4.3) * (1 - ramp(s, 4.9, 5.3))

    // arrivals
    this.spawnAcc += rate * dt
    while (this.spawnAcc >= 1) {
      this.spawnAcc -= 1
      const ci = this.pickClass()
      const y = L.srcY[ci]
      this.pk.push({ id: this.nid++, cls: CLASSES[ci], phase: 'stream', t: 0, x: L.srcX, y, sx: L.srcX, sy: y, age: 0, srcIdx: ci, fx: 0, fy: 0, life: 0, chosen: false, reason: '' })
    }

    // advance packets
    for (const p of this.pk) {
      if (p.phase === 'stream') {
        p.t += dt / 1.15
        const t = smooth(clamp(p.t)); const x0 = p.sx + 14, y0 = p.sy, x3 = L.qTail - L.g * 0.6, y3 = L.cy
        const x1 = x0 + (x3 - x0) * 0.5, y1 = y0, x2 = x3 - (x3 - x0) * 0.4, y2 = y3
        const it = 1 - t
        p.x = it ** 3 * x0 + 3 * it * it * t * x1 + 3 * it * t * t * x2 + t ** 3 * x3
        p.y = it ** 3 * y0 + 3 * it * it * t * y1 + 3 * it * t * t * y2 + t ** 3 * y3
        if (p.t >= 1) {
          if (this.q.length >= CAP) { p.phase = 'drop'; p.life = 0 } else { p.phase = 'queued'; this.q.push(p) }
        }
      } else if (p.phase === 'queued') {
        p.age += dt
        const i = this.q.indexOf(p), sl = this.slot(i), k = 1 - Math.exp(-dtReal * 8)
        p.x += (sl.x - p.x) * k; p.y += (sl.y - p.y) * k
      } else if (p.phase === 'sel') {
        p.t += dt / 0.55
        const t = smooth(clamp(p.t)), it = 1 - t
        const mx = (p.fx + L.sx) / 2, my = L.cy - 70 * L.u
        p.x = it * it * p.fx + 2 * it * t * mx + t * t * L.sx; p.y = it * it * p.fy + 2 * it * t * my + t * t * L.cy
        if (p.t >= 1) { p.phase = 'tx'; p.t = 0 }
      } else if (p.phase === 'tx') {
        p.t += dt / Math.max(0.3, svc - 0.5)
        const t = clamp(p.t); p.x = lerp(L.sx + L.sr * 0.6, L.sink, t * t * (3 - 2 * t)); p.y = L.cy
        if (p.t >= 1) { p.phase = 'done'; p.life = 0; this.serving = null; this.busy = 0 }
      } else { p.life += dtReal }
    }
    // server: choose next
    if (!this.serving && this.q.length) {
      const ch = this.choose(acaps)
      this.q.splice(this.q.indexOf(ch.p), 1)
      ch.p.phase = 'sel'; ch.p.t = 0; ch.p.fx = ch.p.x; ch.p.fy = ch.p.y; ch.p.chosen = true; ch.p.reason = ch.reason
      this.serving = ch.p; this.lastChosenAt = this.time; this.lastReason = ch.reason
    }
    this.pk = this.pk.filter(p => !((p.phase === 'done' || p.phase === 'drop') && p.life > (p.phase === 'done' ? 1.1 : 1.0)))
  }

  private choose(acaps: boolean): { p: Pkt; reason: string } {
    if (!acaps) return { p: this.q[0], reason: 'Arrived first' }
    const at = this.q.filter(p => this.tier(p) === 'AT_RISK')
    if (at.length) { at.sort((a, b) => this.frac(a) * BUDGET[a.cls] - this.frac(b) * BUDGET[b.cls]); return { p: at[0], reason: 'AT RISK · LEAST SLACK' } }
    const safe = this.q.filter(p => this.tier(p) === 'SAFE')
    const pool = safe.length ? safe : this.q
    const rank = (p: Pkt) => CLASSES.indexOf(p.cls)
    const best = [...pool].sort((a, b) => rank(a) - rank(b) || this.q.indexOf(a) - this.q.indexOf(b))[0]
    return { p: best, reason: safe.length ? 'SAFE · CRITICALITY' : 'INFEASIBLE · TRIAGE' }
  }

  hit(mx: number, my: number): Hit | null {
    const L = this.layout, u = L.u
    if (mx < L.srcX + 40 * u && mx > L.srcX - 30 * u) return { key: 'source', title: 'Traffic sources', body: 'Four classes of traffic enter the network: Emergency, Video, GPS and Normal.' }
    if (mx > L.qTail - L.g && mx < L.qHead + L.g && Math.abs(my - L.cy) < 44 * u) return { key: 'queue', title: 'Queue', body: 'Packets wait in a finite buffer. When it is full, new arrivals are dropped.' }
    if (Math.hypot(mx - L.sx, my - L.cy) < L.sr * 1.2) return { key: 'scheduler', title: 'Scheduler', body: 'Chooses which waiting packet uses the link next. This is where FIFO, Static Priority and ACAPS differ.' }
    if (mx > L.sx + L.sr && mx < L.sink + 20 * u && Math.abs(my - L.cy) < 30 * u) return { key: 'link', title: 'Output link', body: 'Transmits one packet at a time. Its bandwidth sets how long each transmission takes.' }
    return null
  }

  render(ctx: CanvasRenderingContext2D, pal: Palette, P: SceneParams, hover: Hit['key'] | null) {
    const L = this.layout, { w, h, u, cy } = L; if (!w) return
    const s = P.step
    const rings = ramp(s, 2.7, 3.4), schedOn = 0.35 + 0.65 * ramp(s, 3.4, 4.2), linkNarrow = interp([0, 0, 1, 1, 0.85, 0.5, 0.15, 0], s)
    const occ = this.q.length / CAP
    ctx.clearRect(0, 0, w, h)
    ctx.font = `600 ${Math.max(9, 10.5 * u)}px 'Inter Variable', system-ui, sans-serif`; ctx.textBaseline = 'alphabetic'
    const ox = this.px * 7 * u, oy = this.py * 5 * u

    // ambient glow behind scheduler
    ctx.save(); ctx.translate(ox * 0.4, oy * 0.4)
    const gl = ctx.createRadialGradient(L.sx, cy, 0, L.sx, cy, 260 * u); gl.addColorStop(0, hexA(pal.accent, 0.16 * schedOn)); gl.addColorStop(1, hexA(pal.accent, 0))
    ctx.fillStyle = gl; ctx.fillRect(0, 0, w, h); ctx.restore()

    // ---- stream links (sources -> queue) ----
    ctx.save(); ctx.translate(ox * 0.8, oy * 0.8)
    for (let i = 0; i < 4; i++) {
      const y0 = L.srcY[i], x0 = L.srcX + 14, x3 = L.qTail - L.g * 0.6
      const gr = ctx.createLinearGradient(x0, 0, x3, 0); gr.addColorStop(0, hexA(pal.cls[CLASSES[i]], 0.28)); gr.addColorStop(1, hexA(pal.cls[CLASSES[i]], 0.03))
      ctx.strokeStyle = gr; ctx.lineWidth = 1.2 * u; ctx.beginPath(); ctx.moveTo(x0, y0)
      ctx.bezierCurveTo(x0 + (x3 - x0) * 0.5, y0, x3 - (x3 - x0) * 0.4, cy, x3, cy); ctx.stroke()
    }
    // source nodes
    for (let i = 0; i < 4; i++) {
      const y = L.srcY[i], c = pal.cls[CLASSES[i]]
      ctx.fillStyle = hexA(c, hover === 'source' ? 0.28 : 0.14); ctx.beginPath(); ctx.arc(L.srcX, y, 15 * u, 0, 7); ctx.fill()
      ctx.strokeStyle = hexA(c, 0.7); ctx.lineWidth = 1.2 * u; ctx.stroke()
      glyph(ctx, CLASSES[i], L.srcX, y, 5.2 * u, c)
    }
    ctx.restore()

    // ---- queue channel ----
    ctx.save(); ctx.translate(ox, oy)
    const qx = L.qTail - L.g * 0.9, qw = L.qHead - L.qTail + L.g * 1.8, qh = 40 * u
    rr(ctx, qx, cy - qh / 2, qw, qh, qh / 2)
    ctx.fillStyle = hexA(pal.ink, hover === 'queue' ? 0.07 : 0.04); ctx.fill(); ctx.strokeStyle = hexA(pal.ink, 0.16); ctx.lineWidth = 1 * u; ctx.stroke()
    for (let i = 0; i < CAP; i++) { const sl = this.slot(i); ctx.fillStyle = hexA(pal.ink, 0.09); ctx.beginPath(); ctx.arc(sl.x, cy + qh / 2 + 9 * u, 1.2 * u, 0, 7); ctx.fill() }
    // occupancy bar: the difference between a healthy and a congested queue at a glance
    const oc = occ > 0.7 ? pal.bad : occ > 0.35 ? pal.warn : pal.accent
    rr(ctx, qx + qh / 2, cy + qh / 2 + 16 * u, qw - qh, 3 * u, 2 * u); ctx.fillStyle = hexA(pal.ink, 0.08); ctx.fill()
    const fillW = (qw - qh) * occ
    if (fillW > 1) { rr(ctx, qx + qw - qh / 2 - fillW, cy + qh / 2 + 16 * u, fillW, 3 * u, 2 * u); ctx.fillStyle = oc; ctx.globalAlpha = 0.9; ctx.fill(); ctx.globalAlpha = 1 }

    // scan lines from the scheduler to waiting packets
    if (this.scan > 0.01) {
      for (let i = 0; i < this.q.length; i++) {
        const p = this.q[i]; const wave = clamp(this.scan * 1.4 - i * 0.05, 0, 1)
        ctx.strokeStyle = hexA(pal.accent, 0.35 * wave); ctx.lineWidth = 1 * u; ctx.beginPath(); ctx.moveTo(L.sx, cy)
        ctx.quadraticCurveTo((L.sx + p.x) / 2, cy - (28 + i * 3) * u, p.x, p.y - 12 * u); ctx.stroke()
      }
    }
    // packets
    for (const p of this.pk) this.drawPacket(ctx, p, pal, u, rings, hover)
    ctx.restore()

    // ---- scheduler ----
    ctx.save(); ctx.translate(ox * 1.3, oy * 1.3)
    const R = L.sr, t = this.time
    ctx.strokeStyle = hexA(pal.accent, 0.18 + 0.3 * schedOn); ctx.lineWidth = 1.2 * u
    ctx.beginPath(); ctx.arc(L.sx, cy, R, 0, 7); ctx.stroke()
    ctx.fillStyle = hexA(pal.accent, 0.05 + 0.08 * schedOn + (hover === 'scheduler' ? 0.06 : 0)); ctx.fill()
    ctx.setLineDash([3 * u, 7 * u]); ctx.strokeStyle = hexA(pal.accent, 0.5 * schedOn); ctx.beginPath(); ctx.arc(L.sx, cy, R * 1.28, t * 0.4, t * 0.4 + 6.28); ctx.stroke(); ctx.setLineDash([])
    if (this.scan > 0.01) { ctx.strokeStyle = hexA(pal.accent, 0.5 * (1 - (this.scan % 1))); ctx.lineWidth = 1.6 * u; ctx.beginPath(); ctx.arc(L.sx, cy, R * (1 + this.scan * 1.1), 0, 7); ctx.stroke() }
    // rotating sweep arc
    ctx.strokeStyle = hexA(pal.accent, 0.9 * schedOn); ctx.lineWidth = 2.2 * u; ctx.lineCap = 'round'
    ctx.beginPath(); ctx.arc(L.sx, cy, R * 0.66, t * (0.8 + this.scan * 2), t * (0.8 + this.scan * 2) + 1.3); ctx.stroke()
    ctx.fillStyle = pal.accent; ctx.beginPath(); ctx.arc(L.sx, cy, 4.2 * u, 0, 7); ctx.fill()
    ctx.restore()

    // ---- output link ----
    ctx.save(); ctx.translate(ox * 0.9, oy * 0.9)
    const lw = lerp(6.5 * u, 2.6 * u, linkNarrow), lx0 = L.sx + R, lx1 = L.sink
    const lc = linkNarrow > 0.55 ? pal.warn : pal.accent
    ctx.strokeStyle = hexA(lc, 0.14); ctx.lineWidth = lw + 8 * u; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(lx0, cy); ctx.lineTo(lx1, cy); ctx.stroke()
    ctx.strokeStyle = hexA(lc, 0.55); ctx.lineWidth = lw * 0.5; ctx.setLineDash([10 * u, 10 * u]); ctx.lineDashOffset = -t * (60 - 30 * linkNarrow) * u; ctx.beginPath(); ctx.moveTo(lx0, cy); ctx.lineTo(lx1, cy); ctx.stroke(); ctx.setLineDash([])
    ctx.fillStyle = hexA(pal.ok, 0.16); ctx.beginPath(); ctx.arc(lx1 + 4 * u, cy, 13 * u, 0, 7); ctx.fill(); ctx.strokeStyle = hexA(pal.ok, 0.7); ctx.lineWidth = 1.2 * u; ctx.stroke()
    if (hover === 'link') { ctx.strokeStyle = hexA(pal.ink, 0.3); ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(lx1 + 4 * u, cy, 18 * u, 0, 7); ctx.stroke() }
    ctx.restore()

    // ---- labels ----
    ctx.save(); ctx.textAlign = 'center'; ctx.fillStyle = hexA(pal.ink, 0.55)
    const lab = (txt: string, x: number, y: number, a = 1) => { ctx.globalAlpha = a; (ctx as CanvasRenderingContext2D & { letterSpacing?: string }).letterSpacing = `${1.6 * u}px`; ctx.fillText(txt, x, y) }
    lab('TRAFFIC', L.srcX, cy + 2.4 * Math.min(h * 0.14, 70 * u) + 8 * u)
    lab('QUEUE', (L.qTail + L.qHead) / 2, cy - qh / 2 - 22 * u, ramp(s, 0.6, 1.4))
    lab('SCHEDULER', L.sx, cy + R * 1.28 + 26 * u, 0.5 + 0.5 * ramp(s, 3.4, 4.2))
    lab('OUTPUT LINK', (L.sx + L.sink) / 2 + 16 * u, cy + 34 * u, 1)
    ctx.restore()

    // decision callout
    const sinceChosen = this.time - this.lastChosenAt
    const callout = ramp(s, 4.9, 5.4) * (1 - ramp(s, 6.4, 6.9))
    if (callout > 0.02 && this.serving && this.lastReason) {
      const p = this.serving
      ctx.save(); ctx.globalAlpha = callout; ctx.textAlign = 'left'
      const cx = clamp(p.x + 18 * u, 8, w - 190 * u), cyy = cy - 96 * u
      rr(ctx, cx, cyy - 22 * u, 176 * u, 30 * u, 15 * u); ctx.fillStyle = hexA(pal.bg, 0.78); ctx.fill(); ctx.strokeStyle = hexA(pal.accent, 0.7); ctx.lineWidth = 1 * u; ctx.stroke()
      ctx.fillStyle = pal.ink; (ctx as CanvasRenderingContext2D & { letterSpacing?: string }).letterSpacing = `${1.2 * u}px`; ctx.fillText(this.lastReason, cx + 14 * u, cyy - 2.5 * u)
      ctx.restore(); void sinceChosen
    }
  }

  private drawPacket(ctx: CanvasRenderingContext2D, p: Pkt, pal: Palette, u: number, rings: number, hover: Hit['key'] | null) {
    const c = pal.cls[p.cls]
    let a = 1, r = Math.min(this.layout.g * 0.34, 12 * u)
    r = Math.max(r, 5.5 * u)
    if (p.phase === 'done') a = 1 - clamp(p.life / 1.1)
    if (p.phase === 'drop') { a = 1 - clamp(p.life / 1.0); p.y += 0.6 * u; p.x -= 0.15 * u }
    if (p.phase === 'stream') a = clamp(p.t * 4)
    if (p.phase === 'sel' || p.phase === 'tx') r *= 1.25
    ctx.save(); ctx.globalAlpha = a
    if (p.phase === 'tx') { const tr = ctx.createLinearGradient(p.x - 60 * u, 0, p.x, 0); tr.addColorStop(0, hexA(pal.accent, 0)); tr.addColorStop(1, hexA(pal.accent, 0.5)); ctx.strokeStyle = tr; ctx.lineWidth = 3 * u; ctx.beginPath(); ctx.moveTo(p.x - 60 * u, p.y); ctx.lineTo(p.x, p.y); ctx.stroke() }
    if (rings > 0.02 && p.phase === 'queued') {
      const f = clamp(this.frac(p)), tier = this.tier(p)
      const col = tier === 'SAFE' ? pal.accent : tier === 'AT_RISK' ? pal.warn : pal.bad
      ctx.lineWidth = 1.8 * u; ctx.strokeStyle = hexA(pal.ink, 0.1 * rings); ctx.beginPath(); ctx.arc(p.x, p.y, r + 5 * u, 0, 7); ctx.stroke()
      ctx.strokeStyle = hexA(col, 0.95 * rings); ctx.lineCap = 'round'
      if (tier === 'INFEASIBLE') ctx.setLineDash([2.5 * u, 3 * u])
      ctx.beginPath(); ctx.arc(p.x, p.y, r + 5 * u, -Math.PI / 2, -Math.PI / 2 + Math.max(0.05, f) * 6.283); ctx.stroke(); ctx.setLineDash([])
      if (tier === 'AT_RISK') { ctx.fillStyle = col; ctx.globalAlpha = a * rings; ctx.beginPath(); ctx.arc(p.x, p.y - r - 9 * u, 1.8 * u, 0, 7); ctx.fill() }
    }
    if (p.phase === 'sel' || p.phase === 'tx') { const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 3.2); g.addColorStop(0, hexA(c, 0.55)); g.addColorStop(1, hexA(c, 0)); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, r * 3.2, 0, 7); ctx.fill() }
    glyph(ctx, p.cls, p.x, p.y, r, c)
    if (p.phase === 'drop') { ctx.strokeStyle = pal.bad; ctx.lineWidth = 1.6 * u; ctx.beginPath(); ctx.moveTo(p.x - r, p.y - r); ctx.lineTo(p.x + r, p.y + r); ctx.moveTo(p.x + r, p.y - r); ctx.lineTo(p.x - r, p.y + r); ctx.stroke() }
    ctx.restore(); void hover
  }
}

export function glyph(ctx: CanvasRenderingContext2D, cls: TrafficClass, x: number, y: number, r: number, color: string) {
  ctx.fillStyle = color; ctx.beginPath()
  if (cls === 'emergency') { ctx.moveTo(x, y - r * 1.15); ctx.lineTo(x + r * 1.15, y); ctx.lineTo(x, y + r * 1.15); ctx.lineTo(x - r * 1.15, y); ctx.closePath() }
  else if (cls === 'video') rr(ctx, x - r * 0.95, y - r * 0.95, r * 1.9, r * 1.9, r * 0.55)
  else if (cls === 'gps') { ctx.moveTo(x, y - r * 1.1); ctx.lineTo(x + r * 1.05, y + r * 0.85); ctx.lineTo(x - r * 1.05, y + r * 0.85); ctx.closePath() }
  else ctx.arc(x, y, r, 0, 7)
  ctx.fill()
}
export function rr(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  r = Math.min(r, w / 2, h / 2); ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath()
}
/** Apply alpha to any css colour string we read from tokens (hex, rgb(a)). */
const cache = new Map<string, string>()
export function hexA(c: string, a: number): string {
  const key = c + '|' + a.toFixed(3); const hit = cache.get(key); if (hit) return hit
  let r = 255, g = 255, b = 255, m: RegExpMatchArray | null
  if (c.startsWith('#')) { const h = c.length === 4 ? c.slice(1).split('').map(x => x + x).join('') : c.slice(1, 7); r = parseInt(h.slice(0, 2), 16); g = parseInt(h.slice(2, 4), 16); b = parseInt(h.slice(4, 6), 16) }
  else if ((m = c.match(/rgba?\(([^)]+)\)/))) { const p = m[1].split(/[ ,/]+/).map(Number); r = p[0]; g = p[1]; b = p[2]; if (p[3] != null && !Number.isNaN(p[3])) a *= p[3] }
  const out = `rgba(${r},${g},${b},${clamp(a).toFixed(3)})`
  if (cache.size > 2000) cache.clear()
  cache.set(key, out); return out
}
