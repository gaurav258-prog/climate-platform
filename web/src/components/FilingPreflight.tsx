import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, AlertTriangle, Snowflake } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { balance } from '../lib/money'
import { Button, StatGrid, type StatItem } from './ui'
import { Dialog } from './Dialog'

// The confirm-data step: before a filing is frozen, the preparer reviews the basis, the data coverage and
// the headline figures, sees any gaps honestly, and ticks "I confirm this is the data to file". Only then
// is the snapshot frozen. This is the gate between "the live book" and an immutable filing.

interface Preflight {
  framework: string; label: string; period_label: string
  basis: { scenario: string; horizon: string; materiality_threshold: number; reporting_period_end: string }
  can_generate: boolean; existing_status: string | null; entity_scoped: boolean
  coverage: { label: string; done: number; total: number; pct: number } | null
  total_value_eur: number | null; value_at_risk_eur?: number | null; noun: string; positions?: number; gaps: string[]
  // Binds this exact preflight result — generate must echo it back, and the backend re-verifies it's still
  // fresh (the book hasn't changed since). Never a bare "I confirm" boolean; see filings._confirm_token.
  confirm_token: string
  // a per-product report (SFDR Annexes II–V): the fund it discloses — chosen here when no obligation fixes it
  product_scoped?: boolean; needs_fund?: boolean; funds?: { fund_id: string; name: string; sfdr_classification: string }[]
  fund?: { fund_id: string; name: string; template: string }
  // intake phase 5: how far each view of the asset facts is from the book; and the figures where both the client's
  // attested number and ours exist
  views?: Record<'joint' | 'client' | 'tellumen', { label: string; facts_changed: number; by_field: Record<string, number> }>
  figures?: { datapoint: string; label: string; unit: string | null; client_value: number | string; tellumen_value: number | null; delta_pct: number | null; provider: string | null }[]
}
type View = 'joint' | 'client' | 'tellumen'
const VIEW_ORDER: View[] = ['joint', 'client', 'tellumen']
const num = (v: unknown) => typeof v === 'number' ? v.toLocaleString('en-GB', { maximumFractionDigits: 1 }) : v == null ? '—' : String(v)
interface Ent { entity_id: string; name: string; kind: string; parent_entity_id: string | null; n_assets: number }

const eur = (n?: number | null) => balance(n)   // the live book, before freezing: the organisation's currency

// The obligation a filing is being prepared for (from its card): its entity and period are fixed, and the server
// enforces them (filings._obligation_scope).
export interface ForObligation { obligation_id: string; entity_id: string | null; entity_name: string | null; filing_role: string; period_end: string; period_label: string; fund_id?: string | null; fund_name?: string | null }

