import { useMemo, useRef, useState, type ReactNode } from 'react'
import type { QueuePoint, SchedulerId } from '../api/types'
import { SCHEDULERS } from '../api/types'
import { hideTip, showTip } from '../components/ui'
import { cssVarSched, SCHED_LABEL } from '../lib/format'

/** Round-number ticks from 0 to max (charts here always start at zero so bar lengths are honest). */
export function niceTicks(max: number, n = 4): number[] {
  if (!(max > 0)) return [0, 1]
  const raw = max / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * mag
  const out: number[] = []; for (let v = 0; v <= max + step * 0.999; v += step) out.push(+v.toFixed(10)); return out
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return <div className="legend" role="list">{items.map(i => <span className="it" role="listitem" key={i.label}><span className="sw" style={{ background: i.color }} />{i.label}</span>)}</div>
}
export const SchedLegend = ({ only }: { only?: SchedulerId[] }) => <Legend items={(only ?? SCHEDULERS).map(s => ({ label: SCHED_LABEL[s], color: cssVarSched(s) }))} />

/* ------------------------------------------------------------------ grouped bars */
export interface BarGroup { key: string; label: ReactNode; values: Partial<Record<SchedulerId, number | null>> }
export function GroupedBars({ groups, unit, digits = 2, height = 280, fmt, active }: { groups: BarGroup[]; unit: string; digits?: number; height?: number; fmt?: (v: number) => string; active?: SchedulerId[] }) {
  const ids = active ?? SCHEDULERS
  const [hov, setHov] = useState<string | null>(null)
  const W = 720, H = height, m = { l: 52, r: 12, t: 22, b: 40 }
  const max = Math.max(0, ...groups.flatMap(g => ids.map(s => g.values[s] ?? 0)))
  const ticks = niceTicks(max), top = ticks[ticks.length - 1] || 1
  const iw = W - m.l - m.r, ih = H - m.t - m.b, gw = iw / groups.length
  const bw = Math.min(34, (gw * 0.72) / ids.length), gap = 2
  const f = (v: number) => (fmt ? fmt(v) : v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }))
  const y = (v: number) => m.t + ih - (v / top) * ih
  return (
    // The chart keeps a minimum physical width and scrolls horizontally on narrow viewports,
    // rather than shrinking its own SVG viewBox — shrinking would make the axis labels and bar
    // values illegible on a phone instead of just requiring a scroll.
    <div className="chart-scroll" tabIndex={0}>
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} style={{ minWidth: Math.min(W, 560) }} role="img" aria-label={`Grouped bar chart in ${unit}`} onPointerLeave={() => { setHov(null); hideTip() }}>
      <g className="grid">{ticks.map(t => <g key={t}><line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} /><text x={m.l - 8} y={y(t) + 4} textAnchor="end">{t.toLocaleString('en-US', { maximumFractionDigits: 3 })}</text></g>)}</g>
      <text x={m.l - 8} y={12} textAnchor="end" style={{ fontWeight: 600 }}>{unit}</text>
      {groups.map((g, gi) => {
        const x0 = m.l + gi * gw + (gw - (bw * ids.length + gap * (ids.length - 1))) / 2
        return (
          <g key={g.key}>
            {ids.map((s, si) => {
              const v = g.values[s]; const x = x0 + si * (bw + gap)
              if (v == null) return <text key={s} x={x + bw / 2} y={y(0) - 6} textAnchor="middle">n/a</text>
              const h = Math.max(v > 0 ? 2 : 0, (v / top) * ih), id = `${g.key}-${s}`
              return (
                <g key={s}>
                  <rect className={`bar ${hov && hov !== id ? 'dim' : ''}`} x={x} y={y(0) - h} width={bw} height={h} rx={4} fill={cssVarSched(s)} style={{ animationDelay: `${si * 60 + gi * 30}ms` }} />
                  {(groups.length <= 4 || v === max) && <text x={x + bw / 2} y={y(0) - h - 6} textAnchor="middle" style={{ fill: 'var(--ink-0)', fontWeight: 600 }}>{f(v)}</text>}
                  <rect x={x - 1} y={m.t} width={bw + 2} height={ih} fill="transparent" tabIndex={0} role="img" aria-label={`${SCHED_LABEL[s]}, ${g.key}: ${f(v)} ${unit}`}
                    onPointerMove={e => { setHov(id); showTip({ title: g.label, rows: [{ k: <><i className="sw" style={{ background: cssVarSched(s), width: 8, height: 8, borderRadius: 2, display: 'inline-block' }} />{SCHED_LABEL[s]}</>, v: `${f(v)} ${unit}` }] }, e.clientX, e.clientY) }}
                    onFocus={e => { const r = e.currentTarget.getBoundingClientRect(); setHov(id); showTip({ title: g.label, rows: [{ k: SCHED_LABEL[s], v: `${f(v)} ${unit}` }] }, r.x + r.width, r.y) }} onBlur={() => { setHov(null); hideTip() }} />
                </g>
              )
            })}
            <text x={m.l + gi * gw + gw / 2} y={H - 14} textAnchor="middle" style={{ fill: 'var(--ink-1)', fontWeight: 600 }}>{g.label}</text>
          </g>
        )
      })}
      <line x1={m.l} x2={W - m.r} y1={y(0)} y2={y(0)} stroke="var(--line-strong)" />
    </svg>
    </div>
  )
}

