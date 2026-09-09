import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, StatGrid, Eyebrow } from '../components/ui'
import ReviewTabs from '../components/ReviewTabs'

// Model-risk register — a card per model the figures rest on (identity, what it may claim, validation, data,
// limitations, governance) and the organisation's own review record, bound to the hash of the card reviewed.
interface Feed { key: string; name: string; status: string | null; last_refresh: string | null }
interface Review { review_id: string; reviewer: string; conclusion: string; conclusion_label: string; comment: string | null; evidence_sha256: string; next_review_by: string | null; reviewed_at: string }
interface CardT { ref: string; kind: 'score' | 'impact'; hazard: string; name: string; algorithm: string; lifecycle: string; active: boolean; tier: string; claim: string; use: string
  r2_oos: number | null; gate: number; fidelity: { family_label: string; symbol: string; value: number | null; band_label: string; published: boolean } | null
  validation: { level?: string; kind?: string; method?: string; detail?: string; skill_grade?: string | null; strength?: string; passed_gate?: boolean | null; at?: string; note?: string; n_years?: number; baseline?: string; challenger?: { verdict: string; method: string } | null } | null
  data: Record<string, unknown> & { feeds?: Feed[] }; limitations: string[]
  governance: { approved_by?: string | null; approved_at?: string | null; activated_by?: string | null; activated_at?: string | null; events: { from: string | null; to: string; actor: string; reason: string | null; at: string }[] }
  controls: string[]; card_sha256: string; review: Review | null; review_state: 'none' | 'stale' | 'overdue' | 'current' }
interface Resp { cards: CardT[]; conclusions: Record<string, string>; note: string; can_review: boolean
  summary: { models: number; in_use: number; calibrated: number; screening: number; unvalidated: number; reviewed_current: number; review_stale: number; review_overdue: number; unreviewed: number } }
const TIER: Record<string, string> = { calibrated: 'var(--color-good)', ranged: 'var(--color-good)', backtested: 'var(--color-good)', screening: 'var(--color-warn)', indicative: 'var(--color-warn)', candidate: 'var(--color-faint)' }
const RS: Record<CardT['review_state'], { label: string; color: string }> = { none: { label: 'not reviewed', color: 'var(--color-faint)' }, stale: { label: 'review stale (card changed)', color: 'var(--color-warn)' }, overdue: { label: 'review overdue', color: 'var(--color-bad)' }, current: { label: 'reviewed', color: 'var(--color-good)' } }
const dt = (s: string | null | undefined) => s ? s.slice(0, 16).replace('T', ' ') : '—'
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'

