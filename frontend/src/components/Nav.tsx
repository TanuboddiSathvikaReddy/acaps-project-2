import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useApp } from '../state/store'
import { Logo, Moon, Sun } from './Icons'

export const ROUTES = [
  { id: 'home', label: 'ACAPS' },
  { id: 'simulation', label: 'Simulation' },
  { id: 'results', label: 'Results' },
  { id: 'compare', label: 'Compare' },
] as const

export function Nav({ route, go }: { route: string; go: (r: string) => void }) {
  const { s, toggleTheme } = useApp()
  const links = useRef<HTMLDivElement>(null)
  const [pill, setPill] = useState<{ x: number; w: number } | null>(null)
  const [hide, setHide] = useState(false)
  useLayoutEffect(() => {
    const m = () => { const el = links.current?.querySelector<HTMLElement>('[aria-current="page"]'); setPill(el ? { x: el.offsetLeft, w: el.offsetWidth } : null) }
    m(); const ro = new ResizeObserver(m); if (links.current) ro.observe(links.current); return () => ro.disconnect()
  }, [route])
  useEffect(() => {
    let lastY = window.scrollY
    const on = () => { const y = window.scrollY; setHide(y > lastY + 4 && y > 420 ? true : y < lastY - 4 ? false : hide); lastY = y }
    window.addEventListener('scroll', on, { passive: true }); return () => window.removeEventListener('scroll', on)
  }, [hide])
  return (
    <nav className={`nav ${hide ? 'hide' : ''}`} aria-label="Primary">
      <a className="brand" href="#/" onClick={e => { e.preventDefault(); go('home') }} aria-label="ACAPS home"><i><Logo /></i><span>ACAPS</span></a>
      <div className="nav-links" ref={links}>
        {pill && <span className="nav-pill" style={{ transform: `translateX(${pill.x}px)`, width: pill.w }} />}
        {ROUTES.filter(r => r.id !== 'home').map(r => (
          <a key={r.id} href={`#/${r.id}`} className={'opt' in r && r.opt ? 'opt' : ''} aria-current={route === r.id ? 'page' : undefined} onClick={e => { e.preventDefault(); go(r.id) }}>{r.label}</a>
        ))}
      </div>
      <span className="sep" />
      <button className="icon-btn" onClick={toggleTheme} aria-label={`Switch to ${s.theme === 'dark' ? 'light' : 'dark'} theme`}>{s.theme === 'dark' ? <Sun /> : <Moon />}</button>
    </nav>
  )
}