/* ------------------------------------------------------------------ queue timeline */
export interface Series { id: SchedulerId; points: QueuePoint[] }
export function QueueTimeline({ series, capacity, thresholds, endUs, playheadUs, mode = 'length', height = 260, onSeek }: {
  series: Series[]; capacity: number; thresholds: { medium: number; high: number }; endUs: number; playheadUs?: number; mode?: 'length' | 'occupancy'; height?: number; onSeek?: (us: number) => void
}) {
  const W = 760, H = height, m = { l: 48, r: 14, t: 16, b: 32 }
  const iw = W - m.l - m.r, ih = H - m.t - m.b
  const top = mode === 'length' ? capacity : 1
  const val = (p: QueuePoint) => (mode === 'length' ? p.queueLength : p.occupancy)
  const x = (t: number) => m.l + (t / endUs) * iw, y = (v: number) => m.t + ih - (v / top) * ih
  const ref = useRef<SVGSVGElement>(null)
  // Queue length is a step function (it only changes at discrete arrival/departure/drop events),
  // so the line must hold at each value until the next recorded point ("step-after"), not
  // interpolate a diagonal between them — a diagonal would imply values that were never measured.
  const paths = useMemo(() => series.map(s => {
    let d = '', prevY = 0
    s.points.forEach((p, i) => {
      const px = x(p.timeUs).toFixed(1), py = y(val(p))
      if (i === 0) d += `M${px} ${py.toFixed(1)}`
      else d += `L${px} ${prevY.toFixed(1)}L${px} ${py.toFixed(1)}` // hold at the previous value to this x, then step
      prevY = py
    })
    return { id: s.id, d }
  }), [series, endUs, mode, top]) // eslint-disable-line react-hooks/exhaustive-deps
  const [cur, setCur] = useState<number | null>(null)
  const xt = niceTicks(endUs / 1e6, 5)
  const near = (s: Series, t: number) => { const a = s.points; let lo = 0, hi = a.length - 1; while (lo < hi) { const md = (lo + hi + 1) >> 1; if (a[md].timeUs <= t) lo = md; else hi = md - 1 } return a[lo] }
  const move = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W
    const t = Math.max(0, Math.min(endUs, ((px - m.l) / iw) * endUs)); setCur(t)
    showTip({ title: `t = ${(t / 1e6).toFixed(3)} s`, rows: series.map(s => { const p = near(s, t); return { k: <><i style={{ background: cssVarSched(s.id), width: 8, height: 8, borderRadius: 2, display: 'inline-block' }} />{SCHED_LABEL[s.id]}</>, v: `${p.queueLength} pkts · ${(p.occupancy * 100).toFixed(0)}% · ${p.congestionLevel}` } }) }, e.clientX, e.clientY)
  }
  const yt = mode === 'length' ? niceTicks(capacity, 4) : [0, 0.25, 0.5, 0.75, 1]
  const one = series.length === 1
  return (
    <div className="chart-scroll" tabIndex={0}>
    <svg ref={ref} className="chart" viewBox={`0 0 ${W} ${H}`} style={{ minWidth: Math.min(W, 560), cursor: onSeek ? 'pointer' : 'default' }} role="img" aria-label="Queue over simulation time" onPointerMove={move} onPointerLeave={() => { setCur(null); hideTip() }} onClick={() => cur != null && onSeek?.(cur)}>
      <defs><linearGradient id="qfill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--accent)" stopOpacity=".28" /><stop offset="1" stopColor="var(--accent)" stopOpacity="0" /></linearGradient></defs>
      <g className="grid">{yt.map(t => <g key={t}><line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} /><text x={m.l - 8} y={y(t) + 4} textAnchor="end">{mode === 'length' ? t : `${t * 100}%`}</text></g>)}</g>
      {[thresholds.medium, thresholds.high].map((th, i) => { const v = mode === 'length' ? th * capacity : th; return <g key={i}><line x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} stroke={i ? 'var(--bad)' : 'var(--warn)'} strokeDasharray="4 5" strokeOpacity=".6" /><text x={W - m.r} y={y(v) - 5} textAnchor="end" style={{ fill: i ? 'var(--bad)' : 'var(--warn)' }}>{i ? 'HIGH' : 'MEDIUM'} ≥ {Math.round(th * 100)}%</text></g> })}
      {one && <path d={`${paths[0].d}L${x(series[0].points.at(-1)?.timeUs ?? 0)} ${y(0)}L${x(series[0].points[0]?.timeUs ?? 0)} ${y(0)}Z`} fill="url(#qfill)" />}
      {paths.map(p => <path key={p.id} d={p.d} fill="none" stroke={cssVarSched(p.id)} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />)}
      {xt.map(t => <text key={t} x={x(t * 1e6)} y={H - 10} textAnchor="middle">{t}s</text>)}
      <text x={m.l - 8} y={10} textAnchor="end" style={{ fontWeight: 600 }}>{mode === 'length' ? 'packets' : '% of capacity'}</text>
      {playheadUs != null && <line x1={x(playheadUs)} x2={x(playheadUs)} y1={m.t} y2={m.t + ih} stroke="var(--ink-0)" strokeOpacity=".7" />}
      {cur != null && <><line x1={x(cur)} x2={x(cur)} y1={m.t} y2={m.t + ih} stroke="var(--ink-2)" strokeDasharray="3 3" />{series.map(s => { const p = near(s, cur); return <circle key={s.id} cx={x(cur)} cy={y(val(p))} r={4.5} fill={cssVarSched(s.id)} stroke="var(--bg-1)" strokeWidth={2} /> })}</>}
    </svg>
    </div>
  )
}