export default function ModelRisk() {
  const q = useQuery({ queryKey: ['model-risk'], queryFn: () => api.get<Resp>('/v1/model-risk') })
  const [open, setOpen] = useState<string | null>(null); const [review, setReview] = useState<CardT | null>(null); const [inUse, setInUse] = useState(true)
  const d = q.data
  const s = d?.summary
  const rows = (d?.cards ?? []).filter(c => !inUse || c.active)
  return (
    <div className="fadeup space-y-6">
      <ReviewTabs />
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Eyebrow>Assess · model-risk register</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-2">What do the figures rest on?</h1>
          <p className="text-[15px] leading-relaxed text-[var(--color-mute)] max-w-2xl">A card for every model behind a score or a euro figure: what it may claim, how it was validated, the data behind it, its limits and its governance. Your own review is recorded by name and bound to the card you saw; when the card changes, the review goes stale.</p>
        </div>
        <Button variant="ghost" onClick={() => download('/v1/model-risk/register.csv', 'model-risk-register.csv')}>Export register (CSV)</Button>
      </div>
      {s && <StatGrid cols={4} items={[
        { label: 'Models in use', value: String(s.in_use), sub: `${s.models} in the register incl. candidates` },
        { label: 'Calibrated / screening', value: `${s.calibrated} / ${s.screening}`, sub: 'may publish a euro figure / signal only', accent: s.screening ? 'var(--color-warn)' : 'var(--color-good)' },
        { label: 'Without validation evidence', value: String(s.unvalidated), sub: 'no run on the ledger at model or hazard level', accent: s.unvalidated ? 'var(--color-warn)' : undefined },
        { label: 'Reviewed and current', value: `${s.reviewed_current} / ${s.in_use}`, sub: `${s.review_stale} stale · ${s.review_overdue} overdue · ${s.unreviewed} not reviewed`, accent: s.unreviewed || s.review_stale || s.review_overdue ? 'var(--color-warn)' : 'var(--color-good)' },
      ]} />}
      <Card className="p-5">
        <div className="flex items-center gap-3 mb-3 text-[12px]">
          <label className="flex items-center gap-2 text-[var(--color-mute)]"><input type="checkbox" checked={inUse} onChange={e => setInUse(e.target.checked)} /> in use only</label>
          <span className="text-[var(--color-faint)]">{d?.note}</span>
        </div>
        {q.isLoading ? <div className="text-[12.5px] text-[var(--color-faint)] py-6 text-center">assembling the model cards…</div> : (
          <div className="overflow-x-auto"><table className="data-table text-[12px]">
            <thead><tr><th>Model</th><th>Hazard</th><th>Tier</th><th>What it may claim</th><th className="num">OOS r²</th><th>Fidelity</th><th>Validation</th><th>Review</th><th></th></tr></thead>
            <tbody>{rows.map(c => (<>
              <tr key={c.ref}>
                <td><span className="text-[var(--color-ink)]">{c.name}</span><div className="mono text-[10px] text-[var(--color-faint)]">{c.kind === 'score' ? 'score' : 'impact'} · {c.lifecycle}{c.active ? '' : ' · not in use'}</div></td>
                <td>{c.hazard}</td>
                <td><span className="font-medium" style={{ color: TIER[c.tier] ?? 'var(--color-mute)' }}>{c.tier}</span></td>
                <td className="max-w-[260px] text-[var(--color-mute)]">{c.claim}</td>
                <td className="num mono">{c.r2_oos != null ? c.r2_oos.toFixed(2) : '—'}<span className="text-[10px] text-[var(--color-faint)]"> / {c.gate.toFixed(2)}</span></td>
                <td>{c.fidelity ? `${c.fidelity.symbol} ${c.fidelity.value ?? '—'} · ${c.fidelity.band_label}` : <span className="text-[var(--color-faint)]">not testable</span>}</td>
                <td className="max-w-[220px]">{c.validation ? <span>{c.validation.method ?? c.validation.kind}{c.validation.skill_grade ? ` · ${c.validation.skill_grade}` : c.validation.strength ? ` · ${c.validation.strength}` : ''}{c.validation.level === 'hazard' ? <span className="text-[var(--color-faint)]"> · hazard level</span> : ''}</span> : <span className="text-[var(--color-warn)]">none on record</span>}</td>
                <td><span style={{ color: RS[c.review_state].color }}>{RS[c.review_state].label}</span>{c.review && <div className="mono text-[10px] text-[var(--color-faint)]">{c.review.reviewer} · {c.review.reviewed_at.slice(0, 10)}{c.review.next_review_by ? ` · next ${c.review.next_review_by}` : ''}</div>}</td>
                <td className="whitespace-nowrap"><button onClick={() => setOpen(open === c.ref ? null : c.ref)} className="text-[var(--color-sky)] hover:underline">{open === c.ref ? 'Hide' : 'Card'}</button>
                  {' · '}<button onClick={() => download(`/v1/model-risk/card.pdf?ref=${encodeURIComponent(c.ref)}`, `model-card-${c.hazard}.pdf`)} className="text-[var(--color-sky)] hover:underline">PDF</button>
                  {d?.can_review && <>{' · '}<button onClick={() => setReview(c)} className="text-[var(--color-sky)] hover:underline font-medium">Review</button></>}</td>
              </tr>
              {open === c.ref && <tr key={c.ref + '-d'}><td colSpan={9} className="bg-[var(--color-panel-2)]"><CardDetail c={c} /></td></tr>}
            </>))}</tbody>
          </table></div>)}
      </Card>
      {review && d && <ReviewDialog c={review} conclusions={d.conclusions} onClose={() => setReview(null)} />}
    </div>
  )
}

