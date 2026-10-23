import { useState } from 'react'
import { SCHEDULERS } from '../api/types'
import type { RunView } from '../adapters/run'
import { SCHED_LABEL, cssVarSched, packetAlias } from '../lib/format'
import { ClassGlyph } from './Icons'

const PAGE = 10

/**
 * The central idea of the project (design brief §4C): the same immutable workload, replayed by
 * all three schedulers, picks packets in a different order. Real backend decisions only — each
 * column is that scheduler's own, already-recorded `decisions` list. Starts at 10 selections per
 * scheduler; "Show next 10" actually reveals more (not a static "+N more" label), up to the full,
 * real selection order — never hundreds of rows at once. The packet alias (e.g. VIDEO-377) already
 * names the class, so it isn't repeated as a separate label next to it.
 */
export function SchedulerOrder({ view }: { view: RunView }) {
  const total = view.schedulers.ACAPS.decisions.length
  const [shown, setShown] = useState(PAGE)
  const n = Math.min(shown, total)
  return (
    <div className="glass pad" aria-label="Packet selection order by scheduler">
      <div className="row spread" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 10 }}>
        <div className="row" style={{ gap: 10 }}>
          <span className="eyebrow">Three scheduler orders</span>
          <span className="badge accent" title={`Workload fingerprint ${view.raw.workload.fingerprint}`}>SAME WORKLOAD</span>
        </div>
        <span className="small muted">First {n} selections per scheduler, in order</span>
      </div>
      <div className="sched-order-grid">
        {SCHEDULERS.map(s => {
          const decisions = view.schedulers[s].decisions
          return (
            <div key={s}>
              <div className="row" style={{ gap: 8, marginBottom: 8 }}>
                <i style={{ background: cssVarSched(s), width: 10, height: 10, borderRadius: 3, display: 'inline-block' }} />
                <b>{SCHED_LABEL[s]}</b>
              </div>
              <ol style={{ display: 'grid', gap: 6, listStyle: 'none', margin: 0, padding: 0 }}>
                {decisions.slice(0, n).map((d, i) => (
                  <li key={d.timeUs} className="row" style={{ gap: 8, fontSize: '.85em' }}>
                    <span className="mono muted" style={{ width: 22, textAlign: 'right' }}>{i + 1}</span>
                    <ClassGlyph cls={d.chosenClass} size={11} />
                    <span className="mono">{packetAlias(d.chosenClass, d.chosenPacketId)}</span>
                  </li>
                ))}
              </ol>
            </div>
          )
        })}
      </div>
      {n < total && (
        <div className="row" style={{ justifyContent: 'center', marginTop: 14 }}>
          <button className="btn ghost sm" onClick={() => setShown(v => v + PAGE)}>Show next {Math.min(PAGE, total - n)}</button>
        </div>
      )}
    </div>
  )
}
