import { Drawer } from '../../components/Drawer'
import { CloseButton } from '../../components/Dialog'
import type { SF } from './types'

// How the two figures are made and on what legal basis — the explanation the main screen leaves out (UI standard).
const STEPS = [
  { t: 'Each region’s loss', b: 'For each peril and region, the sum insured in each zone is multiplied by the region’s factor and the zone’s risk weight, then combined with the zone correlations. Where postal codes are missing, the region’s zones are grouped at their highest risk weight (Article 90b): an upper bound.' },
  { t: 'After reinsurance', b: 'The Regulation’s events for the region are applied to that loss, each one net of your attested treaty: the quota share first, then the excess of loss per event, with reinstatements only where you state them and their premium (Article 126). Where the Regulation sets two scenarios, the larger is the region’s charge.' },
  { t: 'Each peril', b: 'The regions are combined with the correlations of the Annexes. Risks in other countries are charged on the premiums you state for them.' },
  { t: 'Natural catastrophe', b: 'The five perils are combined as the square root of the sum of their squares (Article 120).' },
]

export default function Methods({ sf, onClose }: { sf?: SF; onClose: () => void }) {
  const h = (t: string) => <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] mt-6 mb-2">{t}</h4>
  const p = (body: React.ReactNode) => <p className="m-0 text-[13px] leading-relaxed text-[var(--color-ink)]">{body}</p>
  return (
    <Drawer label="Methods and legal basis" onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-center justify-between"><div className="text-[16px] font-semibold text-[var(--color-ink)]">Methods and legal basis</div><CloseButton onClick={onClose} /></div>
      {h('Legal basis')}
      <div className="space-y-2">
        {p('Delegated Regulation (EU) 2015/35, Articles 90b and 119 to 126, with Annexes III, V to X, XIII and XXII to XXVI. Reported on template S.27.01.01 of Implementing Regulation (EU) 2023/894.')}
        {sf?.version_name && p(<>In force on your reporting date{sf.reference_date ? ` (${new Date(sf.reference_date).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })})` : ''}: {sf.version_name}.</>)}
        {sf?.version_source && <p className="m-0 text-[12px] text-[var(--color-mute)]">Tables checked against the consolidated text {sf.version_source}.</p>}
      </div>
      {h('How the standard formula is worked out')}
      <ol className="space-y-3 m-0 p-0 list-none">
        {STEPS.map((x, i) => (
          <li key={x.t} className="flex gap-3">
            <span className="w-6 h-6 shrink-0 rounded-full grid place-items-center text-[11px] font-semibold bg-[var(--color-panel-2)] text-[var(--color-sky)]">{i + 1}</span>
            <div><div className="text-[13px] font-semibold text-[var(--color-ink)]">{x.t}</div><div className="text-[13px] text-[var(--color-mute)] leading-relaxed">{x.b}</div></div>
          </li>
        ))}
      </ol>
      {!!sf?.readings?.length && <>
        {h('Where the text leaves a point open')}
        <div className="space-y-3">
          {sf.readings.map(r => (
            <div key={r.subject}>
              <div className="text-[13px] font-semibold text-[var(--color-ink)]">{r.subject}</div>
              <div className="text-[13px] text-[var(--color-mute)] leading-relaxed">{r.reading}</div>
            </div>
          ))}
        </div>
      </>}
      {h('Modelled 1-in-200 loss')}
      {p('Our catastrophe simulation of your book on the damage ratios and event probabilities your organisation states: the loss of the worst year in 200 (99.5 %), before and after your attested treaty. It covers every climate hazard your book is scored on. It is context for the standard formula, not an approved internal model (Directive 2009/138/EC, Article 112).')}
      {h('Out of scope')}
      {p('Man-made catastrophe, non-proportional property reinsurance and health catastrophe risk are other parts of S.27.01.01, outside climate scope.')}
    </Drawer>
  )
}