/* ------------------------------------------------------------------ mean +/- std, min..max per scheduler */
export interface RangeRow { key: string; label: string; stats: Partial<Record<SchedulerId, { mean: number | null; std: number | null; min: number | null; max: number | null; n: number }>> }
export function RangeChart({ rows, unit, digits = 2, zeroLine }: { rows: RangeRow[]; unit: string; digits?: number; zeroLine?: boolean }) {
  const W = 720, rh = 30 * 3 + 26, H = rows.length * rh + 34, m = { l: 128, r: 20, t: 8 }
  let lo = 0, hi = 0
  rows.forEach(r => SCHEDULERS.forEach(s => { const st = r.stats[s]; if (st?.min != null) lo = Math.min(lo, st.min); if (st?.max != null) hi = Math.max(hi, st.max) }))
  if (hi === lo) hi = lo + 1
  const pad = (hi - lo) * 0.05; lo = lo < 0 ? lo - pad : 0; hi += pad
  const x = (v: number) => m.l + ((v - lo) / (hi - lo)) * (W - m.l - m.r)
  const f = (v: number | null) => (v == null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }))
  const ticks = niceTicks(hi - lo, 5).map(t => t + (lo < 0 ? lo : 0)).filter(t => t <= hi)
  return (
    <div className="chart-scroll" tabIndex={0}>
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} style={{ minWidth: Math.min(W, 560) }} role="img" aria-label={`Mean, standard deviation, minimum and maximum in ${unit}`} onPointerLeave={hideTip}>
      <g className="grid">{ticks.map(t => <g key={t}><line x1={x(t)} x2={x(t)} y1={m.t} y2={H - 26} /><text x={x(t)} y={H - 8} textAnchor="middle">{f(t)}</text></g>)}</g>
      {zeroLine && lo < 0 && <line x1={x(0)} x2={x(0)} y1={m.t} y2={H - 26} stroke="var(--ink-2)" />}
      <text x={W - m.r} y={H - 8} textAnchor="end" style={{ fontWeight: 600 }}>{unit}</text>
      {rows.map((r, ri) => (
        <g key={r.key} transform={`translate(0 ${m.t + ri * rh})`}>
          <text x={0} y={22} style={{ fill: 'var(--ink-0)', fontWeight: 600 }}>{r.label}</text>
          {SCHEDULERS.map((s, si) => {
            const st = r.stats[s]; if (!st || st.mean == null) return null; const cy = 14 + si * 26
            return (
              <g key={s} onPointerMove={e => showTip({ title: `${r.label} · ${SCHED_LABEL[s]}`, rows: [{ k: 'Mean', v: `${f(st.mean)} ${unit}` }, { k: 'Std dev', v: st.std == null ? '—' : `${f(st.std)} ${unit}` }, { k: 'Min', v: `${f(st.min)} ${unit}` }, { k: 'Max', v: `${f(st.max)} ${unit}` }, { k: 'Runs', v: String(st.n) }] }, e.clientX, e.clientY)}>
                <rect x={m.l} y={cy - 12} width={W - m.l - m.r} height={24} fill="transparent" />
                <line x1={x(st.min ?? st.mean)} x2={x(st.max ?? st.mean)} y1={cy} y2={cy} stroke={cssVarSched(s)} strokeOpacity=".4" strokeWidth={2} strokeLinecap="round" />
                {/* mean ± 1 std dev can fall outside the actual min..max range for a skewed metric; clamp the box to
                    the plotted domain so it never extends past the axis the ticks describe. */}
                {st.std != null && <rect x={x(Math.max(lo, st.mean - st.std))} y={cy - 5} width={Math.max(2, x(Math.min(hi, st.mean + st.std)) - x(Math.max(lo, st.mean - st.std)))} height={10} rx={5} fill={cssVarSched(s)} fillOpacity=".45" />}
                <circle cx={x(st.mean)} cy={cy} r={5.5} fill={cssVarSched(s)} stroke="var(--bg-1)" strokeWidth={2} />
              </g>
            )
          })}
        </g>
      ))}
    </svg>
    </div>
  )
}
