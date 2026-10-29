import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, AlertTriangle, Snowflake } from 'lucide-react'
import { api, apiDetail, apiMessage } from '../lib/api'
import { balance } from '../lib/money'
import { horizonLabel, scenarioLabel, statusLabel } from '../lib/hazards'
import { Button, StatGrid, type StatItem } from './ui'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from './Details'
import ReportingRoleForm from './esrs/ReportingRoleForm'
import { StatusChip } from './StatusChip'
import { Dialog } from './Dialog'

// The confirm-data step: before a filing is frozen, the preparer sees the scope, how complete the data is, the
// headline figures and anything still missing (each in the catalogue's words), and confirms "this is the data to
// file". Only then is the report frozen — the gate between the live book and an unchangeable filing.

interface Preflight {
  framework: string; label: string; period_label: string
  basis: { scenario: string; horizon: string; reporting_period_end: string }
  can_generate: boolean; existing_status: string | null; entity_scoped: boolean
  coverage: { label: string; done: number; total: number; pct: number } | null
  total_value_eur: number | null; value_at_risk_eur?: number | null; noun: string; positions?: number; gaps: Message[]
  // binds this exact result: freezing echoes it back and the server checks the book has not changed since
  confirm_token: string
  // a per-product report (SFDR Annexes II–V): the fund it discloses — chosen here when no obligation fixes it
  product_scoped?: boolean; needs_fund?: boolean; funds?: { fund_id: string; name: string; sfdr_classification: string }[]
  fund?: { fund_id: string; name: string; template: string }
  // a report the organisation as a whole does not file (services/governance/report_filers.py — an organisation that
  // records its undertakings): the filer it is prepared for, chosen first; who reports it and why; and the undertakings
  // whose reporting role for the year is still to be stated (an EU Taxonomy report)
  needs_scope?: boolean; scopes?: { entity_id: string; name: string; role: 'solo' | 'consolidated' }[]
  scope_basis?: { title: string; shows: string; legal: string }
  undetermined?: { entity_id: string; name: string; msg: Message | null }[]
  // which values of the asset facts to read, and the figures both the customer and the platform produce
  views?: Record<'joint' | 'client' | 'tellumen', { label: string; facts_changed: number }>
  figures?: { datapoint: string; label: string; unit: string | null; client_value: number | string; tellumen_value: number | null; delta_pct: number | null; provider: string | null }[]
}
type View = 'joint' | 'client' | 'tellumen'
interface Ent { entity_id: string; name: string; kind: string; n_assets: number }

const num = (v: unknown) => typeof v === 'number' ? v.toLocaleString('en-GB', { maximumFractionDigits: 1 }) : v == null ? '—' : String(v)
const CLASS: Record<string, string> = { article_8: 'Article 8', article_9: 'Article 9' }
// the SFDR template a fund's document is printed on (product_filings.PRODUCT_SCOPED annex ids)
const TEMPLATE: Record<string, string> = { AII: 'Pre-contractual, Article 8', AIII: 'Pre-contractual, Article 9', AIV: 'Periodic, Article 8', AV: 'Periodic, Article 9' }
const LEGAL: Record<string, string> = { AII: 'Annex II', AIII: 'Annex III', AIV: 'Annex IV', AV: 'Annex V' }

// The obligation a filing is prepared for (from its card): its entity and period are fixed, and the server enforces them.
export interface ForObligation { obligation_id: string; entity_id: string | null; entity_name: string | null; filing_role: string; scope_role?: string | null; period_end: string; period_label: string; fund_id?: string | null; fund_name?: string | null }

const Label = ({ children, info }: { children: React.ReactNode; info?: { title: string; body: React.ReactNode } }) => (
  <div className="text-[12px] text-[var(--color-faint)] mb-1 flex items-center gap-1.5">{children}
    {info && <InfoButton compact details={{ title: info.title, sections: [{ heading: HEADING.shows, body: info.body }] }} />}</div>)
const select = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'

