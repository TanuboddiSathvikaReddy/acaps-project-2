import type { TrafficClass } from '../api/types'
import { TRAFFIC_CLASSES } from '../api/types'

/** Input constraint only: keep four integer percentages summing to exactly 100 while one is dragged. */
export function setMixShare(mix: Record<TrafficClass, number>, cls: TrafficClass, value: number): Record<TrafficClass, number> {
  const v = Math.max(0, Math.min(100, Math.round(value)))
  const others = TRAFFIC_CLASSES.filter(c => c !== cls)
  const rest = 100 - v
  const otherSum = others.reduce((s, c) => s + mix[c], 0)
  const next = { ...mix, [cls]: v } as Record<TrafficClass, number>
  if (otherSum === 0) {
    const base = Math.floor(rest / others.length)
    others.forEach((c, i) => (next[c] = base + (i < rest - base * others.length ? 1 : 0)))
    return next
  }
  let assigned = 0
  const raw = others.map(c => ({ c, x: (mix[c] / otherSum) * rest }))
  raw.forEach(r => { next[r.c] = Math.floor(r.x); assigned += next[r.c] })
  let left = rest - assigned
  raw.sort((a, b) => (b.x - Math.floor(b.x)) - (a.x - Math.floor(a.x)))
  for (const r of raw) { if (left <= 0) break; next[r.c] += 1; left-- }
  return next
}
export const mixToFractions = (m: Record<TrafficClass, number>) =>
  Object.fromEntries(TRAFFIC_CLASSES.map(c => [c, m[c] / 100])) as Record<TrafficClass, number>
export const mixFromFractions = (m: Record<TrafficClass, number>) => {
  const raw = TRAFFIC_CLASSES.map(c => ({ c, x: m[c] * 100 }))
  const out = {} as Record<TrafficClass, number>
  let sum = 0
  raw.forEach(r => { out[r.c] = Math.floor(r.x); sum += out[r.c] })
  raw.sort((a, b) => (b.x - Math.floor(b.x)) - (a.x - Math.floor(a.x)))
  for (let i = 0; sum < 100 && i < raw.length; i++, sum++) out[raw[i].c] += 1
  return out
}
