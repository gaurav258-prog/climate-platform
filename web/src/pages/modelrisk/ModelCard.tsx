import { useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { FileDown, ShieldCheck } from 'lucide-react'
import { api, apiMessage, download } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useResizableWidth } from '../../lib/resizable'
import { Button } from '../../components/ui'
import { Dialog, CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { StatusChip } from '../../components/StatusChip'
import { DetailsBody, InfoButton, MessageLine } from '../../components/Details'
import { FEED_TONE, FEED_WORD, REVIEW, STANDING_TONE, day, type Card } from './model'

// One model card, to the UI standard (2026-10-16): what the model may claim, how it was tested, what its score
// measures, the data and governance behind it, and the organisation's review — in the catalogue's words. Its
// references (the model's identifier, the card's fingerprint) sit at the foot, for an auditor to quote.

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-2">{title}</h4>
      {children}
    </section>
  )
}
function Row({ k, children }: { k: string; children: ReactNode }) {
  return <div className="contents"><dt className="text-[var(--color-mute)]">{k}</dt><dd className="m-0 text-[var(--color-ink)]">{children}</dd></div>
}

// a test result against the bar it must clear: the value on 0–100, the bar marked, the band in words
export function FidelityBar({ c, compact }: { c: Card; compact?: boolean }) {
  const f = c.fidelity
  if (!f || f.value == null) return <span className="text-[12px] text-[var(--color-faint)]">Not testable</span>
  const color = f.published ? 'var(--color-good)' : 'var(--color-warn)'
  return (
    <div className={compact ? 'min-w-[120px]' : ''}>
      <div className="flex items-baseline justify-between gap-2 text-[12px]">
        <span style={{ color }}>{f.band_label}</span>
        <span className="tabular-nums text-[var(--color-mute)]">{Math.round(f.value)} / 100</span>
      </div>
      <div className="relative mt-1 h-1.5 rounded-full bg-[var(--color-panel-2)]" role="img" aria-label={`${f.family_label} ${Math.round(f.value)} of 100, bar ${f.floor}`}>
        <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(2, f.value)}%`, background: color, opacity: 0.8 }} />
        <span className="absolute -top-0.5 w-px h-2.5 bg-[var(--color-ink)]" style={{ left: `${f.floor}%` }} />
      </div>
    </div>
  )
}

export function ModelCard({ c, canReview, onReview, onClose }: { c: Card; canReview: boolean; onReview: () => void; onClose: () => void }) {
  const { width, setWidth, startResize } = useResizableWidth('tellumen.drawerw', 520, 380, 900, 'right')
  const v = c.validation
  const n = c.validation_names
  const g = c.governance
  const rv = REVIEW[c.review_state]
  return (
    <Drawer label={c.name} onClose={onClose} style={{ width, maxWidth: '96vw' }} resize={{ start: startResize, reset: () => setWidth(520) }}
      className="w-full h-full bg-[var(--color-bg-2)] border-l border-[var(--color-line)] overflow-y-auto">
      <div className="sticky top-0 z-10 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[12px] text-[var(--color-mute)]">{c.kind_name}{c.lifecycle_name ? ` · ${c.lifecycle_name}` : ''}</div>
          <h3 className="display text-[20px] font-semibold text-[var(--color-ink)] m-0 mt-1">{c.name}</h3>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {c.standing && c.standing_name && <StatusChip label={c.standing_name} tone={STANDING_TONE[c.standing]} />}
            <StatusChip label={rv.label} tone={rv.tone} />
          </div>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="p-5 space-y-6 text-[13px]">
        <Section title="What it may claim">
          <div className="font-medium text-[var(--color-ink)]">{c.claim.label}</div>
          {c.claim.detail?.what && <p className="m-0 mt-1 text-[12.5px] leading-relaxed text-[var(--color-mute)]">{c.claim.detail.what}</p>}
        </Section>
        <Section title="How it was tested">
          <div className="space-y-3">
            <div className="text-[var(--color-mute)]"><MessageLine m={c.evidence} /></div>
            {v && (
              <>
                <FidelityBar c={c} />
                <dl className="grid grid-cols-[150px_1fr] gap-x-3 gap-y-1.5 text-[12.5px] m-0">
                  {n?.design && <Row k="Design">{n.design}</Row>}
                  {n?.skill && <Row k="Skill">{n.skill}</Row>}
                  {v.passed_gate != null && <Row k="Its bar">{v.passed_gate ? 'Passed' : 'Not passed'}</Row>}
                  {v.record && <Row k="Observed record">{v.record}</Row>}
                  {v.n_samples != null && <Row k="Places compared"><span className="tabular-nums">{v.n_samples.toLocaleString()}</span></Row>}
                  {v.n_years != null && <Row k="Years of harvests"><span className="tabular-nums">{v.n_years}{v.baseline?.[0] ? ` (${v.baseline[0]}–${v.baseline[1]})` : ''}</span></Row>}
                  {v.challenger && <Row k="Second method">{n?.verdict ?? '—'}</Row>}
                  {v.at && <Row k="Tested">{day(v.at)}</Row>}
                </dl>
              </>
            )}
          </div>
        </Section>
        {c.basis && (
          <Section title="What the score measures">
            <DetailsBody sections={[
              { heading: 'Source', body: c.basis.label },
              ...(c.basis.detail?.what ? [{ heading: 'What it measures', body: c.basis.detail.what }] : []),
              ...(c.basis.detail?.why ? [{ heading: 'How it was checked', body: c.basis.detail.why }] : []),
            ]} />
          </Section>
        )}
        {(c.limits.length > 0 || c.basis?.detail?.next) && (
          <Section title="Limits">
            <ul className="m-0 pl-4 space-y-1 text-[12.5px] text-[var(--color-mute)]">
              {c.basis?.detail?.next && <li>{c.basis.detail.next}</li>}
              {c.limits.map((m, i) => <li key={i}><MessageLine m={m} /></li>)}
            </ul>
          </Section>
        )}
        <Section title="Method and data">
          <dl className="grid grid-cols-[150px_1fr] gap-x-3 gap-y-1.5 text-[12.5px] m-0">
            <Row k="Method">{c.method_name ?? (c.method_message ? <MessageLine m={c.method_message} /> : '—')}</Row>
            <Row k="Used for">{c.use.detail?.what ?? c.use.label}</Row>
            {c.data.training_vintage && <Row k="Training data as of">{day(c.data.training_vintage)}</Row>}
            {c.data.training_cells != null && <Row k="Places trained on"><span className="tabular-nums">{c.data.training_cells.toLocaleString()}</span></Row>}
          </dl>
          {c.feeds.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {c.feeds.map(f => (
                <div key={f.key} className="flex items-center justify-between gap-3 text-[12.5px]">
                  <span className="text-[var(--color-ink)] min-w-0 truncate" title={f.name}>{f.name}</span>
                  <span className="flex items-center gap-2 shrink-0">
                    {f.last_refresh && <span className="text-[11.5px] text-[var(--color-faint)]">{day(f.last_refresh)}</span>}
                    <StatusChip label={FEED_WORD[f.status ?? 'untracked'] ?? 'Not tracked'} tone={FEED_TONE[f.status ?? 'untracked'] ?? 'neutral'} />
                  </span>
                </div>
              ))}
            </div>
          )}
        </Section>
        <Section title="Governance">
          <dl className="grid grid-cols-[150px_1fr] gap-x-3 gap-y-1.5 text-[12.5px] m-0">
            <Row k="Registered">{day(g.registered_at)}</Row>
            {c.kind === 'score' && <Row k="Approved">{g.approved_at ? `${c.governance_names.approved_by ?? '—'} · ${day(g.approved_at)}` : 'Not approved'}</Row>}
            {c.kind === 'score' && <Row k="Put in use">{g.activated_at ? `${c.governance_names.activated_by ?? '—'} · ${day(g.activated_at)}` : '—'}</Row>}
            <Row k="Controls">{c.controls.join(', ')}</Row>
          </dl>
          {g.events.length > 0 && (
            <ol className="mt-3 m-0 pl-0 list-none space-y-1.5 border-l border-[var(--color-line-2)] ml-1">
              {g.events.map((e, i) => (
                <li key={i} className="pl-3 relative text-[12.5px]">
                  <span className="absolute -left-[4px] top-1.5 w-[7px] h-[7px] rounded-full bg-[var(--color-sky)]" />
                  <span className="text-[var(--color-ink)]">{c.governance_names.events[i]?.to ?? 'Lifecycle step'}</span>
                  <span className="text-[var(--color-faint)]"> · {c.governance_names.events[i]?.who ?? '—'} · {day(e.at)}</span>
                  {e.reason && <InfoButton compact className="ml-1" details={{ title: 'Lifecycle step', sections: [{ heading: 'Reason recorded', body: e.reason }] }} />}
                </li>
              ))}
            </ol>
          )}
        </Section>
        <Section title="Your review">
          {c.review ? (
            <dl className="grid grid-cols-[150px_1fr] gap-x-3 gap-y-1.5 text-[12.5px] m-0">
              <Row k="Conclusion">{c.review.conclusion_label}</Row>
              <Row k="By">{c.review.reviewer} · {day(c.review.reviewed_at)}</Row>
              {c.review.next_review_by && <Row k="Next review by">{day(c.review.next_review_by)}</Row>}
              {c.review.comment && <Row k="Comment"><InfoButton label="Read the comment" details={{ title: 'Review comment', sections: [{ heading: c.review.reviewer, body: c.review.comment }] }} /></Row>}
            </dl>
          ) : <div className="text-[12.5px] text-[var(--color-mute)]">No review recorded yet.</div>}
          <div className="flex flex-wrap gap-2 mt-3">
            {canReview && <Button onClick={onReview}><ShieldCheck size={14} /> Record a review</Button>}
            <Button variant="ghost" onClick={() => download(`/v1/model-risk/card.pdf?ref=${encodeURIComponent(c.ref)}`, `model-card-${c.hazard}.pdf`)}><FileDown size={14} /> Card as PDF</Button>
          </div>
        </Section>
        <Section title="References">
          <dl className="grid grid-cols-[150px_1fr] gap-x-3 gap-y-1.5 text-[12px] m-0 text-[var(--color-faint)]">
            <Row k="Model reference"><span className="text-[var(--color-mute)] break-all">{c.model}</span></Row>
            <Row k="Card fingerprint"><span className="text-[var(--color-mute)] tabular-nums">{c.card_sha256.slice(0, 16)}</span></Row>
          </dl>
        </Section>
      </div>
    </Drawer>
  )
}

export function ReviewDialog({ c, conclusions, onClose }: { c: Card; conclusions: Record<string, string>; onClose: () => void }) {
  const qc = useQueryClient()
  const [conclusion, setConclusion] = useState('fit_for_use'); const [comment, setComment] = useState(''); const [next, setNext] = useState(''); const [busy, setBusy] = useState(false)
  const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]'
  const submit = async () => {
    setBusy(true)
    try {
      await api.post('/v1/model-risk/review', { ref: c.ref, conclusion, comment: comment || null, next_review_by: next || null })
      toast.success(`Review recorded for ${c.name}.`); await qc.invalidateQueries({ queryKey: ['model-risk'] }); onClose()
    } catch (e) { toast.error(apiMessage(e, 'Could not record the review.')) } finally { setBusy(false) }
  }
  return (
    <Dialog bare title={`Review · ${c.name}`} onClose={onClose} className="w-full max-w-[520px] rounded-xl border border-[var(--color-line)] bg-[var(--color-bg)] p-6 shadow-2xl">
      <CloseButton onClick={onClose} className="absolute top-4 right-4" />
      <div className="text-[12px] text-[var(--color-mute)] mb-1">Independent review · {c.kind_name}</div>
      <h2 className="display text-lg font-semibold m-0 text-[var(--color-ink)]">{c.name}</h2>
      <p className="text-[12.5px] text-[var(--color-mute)] mt-1 mb-4">Recorded by name and bound to this card. If the card’s facts change, the review shows as stale.</p>
      <div className="space-y-3">
        <label className="block text-[12px] text-[var(--color-mute)]">Conclusion<select value={conclusion} onChange={e => setConclusion(e.target.value)} className={inp + ' mt-1'}>{Object.entries(conclusions).map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select></label>
        <label className="block text-[12px] text-[var(--color-mute)]">Comment{conclusion !== 'fit_for_use' ? ' (needed for this conclusion)' : ''}<textarea value={comment} onChange={e => setComment(e.target.value)} rows={3} className={inp + ' mt-1'} /></label>
        <label className="block text-[12px] text-[var(--color-mute)]">Next review by<input type="date" value={next} onChange={e => setNext(e.target.value)} className={inp + ' mt-1'} /></label>
        <div className="flex justify-end gap-2 pt-1"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={submit} disabled={busy || (conclusion !== 'fit_for_use' && !comment)}>{busy ? 'Recording…' : 'Record review'}</Button></div>
      </div>
    </Dialog>
  )
}