// disclosureDate: the date the report will be made (an ORSA's conclusion) when it is not today — it chooses the rules
export default function FilingPreflight({ framework, obligation, fund, entity, disclosureDate, onClose, onGenerated }: { framework: string; obligation?: ForObligation; fund?: { fund_id: string; name: string }; entity?: string; disclosureDate?: string; onClose: () => void; onGenerated: (id: string) => void }) {
  const [entityId, setEntityId] = useState<string>(obligation?.entity_id ?? entity ?? '')   // '' = whole organisation
  // which of the entity's reports, where it holds two (an undertaking heading a group: its own and the group's)
  const [role, setRole] = useState<string>(obligation?.scope_role ?? '')
  const [fundId, setFundId] = useState<string>(obligation?.fund_id ?? fund?.fund_id ?? '')
  const q = useQuery({ queryKey: ['preflight', framework, entityId, role, fundId], queryFn: () => api.get<Preflight>(
    `/v1/filings/preflight?framework=${framework}${entityId ? `&entity_id=${entityId}` : ''}${entityId && role ? `&filing_role=${role}` : ''}${fundId ? `&fund_id=${fundId}` : ''}`) })
  const ents = useQuery({ queryKey: ['filing-entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/filings/entities') })
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Message | null>(null)
  const [view, setView] = useState<View>('joint')
  const [figs, setFigs] = useState<Record<string, 'client' | 'tellumen'>>({})
  const d = q.data
  const entities = ents.data?.entities ?? []
  // who files this report (services/governance/report_filers.py): when the organisation is not the filer, only its
  // filers are offered — the whole organisation never is
  const who = useQuery({ queryKey: ['filers', framework], queryFn: () => api.get<{ organisation: boolean; filers: NonNullable<Preflight['scopes']> }>(`/v1/filings/filers?framework=${framework}`) })
  const filers = d?.needs_scope && d.scopes ? d.scopes : who.data && !who.data.organisation ? who.data.filers : null
  const [roleFor, setRoleFor] = useState<{ entity_id: string; name: string } | null>(null)

  const freeze = async () => {
    if (!d?.confirm_token) return
    setBusy(true); setErr(null)
    try {
      const f = await api.post<{ filing_id: string }>('/v1/filings',
        { framework, confirm_token: d.confirm_token, entity_id: entityId || null, filing_role: (entityId && role) || null, fund_id: fundId || null, obligation_id: obligation?.obligation_id ?? null, view, figure_sources: figs, disclosure_date: disclosureDate || null })
      onGenerated(f.filing_id)
    } catch (e) {
      // the book changed since this check loaded, or a rule refused: show why, and re-read so the preparer confirms what is current
      setErr({ label: apiMessage(e, 'The filing could not be frozen'), detail: apiDetail(e) })
      q.refetch()
    } finally { setBusy(false) }
  }
  const blockedByExisting = !!d && !d.can_generate && !d.needs_fund && !d.needs_scope   // one live filing per report, period and scope
  const periodMismatch = !!(obligation && d && obligation.period_end !== d.basis.reporting_period_end.slice(0, 10))
  const blocked = blockedByExisting || periodMismatch || !!d?.needs_fund || !!d?.needs_scope

  const metrics: StatItem[] = d ? [
    d.coverage ? { label: d.coverage.label[0].toUpperCase() + d.coverage.label.slice(1), value: `${d.coverage.pct}%`, sub: `${d.coverage.done} of ${d.coverage.total}` }
      : { label: 'Coverage', value: '—', sub: 'No single measure' },
    ...(d.total_value_eur != null ? [{ label: d.noun === 'positions' ? 'Net asset value in scope' : 'Book value', value: balance(d.total_value_eur),
      sub: d.positions != null ? `${d.positions} positions` : d.coverage ? `${d.coverage.total} ${d.noun}` : undefined }] : []),
    ...(d.value_at_risk_eur != null ? [{ label: 'Value at risk', value: balance(d.value_at_risk_eur) }] : []),
  ] : []

  return (
    <Dialog title="Confirm the data before filing" onClose={onClose}>
      <div className="space-y-4">
        {q.isError ? <MessageLine m={{ label: apiMessage(q.error, 'The data cannot be checked'), detail: apiDetail(q.error) }} className="text-[13px] text-[var(--color-bad)]" />
          : !d ? <div className="text-[13px] text-[var(--color-faint)]">Checking the book…</div> : (<>
          <div>
            <h3 className="display text-lg font-semibold m-0">{d.label}</h3>
            <div className="text-[12.5px] text-[var(--color-mute)] mt-0.5">{d.period_label} · {scenarioLabel(d.basis.scenario)} · {horizonLabel(d.basis.horizon)}</div>
          </div>

          {obligation && (
            <div>
              <Label info={{ title: 'Reporting scope', body: 'The obligation sets who this filing is for and its period; the server holds the filing to them.' }}>Reporting scope</Label>
              <div className="text-[13px]">{obligation.fund_name ? `${obligation.fund_name} · fund` : obligation.entity_name ? `${obligation.entity_name} · ${obligation.filing_role === 'consolidated' ? 'consolidated' : 'solo'}` : 'Whole organisation'} · {obligation.period_label}</div>
            </div>)}
          {periodMismatch && obligation && (
            <div className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-warn)]"><AlertTriangle size={14} className="shrink-0" /> This obligation is for another period
              <InfoButton compact details={{ title: 'This obligation is for another period', sections: [
                { heading: HEADING.shows, body: `The obligation is for ${obligation.period_label} (ending ${obligation.period_end}); your reporting period ends ${d.basis.reporting_period_end.slice(0, 10)}.` },
                { heading: 'What you can do', body: 'Change the reporting period under Basis, then prepare it.' }] }} /></div>)}

          {d.product_scoped && !obligation && (
            <div>
              <Label>Fund</Label>
              {fund ? <div className="text-[13px]">{fund.name}</div> : (
                <select value={fundId} onChange={e => { setFundId(e.target.value); setConfirmed(false) }} className={select}>
                  <option value="">Choose the fund…</option>
                  {(d.funds ?? []).map(f => <option key={f.fund_id} value={f.fund_id}>{f.name} ({CLASS[f.sfdr_classification] ?? 'Other'})</option>)}
                </select>)}
              {d.fund && <div className="mt-1.5 flex items-center gap-1.5"><StatusChip tone="neutral" label={TEMPLATE[d.fund.template] ?? 'Its SFDR template'} />
                <InfoButton compact details={{ title: 'The template for this fund', sections: [{ heading: HEADING.shows, body: "A fund's document is printed on the template for its SFDR classification." },
                  { heading: 'Legal basis', body: `Delegated Regulation (EU) 2022/1288, ${LEGAL[d.fund.template] ?? 'Annexes II to V'}.` }] }} /></div>}
              {d.needs_fund && (d.funds ?? []).length === 0 && <div className="text-[12.5px] text-[var(--color-warn)] mt-1">No fund is classified Article 8 or 9 yet.</div>}
            </div>)}

          {(!obligation || d.needs_scope) && (filers || entities.length > 0) && d.entity_scoped && (
            <div>
              {/* from a calendar card the scope is the card's (above): only why, and the roles still to state */}
              {!obligation && <Label info={{ title: 'Reporting scope', body: "A group consolidates its whole subtree, weighting each entity's book by its ownership and consolidation method; a legal entity files its own book." }}>Reporting scope</Label>}
              {obligation ? null : filers ? (
                // one entity can be offered twice — for its group and for itself — so a choice is the entity and the role
                <select value={entityId ? `${entityId}|${role}` : ''} onChange={e => { const [id, r] = e.target.value.split('|'); setEntityId(id); setRole(r ?? ''); setConfirmed(false) }} className={select}>
                  <option value="" disabled>{filers.length ? 'Choose who reports it…' : 'No filer known yet'}</option>
                  {filers.map(f => <option key={`${f.entity_id}|${f.role}`} value={`${f.entity_id}|${f.role}`}>{f.role === 'consolidated' ? `Group · ${f.name}` : f.name}</option>)}
                </select>) : (
                <select value={entityId} onChange={e => { setEntityId(e.target.value); setRole(''); setConfirmed(false) }} className={select}>
                  <option value="">Whole organisation</option>
                  {entities.filter(e => e.kind === 'group').map(e => <option key={e.entity_id} value={e.entity_id}>Consolidated · {e.name}</option>)}
                  {entities.filter(e => e.kind !== 'group').map(e => <option key={e.entity_id} value={e.entity_id}>{e.name} ({e.n_assets} assets)</option>)}
                </select>)}
              {d.needs_scope && d.scope_basis && (
                <div className="mt-1.5 flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)]">Not reported by the whole organisation
                  <InfoButton compact details={{ title: d.scope_basis.title, sections: [
                    { heading: HEADING.shows, body: d.scope_basis.shows }, { heading: 'Legal basis', body: d.scope_basis.legal }] }} /></div>)}
              {(d.undetermined?.length ?? 0) > 0 && (
                <div className="mt-2 space-y-1.5">
                  <div className="text-[12px] text-[var(--color-warn)]">Reporting role not stated for {d.period_label}</div>
                  {d.undetermined!.map(u => (
                    <div key={u.entity_id} className="flex items-center gap-2 text-[12.5px]">
                      <span className="text-[var(--color-ink)]">{u.name}</span>
                      {u.msg && <InfoButton compact details={messageDetails(u.msg)} />}
                      <Button variant="ghost" onClick={() => setRoleFor(u)}>State the role</Button>
                    </div>))}
                </div>)}
            </div>)}
          {entities.length > 0 && !d.entity_scoped && !d.product_scoped && (
            <Label info={d.framework === 'sfdr_pai' ? { title: 'Whole organisation', body: "Each fund's own statement is prepared in the Funds workspace." } : undefined}>Filed for the whole organisation</Label>)}

          {d.views && (
            <fieldset>
              <legend className="mb-1"><Label info={{ title: 'Which values of your asset facts', body: 'The views differ only in facts the platform derives on its own; today, the country read from the coordinates.' }}>Which values of your asset facts</Label></legend>
              <div className="space-y-1">
                {(['joint', 'client', 'tellumen'] as const).map(v => (
                  <label key={v} className="flex items-start gap-2 text-[12.5px] cursor-pointer">
                    <input type="radio" name="view" checked={view === v} onChange={() => setView(v)} className="mt-0.5 accent-[var(--color-sky)]" />
                    <span><span className="text-[var(--color-ink)]">{d.views![v].label}</span>
                      {v !== 'joint' && <span className="text-[var(--color-faint)]"> · {d.views![v].facts_changed === 0 ? 'same as the book' : `${d.views![v].facts_changed} differ from the book`}</span>}</span>
                  </label>))}
              </div>
            </fieldset>)}

          {(d.figures?.length ?? 0) > 0 && (
            <div>
              <Label info={{ title: 'Figures both you and we produce', body: 'The filing reports the one you choose and keeps the other beside it. Ours is computed again when the filing is frozen.' }}>Figures both you and we produce</Label>
              <div className="space-y-2">
                {d.figures!.map(f => (
                  <div key={f.datapoint} className="rounded-lg border border-[var(--color-line)] p-2.5 text-[12.5px]">
                    <div className="text-[var(--color-ink)] mb-1">{f.label}</div>
                    {(['client', 'tellumen'] as const).map(src => (
                      <label key={src} className="flex items-center gap-2 cursor-pointer">
                        <input type="radio" name={`fig-${f.datapoint}`} checked={(figs[f.datapoint] ?? 'client') === src} disabled={src === 'tellumen' && f.tellumen_value == null}
                          onChange={() => setFigs({ ...figs, [f.datapoint]: src })} className="accent-[var(--color-sky)]" />
                        <span className="text-[var(--color-mute)]">{src === 'client' ? `Yours${f.provider ? ` (${f.provider})` : ''}` : 'Ours'}:</span>
                        <span className="tabular-nums text-[var(--color-ink)]">{num(src === 'client' ? f.client_value : f.tellumen_value)} {f.unit ?? ''}</span>
                        {src === 'tellumen' && f.delta_pct != null && <span className="text-[var(--color-faint)]">· yours differs by {f.delta_pct > 0 ? '+' : ''}{f.delta_pct}%</span>}
                      </label>))}
                  </div>))}
              </div>
            </div>)}

          {blockedByExisting && (
            <div className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-warn)]"><AlertTriangle size={14} /> A live filing already exists · {statusLabel(d.existing_status)}
              <InfoButton compact details={{ title: 'A live filing already exists', sections: [
                { heading: HEADING.shows, body: `A ${d.label} for ${d.period_label} already exists for this scope.` },
                { heading: 'What you can do', body: 'Withdraw it if it is an unfiled draft, or restate it if it was filed.' }] }} /></div>)}

          <StatGrid items={metrics} cols={3} />
          {d.coverage && d.coverage.total > 0 && (
            <div className="h-2 rounded-full bg-[var(--color-line)] overflow-hidden" role="img" aria-label={`${d.coverage.pct}% ${d.coverage.label}`}>
              <div className="h-full rounded-full" style={{ width: `${d.coverage.pct}%`, background: d.coverage.pct >= 100 ? 'var(--color-good)' : 'var(--color-warn)' }} />
            </div>)}

          {d.gaps.length > 0 && (
            <div className="rounded-lg border border-[var(--color-line-2)] p-3">
              <Label info={{ title: 'Still missing', body: 'What is missing is filed as missing: each figure that needs it is left blank and the gap is disclosed, never filled with an assumption.' }}>Still missing</Label>
              <ul className="space-y-1">
                {d.gaps.map((g, i) => <li key={i} className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-ink)]"><AlertTriangle size={12} className="text-[var(--color-warn)] shrink-0" /><MessageLine m={g} /></li>)}
              </ul>
            </div>)}

          {err && <MessageLine m={err} className="text-[12.5px] text-[var(--color-bad)]" />}

          <label className="flex items-start gap-2 text-[12.5px] text-[var(--color-ink)] cursor-pointer">
            <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5 accent-[var(--color-sky)]" disabled={blocked} />
            I confirm this is the data to file. Freeze it as an unchangeable filing.
          </label>
          <div className="flex items-center gap-3">
            <Button onClick={freeze} disabled={busy || !confirmed || blocked}><Snowflake size={14} /> Confirm and freeze</Button>
            {confirmed && <span className="inline-flex items-center gap-1 text-[12px]" style={{ color: 'var(--color-good)' }}><CheckCircle2 size={12} /> Ready</span>}
          </div>
        </>)}
      </div>
      {roleFor && d && <ReportingRoleForm periodEnd={d.basis.reporting_period_end.slice(0, 10)} entity={roleFor.entity_id} name={roleFor.name}
        onClose={() => setRoleFor(null)} onSent={() => { setRoleFor(null); q.refetch() }} />}
    </Dialog>
  )
}
