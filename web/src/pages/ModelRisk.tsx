import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Download } from 'lucide-react'
import { api, download } from '../lib/api'
import { pressable } from '../lib/pressable'
import { Button, Card, PageHeader, SectionHead, StatGrid } from '../components/ui'
import { HBar } from '../components/Charts'
import { StatusChip } from '../components/StatusChip'
import { HEADING, messageDetails } from '../components/Details'
import ReviewTabs from '../components/ReviewTabs'
import { FidelityBar, ModelCard, ReviewDialog } from './modelrisk/ModelCard'
import { REVIEW, STANDING_TONE, type Card as ModelCardT, type Register, type ReviewState } from './modelrisk/model'

// The model-risk register, to the UI standard (2026-10-16): a card for every model behind a score or a euro figure,
// shown as a register of chips and bars — its standing, its latest test against its bar, and the organisation's own
// review. Each card opens with what it may claim, how it was tested, its data, its governance and the review
// (modelrisk/ModelCard.tsx). The server sends facts, names and catalogue messages (services/governance/model_risk.py).

const ABOUT = [
  { heading: HEADING.shows, body: 'A card for every model behind a score or a euro figure: what it may claim, how it was tested, the data behind it and its governance — and your organisation’s own review of it, recorded by name.' },
  { heading: HEADING.read, body: 'The standing is what a hazard’s scores may claim on the hazard register: a validated hazard may lead a headline and carry a figure, an indicator only screens. The bar shows the latest test against the level it must clear (the tick). A review stays current until the card’s facts change or its next-review date passes.' },
  { heading: HEADING.sources, body: 'The model registry, the validation record, the hazard register, the data feeds behind each hazard and, for crop impact, the fits of past harvests.' },
]
const STATE_COLOR: Record<ReviewState, string> = { current: 'var(--color-good)', stale: 'var(--color-warn)', overdue: 'var(--color-bad)', none: 'var(--color-slate)' }