function CardDetail({ c }: { c: CardT }) {
  const g = c.governance; const v = c.validation
  return (
    <div className="grid grid-cols-[140px_1fr] gap-y-1 text-[12px] py-1">
      <span className="text-[var(--color-faint)]">Used for</span><span className="text-[var(--color-ink)]">{c.use}</span>
      <span className="text-[var(--color-faint)]">Algorithm</span><span>{c.algorithm}</span>
      <span className="text-[var(--color-faint)]">Validation</span><span>{v ? <>{v.note ? <span className="text-[var(--color-faint)]">{v.note} </span> : null}{v.method ?? v.kind}{v.detail ? ` · ${v.detail}` : ''}{v.n_years ? ` · ${v.n_years} years · baseline ${v.baseline}` : ''}{v.passed_gate != null ? (v.passed_gate ? ' · passed the gate' : ' · did not pass the gate') : ''}{v.at ? ` · ${v.at.slice(0, 10)}` : ''}{v.challenger ? ` · challenger ${v.challenger.method}: ${v.challenger.verdict}` : ''}</> : 'No validation run on record.'}</span>
      <span className="text-[var(--color-faint)]">Data</span><span>{Object.entries(c.data).filter(([k]) => k !== 'feeds').map(([k, val]) => `${k.replace('_', ' ')}: ${val ?? '—'}`).join(' · ')}{c.data.feeds?.length ? <> · feeds: {c.data.feeds.map(f => `${f.name} (${f.status ?? '—'})`).join(', ')}</> : null}</span>
      <span className="text-[var(--color-faint)]">Limitations</span><span>{c.limitations.length ? <ul className="m-0 pl-4">{c.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul> : 'None recorded.'}</span>
      <span className="text-[var(--color-faint)]">Governance</span><span>approved {g.approved_by ?? '—'} {g.approved_at ? dt(g.approved_at) : ''} · activated {g.activated_by ?? '—'} {g.activated_at ? dt(g.activated_at) : ''} · controls {c.controls.join(', ')}</span>
      {g.events.length > 0 && <><span className="text-[var(--color-faint)]">Lifecycle</span><span>{g.events.map((e, i) => <div key={i} className="mono text-[11px]">{dt(e.at)} · {e.from ?? '—'} → {e.to} · {e.actor}{e.reason ? ` · ${e.reason}` : ''}</div>)}</span></>}
      <span className="text-[var(--color-faint)]">Card hash</span><span className="mono text-[11px] text-[var(--color-faint)]">{c.card_sha256}</span>
    </div>
  )
}

function ReviewDialog({ c, conclusions, onClose }: { c: CardT; conclusions: Record<string, string>; onClose: () => void }) {
  const qc = useQueryClient()
  const [conclusion, setConclusion] = useState('fit_for_use'); const [comment, setComment] = useState(''); const [next, setNext] = useState(''); const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try { await api.post('/v1/model-risk/review', { ref: c.ref, conclusion, comment: comment || null, next_review_by: next || null }); toast.success(`Review recorded for ${c.name}.`); await qc.invalidateQueries({ queryKey: ['model-risk'] }); onClose() }
    catch (e) { toast.error((e as Error).message || 'Could not record the review.') } finally { setBusy(false) }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-[520px] rounded-xl border border-[var(--color-line)] bg-[var(--color-bg)] p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-blue)] mb-1">Independent review · {c.hazard}</div>
        <h2 className="display text-lg font-semibold m-0 text-[var(--color-ink)]">{c.name}</h2>
        <p className="text-[12.5px] text-[var(--color-mute)] mt-1 mb-4">Your conclusion is recorded by name and bound to card hash <span className="mono text-[11px]">{c.card_sha256.slice(0, 16)}…</span>. If the card changes later, this review shows as stale.</p>
        <div className="space-y-3">
          <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Conclusion<select value={conclusion} onChange={e => setConclusion(e.target.value)} className={inp + ' mt-1'}>{Object.entries(conclusions).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Comment{conclusion !== 'fit_for_use' ? ' (required)' : ''}<textarea value={comment} onChange={e => setComment(e.target.value)} rows={3} className={inp + ' mt-1'} /></label>
          <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Next review by<input type="date" value={next} onChange={e => setNext(e.target.value)} className={inp + ' mt-1'} /></label>
          <div className="flex justify-end gap-2 pt-1"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={submit} disabled={busy || (conclusion !== 'fit_for_use' && !comment)}>{busy ? 'Recording…' : 'Record review'}</Button></div>
        </div>
      </div>
    </div>
  )
}