// disclosureDate: the date the report will be made (an ORSA's conclusion) when it is not today — it chooses the rules
export default function FilingPreflight({ framework, obligation, fund, entity, disclosureDate, onClose, onGenerated }: { framework: string; obligation?: ForObligation; fund?: { fund_id: string; name: string }; entity?: string; disclosureDate?: string; onClose: () => void; onGenerated: (id: string) => void }) {
  const [entityId, setEntityId] = useState<string>(obligation?.entity_id ?? entity ?? '')   // '' = whole organisation
  const [fundId, setFundId] = useState<string>(obligation?.fund_id ?? fund?.fund_id ?? '')   // a per-product report's fund
  // the figures and the confirm token are for exactly the scope being filed
  const q = useQuery({ queryKey: ['preflight', framework, entityId, fundId], queryFn: () => api.get<Preflight>(
    `/v1/filings/preflight?framework=${framework}${entityId ? `&entity_id=${entityId}` : ''}${fundId ? `&fund_id=${fundId}` : ''}`) })
  const ents = useQuery({ queryKey: ['filing-entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/filings/entities') })
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [view, setView] = useState<View>('joint')
  const [figs, setFigs] = useState<Record<string, 'client' | 'tellumen'>>({})
  const d = q.data
  const entities = ents.data?.entities ?? []

  const freeze = async () => {
    if (!d?.confirm_token) return
    setBusy(true); setErr(null)
    try {
      const f = await api.post<{ filing_id: string }>('/v1/filings',
        { framework, confirm_token: d.confirm_token, entity_id: entityId || null, fund_id: fundId || null, obligation_id: obligation?.obligation_id ?? null, view, figure_sources: figs, disclosure_date: disclosureDate || null })
      onGenerated(f.filing_id)
    } catch (e) {
      // A stale token (the book changed since this preflight loaded) surfaces here — refetch so the
      // preparer sees the CURRENT data and can confirm again, rather than silently retrying the old one.
      setErr(apiMessage(e, 'Could not freeze the filing.'))
      q.refetch()
    }
    finally { setBusy(false) }
  }
  // one live filing per framework, period and scope — the pre-filing check answers for the scope being filed
  const blockedByExisting = !!d && !d.can_generate && !d.needs_fund
  // an obligation for another period cannot be prepared until the reporting period is set to it (one period source)
  const periodMismatch = !!(obligation && d && obligation.period_end !== d.basis.reporting_period_end.slice(0, 10))
  const blocked = blockedByExisting || periodMismatch || !!d?.needs_fund     // a per-product report waits for its fund

  return (
    <Dialog title="Confirm the data before filing" onClose={onClose}>
        <div className="space-y-4">
          {!d ? <div className="text-[13px] text-[var(--color-faint)]">checking the book…</div> : (<>
            <div>
              <h3 className="display text-lg font-semibold">{d.label}</h3>
              <div className="mono text-[11px] text-[var(--color-faint)]">{d.period_label} · basis {d.basis.scenario}/{d.basis.horizon} · materiality {d.basis.materiality_threshold}</div>
            </div>

            {obligation && (
              <div>
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Reporting scope · set by the obligation</div>
                <div className="text-[13px]">{obligation.fund_name ? `${obligation.fund_name} — financial product` : obligation.entity_name ? `${obligation.entity_name} — ${obligation.filing_role === 'consolidated' ? 'consolidated' : 'solo'}` : 'Whole organisation'} · {obligation.period_label}</div>
              </div>
            )}
            {periodMismatch && obligation && (
              <div className="flex gap-2 text-[12.5px] text-[var(--color-warn)]"><AlertTriangle size={15} className="shrink-0 mt-0.5" />
                <span>This obligation is for {obligation.period_label} (period ending {obligation.period_end}), but your reporting period is set to end {d.basis.reporting_period_end.slice(0, 10)}. Change the reporting period before preparing it.</span></div>
            )}
            {d.product_scoped && !obligation && (
              <div>
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Financial product</div>
                {fund ? <div className="text-[13px]">{fund.name}</div> : (
                  <select value={fundId} onChange={e => { setFundId(e.target.value); setConfirmed(false) }}
                    className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
                    <option value="">Choose the fund…</option>
                    {(d.funds ?? []).map(f => <option key={f.fund_id} value={f.fund_id}>{f.name} ({f.sfdr_classification.replace('article_', 'Art. ')})</option>)}
                  </select>
                )}
                {d.fund && <div className="mono text-[10px] text-[var(--color-faint)] mt-1">disclosed on {d.fund.template.replace('A', 'Annex ')} — the template for its SFDR article</div>}
                {d.needs_fund && (d.funds ?? []).length === 0 && <div className="text-[12px] text-[var(--color-warn)] mt-1">No fund is classified Article 8 or 9 yet.</div>}
              </div>
            )}
            {!obligation && entities.length > 0 && d.entity_scoped && (
              <div>
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Reporting scope</div>
                <select value={entityId} onChange={e => { setEntityId(e.target.value); setConfirmed(false) }}
                  className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
                  <option value="">Whole organisation</option>
                  {entities.filter(e => e.kind === 'group').map(e => <option key={e.entity_id} value={e.entity_id}>Consolidated — {e.name} (group)</option>)}
                  {entities.filter(e => e.kind !== 'group').map(e => <option key={e.entity_id} value={e.entity_id}>{e.name} ({e.n_assets} assets)</option>)}
                </select>
                <div className="mono text-[10px] text-[var(--color-faint)] mt-1">a group consolidates its whole subtree (proportional lines ownership‑weighted); a legal entity files its own book.</div>
              </div>
            )}
            {entities.length > 0 && !d.entity_scoped && !d.product_scoped && (
              <div className="mono text-[10px] text-[var(--color-faint)]">Files at whole-organisation level{d.framework === 'sfdr_pai' ? ' — per-fund SFDR statements are in the Funds workspace.' : '.'}</div>
            )}

            {d.views && (
              <fieldset>
                <legend className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Which values of your assets' facts</legend>
                <div className="space-y-1">
                  {VIEW_ORDER.map(v => (
                    <label key={v} className="flex items-start gap-2 text-[12.5px] cursor-pointer">
                      <input type="radio" name="view" checked={view === v} onChange={() => setView(v)} className="mt-0.5 accent-[var(--color-sky)]" />
                      <span><span className="text-[var(--color-ink)]">{d.views![v].label}</span>
                        {v !== 'joint' && <span className="text-[var(--color-faint)]"> · {d.views![v].facts_changed === 0 ? 'same as the book' : `${d.views![v].facts_changed} fact(s) differ from the book`}</span>}</span>
                    </label>))}
                </div>
                <div className="mono text-[10px] text-[var(--color-faint)] mt-1">The views differ only in facts we derive independently (today: country from the coordinates).</div>
              </fieldset>
            )}

            {(d.figures?.length ?? 0) > 0 && (
              <div>
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Figures both you and we produce — which to report</div>
                <div className="space-y-2">
                  {d.figures!.map(f => (
                    <div key={f.datapoint} className="rounded-lg border border-[var(--color-line)] p-2.5 text-[12px]">
                      <div className="text-[var(--color-ink)] mb-1">{f.label}</div>
                      {(['client', 'tellumen'] as const).map(src => (
                        <label key={src} className="flex items-center gap-2 cursor-pointer">
                          <input type="radio" name={`fig-${f.datapoint}`} checked={(figs[f.datapoint] ?? 'client') === src} disabled={src === 'tellumen' && f.tellumen_value == null}
                            onChange={() => setFigs({ ...figs, [f.datapoint]: src })} className="accent-[var(--color-sky)]" />
                          <span className="text-[var(--color-mute)]">{src === 'client' ? `Yours${f.provider ? ` (${f.provider})` : ''}` : 'Ours'}:</span>
                          <span className="mono text-[var(--color-ink)]">{num(src === 'client' ? f.client_value : f.tellumen_value)} {f.unit ?? ''}</span>
                          {src === 'tellumen' && f.delta_pct != null && <span className="text-[var(--color-faint)]">· yours differs by {f.delta_pct > 0 ? '+' : ''}{f.delta_pct}%</span>}
                        </label>))}
                    </div>))}
                </div>
                <div className="mono text-[10px] text-[var(--color-faint)] mt-1">The filing reports the one you choose and keeps the other beside it. Ours is recomputed when the filing is frozen.</div>
              </div>
            )}

            {blockedByExisting && (
              <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-warn)]">
                <AlertTriangle size={14} /> A live {d.label} for {d.period_label} already exists for this scope ({d.existing_status}). Supersede it to restate.
              </div>
            )}

            {(() => {
              const metrics: StatItem[] = [
                d.coverage
                  ? { label: d.coverage.label, value: `${d.coverage.pct}%`, sub: `${d.coverage.done}/${d.coverage.total}` }
                  : { label: 'coverage', value: '—', sub: `from your ${d.noun}` },
              ]
              if (d.total_value_eur != null) metrics.push({
                label: d.noun === 'positions' ? 'NAV in scope' : 'book value',
                value: eur(d.total_value_eur),
                sub: d.positions != null ? `${d.positions} positions` : (d.coverage ? `${d.coverage.total} ${d.noun}` : undefined),
              })
              if (d.value_at_risk_eur != null) metrics.push({ label: 'value at risk', value: eur(d.value_at_risk_eur) })
              return <StatGrid items={metrics} cols={3} />
            })()}

            {d.gaps.length > 0 && (
              <div className="rounded-lg border border-[var(--color-line-2)] p-3">
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Known gaps — will be disclosed as-is</div>
                <ul className="space-y-1">
                  {d.gaps.map((g, i) => <li key={i} className="flex items-start gap-1.5 text-[12px] text-[var(--color-mute)]"><AlertTriangle size={12} className="mt-0.5 text-[var(--color-warn)] shrink-0" />{g}</li>)}
                </ul>
              </div>
            )}

            {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}

            <label className="flex items-start gap-2 text-[12.5px] text-[var(--color-ink)] cursor-pointer">
              <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5 accent-[var(--color-sky)]" disabled={blocked} />
              I confirm this is the data to file — freeze it as an immutable filing.
            </label>
            <div className="flex items-center gap-3">
              <Button variant="primary" onClick={freeze} disabled={busy || !confirmed || blocked}><Snowflake size={14} /> Confirm & freeze filing</Button>
              {confirmed && <span className="inline-flex items-center gap-1 text-[11px]" style={{ color: '#34d399' }}><CheckCircle2 size={12} /> ready</span>}
            </div>
          </>)}
        </div>
    </Dialog>
  )
}
