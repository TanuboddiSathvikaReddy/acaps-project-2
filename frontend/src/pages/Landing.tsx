import { useRef } from 'react'
import { Arrow } from '../components/Icons'
import { Reveal } from '../components/ui'
import { NetworkScene } from '../visuals/NetworkScene'

/** A short, concrete orientation strip — not a story, not a set of cards, just the pipeline in
 * one line so a first-time visitor knows what they're about to do. Kept deliberately thin. */
const FLOW = ['Configure traffic', 'Run simulation', 'Watch packets', 'Compare schedulers']

/**
 * The animated opening page (design brief §2, "FINAL UI POLISH & MINIMALISM PASS"): a cinematic,
 * concise introduction — hero animation, title, one-line description, one CTA — not a long
 * scrolling marketing site. The earlier multi-section story walkthrough, life-cycle illustration,
 * worked example and repeated scheduler/explore card grids have been removed; they duplicated
 * material that the Simulation, Results and Compare pages already present with real backend data.
 */
export function Landing({ go }: { go: (r: string) => void }) {
  const heroRef = useRef(3.4)
  return (
    <>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy container">
          <Reveal className="eyebrow"><span className="dot" />Adaptive Context-Aware Packet Scheduling</Reveal>
          <Reveal d={1}><h1 id="hero-title" className="hero-title grad-text">ACAPS</h1></Reveal>
          <Reveal d={2}><p className="lead">A simulation platform for understanding how adaptive packet scheduling behaves under changing network conditions.</p></Reveal>
          <Reveal d={3} className="hero-cta">
            <button className="btn primary lg" onClick={() => go('simulation')}>Launch Simulation <Arrow /></button>
          </Reveal>
        </div>
        <div className="hero-scene">
          <NetworkScene stepRef={heroRef} autoScan label="Illustration: packets from four traffic classes enter a queue, a scheduler selects one, and it is transmitted over an output link." />
          <span className="badge neutral scene-tag">Illustration · hover to explore</span>
        </div>
        <ol className="flow-strip container" aria-label="How ACAPS works">
          {FLOW.map((f, i) => (
            <Reveal as="li" key={f} d={i + 3} className="flow-step"><span className="n">{String(i + 1).padStart(2, '0')}</span>{f}</Reveal>
          ))}
        </ol>
      </section>
      <footer className="foot container small muted">ACAPS · Adaptive Context-Aware Packet Scheduling · A simulation of one router output port. Results describe the tested configurations only.</footer>
    </>
  )
}
