import type { SVGProps } from 'react'
import type { TrafficClass } from '../api/types'
const I = (p: SVGProps<SVGSVGElement>) => ({ viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true, ...p })
export const Arrow = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)} className={`arrow ${p.className ?? ''}`}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
export const Play = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)} fill="currentColor" stroke="none"><path d="M8 5.5v13l11-6.5z" /></svg>
export const Pause = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)} fill="currentColor" stroke="none"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
export const Sun = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
export const Moon = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /></svg>
export const Chevron = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><path d="m6 9 6 6 6-6" /></svg>
export const Close = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><path d="M6 6l12 12M18 6 6 18" /></svg>
export const Info = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
export const Warn = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><path d="M12 3 2.5 20h19z" /><path d="M12 10v4M12 17h.01" /></svg>
export const Check = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
export const Cross = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><path d="M6 6l12 12M18 6 6 18" /></svg>
export const Reset = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5" /></svg>
export const Skip = (p: SVGProps<SVGSVGElement>) => <svg {...I(p)}><path d="M5 5l10 7-10 7zM19 5v14" /></svg>

/** Class glyphs: colour + a distinct shape, so class is never conveyed by colour alone. */
export function ClassGlyph({ cls, size = 12 }: { cls: TrafficClass; size?: number }) {
  const c = `var(--c-${cls})`
  const shape = cls === 'emergency' ? <path d="M6 0.8 11.2 6 6 11.2 0.8 6z" fill={c} /> : cls === 'video' ? <rect x="1" y="1" width="10" height="10" rx="3" fill={c} /> : cls === 'gps' ? <path d="M6 1 11.2 10.6H0.8z" fill={c} /> : <circle cx="6" cy="6" r="5" fill={c} />
  return <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden>{shape}</svg>
}
export const Logo = () => (
  <svg viewBox="0 0 24 24" aria-hidden><circle cx="4.5" cy="12" r="2.2" fill="var(--c-normal)" /><circle cx="10.5" cy="12" r="2.2" fill="var(--accent-3)" /><circle cx="17.5" cy="12" r="3.4" fill="var(--accent)" /><path d="M2 20h20" stroke="var(--accent)" strokeOpacity=".5" strokeWidth="1.6" strokeLinecap="round" /></svg>
)