export default function ModelRisk() {
  const q = useQuery({ queryKey: ['model-risk'], queryFn: () => api.get<Register>('/v1/model-risk') })
  const [open, setOpen] = useState<string | null>(null)
  const [review, setReview] = useState<ModelCardT | null>(null)
  const [inUse, setInUse] = useState(true)
  const [stateFilter, setStateFilter] = useState<ReviewState | null>(null)
  const d = q.data
  const s = d?.summary
  const rows = (d?.cards ?? []).filter(c => (!inUse || c.active) && (!stateFilter || c.review_state === stateFilter))
  const card = d?.cards.find(c => c.ref === open) ?? null
  const about = d ? [...ABOUT, ...messageDetails(d.about).sections.map(x => ({ heading: x.heading === 'Why' ? 'Reviews' : HEADING.limits, body: x.body }))] : ABOUT
  return (
    <div className="fadeup space-y-6">
      <ReviewTabs />
      <PageHeader eyebrow="Assess · Model risk" title="What do the figures rest on?" about={about}
        lead="A card for each model behind a score or a figure."
        actions={<Button variant="ghost" onClick={() => download('/v1/model-risk/register.csv', 'model-risk-register.csv')}><Download size={14} /> Register (CSV)</Button>} />
      {q.isError ? <div className="text-[12.5px] text-[var(--color-warn)]">The register could not be loaded. Try again shortly.</div>
        : !d || !s ? <div className="text-[12.5px] text-[var(--color-faint)] py-6 text-center">Assembling the model cards…</div> : (<>
          <StatGrid cols={4} items={[
            { label: 'Models in use', value: s.in_use, sub: `of ${s.models} registered` },
            { label: 'May carry a figure', value: `${s.carries_figure} of ${s.in_use}`, sub: 'the others screen only', accent: s.screens_only ? 'var(--color-warn)' : 'var(--color-good)' },
            { label: 'Without a test', value: s.unvalidated, sub: 'no test of the model or its hazard', accent: s.unvalidated ? 'var(--color-warn)' : undefined },
            { label: 'Reviews current', value: `${s.reviewed_current} of ${s.in_use}`, accent: s.reviewed_current < s.in_use ? 'var(--color-warn)' : 'var(--color-good)' },
          ]} />
          <Overview d={d} stateFilter={stateFilter} setStateFilter={setStateFilter} />
          <Card className="p-0 overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--color-line)] flex-wrap text-[12.5px]">
              <SectionHead>Register</SectionHead>
              <label className="flex items-center gap-2 text-[var(--color-mute)]"><input type="checkbox" checked={inUse} onChange={e => setInUse(e.target.checked)} /> In use only</label>
              {stateFilter && (
                <button onClick={() => setStateFilter(null)} className="inline-flex items-center gap-1.5 text-[var(--color-mute)] hover:text-[var(--color-ink)]">
                  <StatusChip label={REVIEW[stateFilter].label} tone={REVIEW[stateFilter].tone} /> <span className="text-[var(--color-sky)]">Show all</span>
                </button>
              )}
              <span className="ml-auto text-[var(--color-faint)] tabular-nums">{rows.length} shown</span>
            </div>
            <div className="overflow-x-auto">
              <table className="data-table text-[12.5px] w-full">
                <thead><tr><th>Model</th><th>Hazard standing</th><th>Latest test</th><th>Review</th><th></th></tr></thead>
                <tbody>{rows.map(c => (
                  <tr key={c.ref} {...pressable(() => setOpen(c.ref), { row: true })} className="cursor-pointer hover:bg-[var(--color-panel)]">
                    <td>
                      <div className="text-[var(--color-ink)]">{c.name}</div>
                      <div className="text-[11.5px] text-[var(--color-faint)]">{c.kind_name}{c.lifecycle_name ? ` · ${c.lifecycle_name}` : ''}</div>
                    </td>
                    <td>{c.standing && c.standing_name ? <StatusChip label={c.standing_name} tone={STANDING_TONE[c.standing]} /> : <span className="text-[var(--color-faint)]">—</span>}</td>
                    <td className="min-w-[150px]">{c.validation ? <FidelityBar c={c} compact /> : <StatusChip label={c.evidence.label} tone="warn" />}</td>
                    <td><StatusChip label={REVIEW[c.review_state].label} tone={REVIEW[c.review_state].tone} /></td>
                    <td className="text-right"><ChevronRight size={14} className="text-[var(--color-faint)] inline" /></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </Card>
        </>)}
      {card && d && <ModelCard c={card} canReview={d.can_review} onReview={() => setReview(card)} onClose={() => setOpen(null)} />}
      {review && d && <ReviewDialog c={review} conclusions={d.conclusions} onClose={() => setReview(null)} />}
    </div>
  )
}

// the models in use at a glance: what their hazards may claim, and where their reviews stand (a bar filters the register)
function Overview({ d, stateFilter, setStateFilter }: { d: Register; stateFilter: ReviewState | null; setStateFilter: (s: ReviewState | null) => void }) {
  const s = d.summary
  const active = d.cards.filter(c => c.active)
  const standing = [...active.reduce((m, c) => {
    const k = c.standing_name ?? 'No standing'
    const tone = c.standing ? STANDING_TONE[c.standing] : 'neutral'
    m.set(k, { n: (m.get(k)?.n ?? 0) + 1, tone })
    return m
  }, new Map<string, { n: number; tone: 'good' | 'warn' | 'neutral' }>()).entries()].sort((a, b) => b[1].n - a[1].n)
  const TONE = { good: 'var(--color-good)', warn: 'var(--color-warn)', neutral: 'var(--color-slate)' }
  const states = ([['current', s.reviewed_current], ['stale', s.review_stale], ['overdue', s.review_overdue], ['none', s.unreviewed]] as [ReviewState, number][]).filter(([, n]) => n > 0)
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-5">
        <SectionHead className="mb-3">Standing of the models in use</SectionHead>
        <div className="flex h-3 rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label={standing.map(([k, v]) => `${k} ${v.n}`).join(', ')}>
          {standing.map(([k, v]) => <span key={k} style={{ width: `${100 * v.n / Math.max(1, active.length)}%`, background: TONE[v.tone], opacity: 0.85 }} />)}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[12.5px]">
          {standing.map(([k, v]) => <span key={k} className="inline-flex items-center gap-1.5 text-[var(--color-mute)]"><span className="w-2 h-2 rounded-full" style={{ background: TONE[v.tone] }} />{k} <b className="text-[var(--color-ink)] tabular-nums">{v.n}</b></span>)}
        </div>
      </Card>
      <Card className="p-5">
        <SectionHead className="mb-3">Reviews of the models in use</SectionHead>
        <HBar height={16} format={n => `${n}`} labelWidth="w-28"
          data={states.map(([st, n]) => ({ label: REVIEW[st].label, value: n, color: STATE_COLOR[st] }))}
          onBar={i => setStateFilter(stateFilter === states[i][0] ? null : states[i][0])} />
      </Card>
    </div>
  )
}
