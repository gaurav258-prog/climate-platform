import { useState, Fragment, createContext, useContext } from 'react'
import { Pencil, Check, X, Clock } from 'lucide-react'
import { api, apiDetail, apiMessage } from '../../lib/api'
import { hazardLabel } from '../../lib/hazards'
import { methodLabel, type Labels } from '../../lib/labels'
import { money } from '../../lib/money'
import { toast } from '../../lib/toast'
import { Card } from '../ui'
import { HEADING, InfoButton, MessageLine, type Message, type DetailSection } from '../Details'
import { DocumentItems, type DocItem } from '../SfdrDocumentItems'

// The parts of the final form (FilingForm): the regulator's template layout, the flat list of figures, a value cell with
// where it comes from, a cell the institution supplies, and the manual change of a figure under four eyes.

export interface Override { reason: string; by: string; at: string; approved_by: string; approved_at: string }
export interface Dp {
  key: string; label: string; value: number | string | null; fmt: string; unit: string | null; source: string; note: string | null
  manual?: boolean; original_value?: number | null; override?: Override; pending?: { value: number; reason: string; by: string }
  // a figure both you and we produce: which one this filing reports, and the other
  figure?: { reported: 'client' | 'tellumen'; client_value: number | string | null; tellumen_value: number | null; delta_pct: number | null; client_provider: string | null }
}
export interface Group { group: string; datapoints: Dp[] }
// supply: a value the institution enters for the filing's period; `member` and `choices` for a statement per member from a
// closed list (a group's method for each related undertaking)
export interface AnnexCell { text?: string; dp?: Dp; num?: boolean; source?: string; supply?: { framework: string; key: string; reporting_entity_id?: string | null; filing_role?: string | null; member?: string; choices?: Record<string, string> }; greyed?: boolean; frozen_value?: number | string | null }
export const suppliedKey = (key: string, member?: string | null) => member ? `${key}@${member}` : key
export interface AnnexSection { title: string; key?: string; spec?: { template?: string } | null; note: string | null; columns: string[]; col_sources?: string[]; rows: { type: 'row' | 'subheader'; label?: string; cells?: AnnexCell[] }[]; kind?: 'document'; items?: DocItem[] }
export interface Annex { official_name: string; authority: string | null; official_form: string | null; legal_basis: string | null; form_url: string | null; sections: AnnexSection[] }
export interface Supplied { value: string; status: 'pending' | 'attested'; by?: string | null }
export type EditProps = { filingId: string; canEdit: boolean; edit: string | null; setEdit: (k: string | null) => void; onDone: () => void }

// the currency the frozen filing presents in (fmt 'eur' = a money figure, whatever its currency)
export const CurrencyCtx = createContext('EUR')
export function fmt(v: number | string | null, f: string, ccy = 'EUR'): string {
  if (v == null) return '—'
  if (typeof v === 'string') return v
  if (f === 'eur') return money(v, ccy)
  if (f === 'pct') return `${v}%`
  if (f === 'tco2e') return Math.round(v).toLocaleString('en-GB')
  return Number.isInteger(v) ? v.toLocaleString('en-GB') : v.toLocaleString('en-GB', { maximumFractionDigits: 2 })
}
export const dpLabel = (d: Dp) => d.key.startsWith('hazard.') ? hazardLabel(d.label) : d.label

// A note the server wrote with method choices in it ('not stated: method.at_risk_level (A01@baseline)') names each
// choice in customer words (lib/labels), without the internal member it was missing for.
export const named = (note: string, labels: Labels) =>
  note.replace(/method\.[a-z0-9_]+(?: \([^)]*\))?/g, m => methodLabel(labels, m.split(' ')[0])).replace(/^not computed — /i, 'Not computed: ')

// where a column's figures come from (a template's col_sources)
const SRC: Record<string, { label: string; color: string }> = {
  computed: { label: 'Computed by Tellumen', color: 'var(--color-sky)' },
  integrated: { label: 'From your bank systems', color: 'var(--color-warn)' },
  manual: { label: 'You author', color: 'var(--color-viz, #a78bfa)' },
}
const SrcDot = ({ source }: { source?: string }) => source && SRC[source]
  ? <span className="inline-block w-[6px] h-[6px] rounded-full align-middle" style={{ background: SRC[source].color }} title={SRC[source].label} /> : null

// The regulator's own template layout.
export function AnnexView({ annex, supplied, periodEnd, onSupplied, hideName, labels, ...ep }: { annex: Annex; supplied: Record<string, Supplied>; periodEnd: string | null; onSupplied: () => void; hideName?: boolean; labels: Labels } & EditProps) {
  return (
    <Card className="p-0 overflow-hidden">
      {!hideName && <FormName annex={annex} className="px-4 py-3 border-b border-[var(--color-line)]" />}
      {annex.sections.map((s, si) => {
        const srcs = Array.from(new Set((s.col_sources ?? []).filter(x => SRC[x])))
        return (
          <div key={si} className={si > 0 ? 'border-t border-[var(--color-line)]' : ''}>
            <div className="px-4 py-2 bg-[var(--color-bg-2)] flex items-center gap-2 flex-wrap">
              <span className="text-[12px] font-medium text-[var(--color-ink)]">{s.title}</span>
              {s.note && <InfoButton compact details={{ title: s.title, sections: [{ heading: 'About this section', body: named(s.note, labels) }] }} />}
              {srcs.map(x => <span key={x} className="inline-flex items-center gap-1 text-[10.5px] text-[var(--color-faint)]"><SrcDot source={x} />{SRC[x].label}</span>)}
            </div>
            {s.kind === 'document' ? <DocumentItems items={s.items ?? []} /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead><tr className="text-left">{s.columns.map((c, ci) => (
                    <th key={ci} className={`px-4 py-1.5 text-[10.5px] text-[var(--color-faint)] font-medium align-bottom ${ci >= s.columns.length - 1 ? 'text-right' : ''}`}>
                      <div className={`flex items-center gap-1 ${ci >= s.columns.length - 1 ? 'justify-end' : ''}`}><SrcDot source={s.col_sources?.[ci]} /><span>{c}</span></div></th>))}</tr></thead>
                  <tbody>{s.rows.map((r, ri) => {
                    if (r.type === 'subheader') return <tr key={ri}><td colSpan={s.columns.length} className="px-4 pt-3 pb-1 text-[11px] font-medium text-[var(--color-sky)]">{r.label}</td></tr>
                    const cells = r.cells ?? []
                    const dps = cells.map(c => c.dp).filter(Boolean) as Dp[]
                    const dp = dps.find(d => d.key === ep.edit) ?? dps[0]
                    return (
                      <Fragment key={ri}>
                        <tr className="border-t border-[var(--color-line)]" style={dp?.manual ? { background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' } : undefined}>
                          {cells.map((c, ci) => {
                            if (c.dp) return <td key={ci} className="px-4 py-1.5 text-right align-top"><CellValue dp={c.dp} {...ep} /></td>
                            // a cell the template greys out (no instruction names it): hatched, as printed
                            if (c.greyed) return <td key={ci} aria-label="Not reported" style={{ background: 'repeating-linear-gradient(135deg, transparent 0 5px, var(--color-line) 5px 6px)' }} />
                            // a cell the institution enters itself — never a figure aggregated from loan data
                            if (c.supply) return <td key={ci} className="px-4 py-1.5 align-top text-right"><SupplyCell cell={c} supplied={supplied[suppliedKey(c.supply.key, c.supply.member)]} periodEnd={periodEnd} canEdit={ep.canEdit} onSaved={onSupplied} /></td>
                            const last = ci === cells.length - 1
                            return <td key={ci} className={`px-4 py-1.5 align-top ${c.num ? 'text-right tabular-nums text-[11.5px] text-[var(--color-ink)]' : last ? 'text-right text-[11px] text-[var(--color-faint)]' : 'text-[var(--color-ink)]'}`}>{c.text}</td>
                          })}
                        </tr>
                        {dp && ep.edit === dp.key && <tr><td colSpan={s.columns.length} className="px-4 pb-2"><OverrideEditor filingId={ep.filingId} dp={dp} onClose={() => ep.setEdit(null)} onDone={ep.onDone} /></td></tr>}
                      </Fragment>)
                  })}</tbody>
                </table>
              </div>)}
          </div>)
      })}
    </Card>
  )
}

// The official form's name, its legal basis one click away.
export function FormName({ annex, className }: { annex: Annex; className?: string }) {
  const about: DetailSection[] = [
    ...(annex.official_form ? [{ heading: 'Official form', body: annex.official_form }] : []),
    ...(annex.legal_basis ? [{ heading: 'Legal basis', body: annex.legal_basis }] : []),
    ...(annex.authority ? [{ heading: 'Authority', body: annex.authority }] : []),
  ]
  return (
    <div className={`flex items-center gap-1.5 ${className ?? ''}`}>
      <span className="text-[13px] text-[var(--color-ink)]">{annex.official_name}</span>
      {about.length > 0 && <InfoButton compact details={{ title: annex.official_name, sections: about }} />}
    </div>
  )
}

// A figure on the form: where it comes from, whether it was changed by hand (with the change one click away), a change
// awaiting a second person, and the pencil to propose one.
export function CellValue({ dp, canEdit, edit, setEdit }: { dp: Dp } & EditProps) {
  const ccy = useContext(CurrencyCtx)
  const editable = canEdit && dp.fmt !== 'text' && typeof dp.value === 'number'
  const chip = (c: string) => ({ color: c, background: `color-mix(in oklab, ${c} 14%, transparent)` })
  return (
    <span className="inline-flex items-center gap-1.5 justify-end">
      {dp.pending && <span className="text-[10.5px] px-1.5 py-0.5 rounded inline-flex items-center gap-1" style={chip('var(--color-sky)')}><Clock size={9} /> Awaiting approval: {fmt(dp.pending.value, dp.fmt, ccy)}</span>}
      {dp.manual
        ? <span className="inline-flex items-center gap-1 text-[10.5px] px-1.5 py-0.5 rounded" style={chip('var(--color-warn)')}>Changed by hand
            <InfoButton compact details={{ title: 'Changed by hand', sections: [
              { heading: 'Was', body: fmt(dp.original_value ?? null, dp.fmt, ccy) },
              { heading: 'Reason', body: dp.override?.reason ?? '—' },
              { heading: 'Who', body: `Proposed by ${dp.override?.by ?? '—'}, approved by ${dp.override?.approved_by ?? '—'}` }] }} /></span>
        : dp.value != null && <span className="text-[10.5px] px-1.5 py-0.5 rounded" style={chip(dp.source === 'book' ? 'var(--color-sky)' : 'var(--color-mute)')}>{dp.source === 'book' ? 'Your book' : 'Calculated'}</span>}
      <span className="text-[12.5px] tabular-nums" style={{ color: dp.manual ? 'var(--color-warn)' : 'var(--color-ink)' }}>{fmt(dp.value, dp.fmt, ccy)}</span>
      {dp.unit && <span className="text-[10.5px] text-[var(--color-faint)]">{dp.unit}</span>}
      {editable && edit !== dp.key && <button onClick={() => setEdit(dp.key)} aria-label="Propose a change to this figure" title="Propose a change (four eyes)" className="text-[var(--color-faint)] hover:text-[var(--color-sky)]"><Pencil size={11} /></button>}
    </span>
  )
}

// The flat list of the filing's figures, by group.
export function DatapointList({ groups, labels, ...ep }: { groups: Group[]; labels: Labels } & EditProps) {
  const ccy = useContext(CurrencyCtx)
  return (
    <Card className="p-0 overflow-hidden">
      {groups.map((g, gi) => (
        <div key={gi} className={gi > 0 ? 'border-t border-[var(--color-line)]' : ''}>
          <div className="px-4 py-2 bg-[var(--color-bg-2)] text-[12px] font-medium text-[var(--color-ink)]">{g.group}</div>
          <div className="divide-y divide-[var(--color-line)]">
            {g.datapoints.map(dp => {
              const more: DetailSection[] = [
                ...(dp.note ? [{ heading: HEADING.shows, body: named(dp.note, labels) }] : []),
                ...(dp.figure ? [{ heading: 'Yours and ours', body: `This filing reports ${dp.figure.reported === 'client' ? `your figure${dp.figure.client_provider ? ` (${dp.figure.client_provider})` : ''}` : 'our figure'}. Yours: ${fmt(typeof dp.figure.client_value === 'number' ? dp.figure.client_value : null, dp.fmt, ccy)}; ours: ${fmt(dp.figure.tellumen_value, dp.fmt, ccy)}${dp.figure.delta_pct != null ? `; a difference of ${dp.figure.delta_pct > 0 ? '+' : ''}${dp.figure.delta_pct}%` : ''}.` }] : []),
              ]
              return (
                <div key={dp.key} className="px-4 py-2 text-[12.5px]" style={dp.manual ? { background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' } : undefined}>
                  <div className="flex items-center gap-3">
                    <div className="min-w-0 flex-1 flex items-center gap-1.5">
                      <span className="text-[var(--color-ink)]">{dpLabel(dp)}</span>
                      {dp.figure && <span className="text-[10.5px] text-[var(--color-faint)]">{dp.figure.reported === 'client' ? 'Yours' : 'Ours'}</span>}
                      {more.length > 0 && <InfoButton compact details={{ title: dpLabel(dp), sections: more }} />}
                    </div>
                    <CellValue dp={dp} {...ep} />
                  </div>
                  {ep.edit === dp.key && <OverrideEditor filingId={ep.filingId} dp={dp} onClose={() => ep.setEdit(null)} onDone={ep.onDone} />}
                </div>)
            })}
          </div>
        </div>
      ))}
    </Card>
  )
}

// Propose a manual change of a figure: a second person approves it before it lands; the original stays on record.
function OverrideEditor({ filingId, dp, onClose, onDone }: { filingId: string; dp: Dp; onClose: () => void; onDone: () => void }) {
  const [value, setValue] = useState(String(typeof dp.value === 'number' ? dp.value : ''))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Message | null>(null)
  const save = async () => {
    const v = Number(value)
    if (!isFinite(v)) { setErr({ label: 'Enter a number' }); return }
    if (!reason.trim()) { setErr({ label: 'Give a reason for the change' }); return }
    setBusy(true); setErr(null)
    try { await api.post(`/v1/filings/${filingId}/overrides`, { datapoint_key: dp.key, value: v, reason: reason.trim() }); onDone() }
    catch (e) { setErr({ label: apiMessage(e, 'The change could not be proposed'), detail: apiDetail(e) }) }
    finally { setBusy(false) }
  }
  const box = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
  return (
    <div className="mt-2 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] p-2.5 space-y-2 text-left">
      {err && <MessageLine m={err} className="text-[12px] text-[var(--color-bad)]" />}
      <div className="text-[12px] text-[var(--color-mute)] flex items-center gap-1.5">Change · {dpLabel(dp)}
        <InfoButton compact details={{ title: 'Changing a figure by hand', sections: [{ heading: HEADING.shows, body: 'A second person approves the change before it lands on the form; the original figure stays on record, and the change carries its reason.' }] }} /></div>
      <div className="flex flex-wrap items-center gap-2">
        <input value={value} onChange={e => setValue(e.target.value)} className={`${box} w-40 tabular-nums`} aria-label="New value" placeholder="New value" />
        <input value={reason} onChange={e => setReason(e.target.value)} className={`${box} flex-1 min-w-[200px]`} placeholder="Reason (recorded)" />
        <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-sky)] text-[var(--color-on-accent)] px-3 py-1.5 text-[12px] font-medium disabled:opacity-50"><Check size={13} /> Propose</button>
        <button onClick={onClose} aria-label="Cancel" className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)]"><X size={13} /></button>
      </div>
    </div>
  )
}

// A template cell the institution enters itself, for this filing's reporting period; a second person attests it, and a
// newer attested value lands in the filing on the draft's next refresh.
function SupplyCell({ cell, supplied, periodEnd, canEdit, onSaved }: { cell: AnnexCell; supplied?: Supplied; periodEnd: string | null; canEdit: boolean; onSaved: () => void }) {
  const frozen = cell.text ?? '—'
  const [val, setVal] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    if (!val.trim() || !cell.supply || !periodEnd) return
    setBusy(true)
    const n = Number(val.replace(/,/g, ''))
    try {
      await api.post('/v1/provided', { framework: cell.supply.framework, datapoint_key: cell.supply.key, reporting_period_end: periodEnd, reporting_entity_id: cell.supply.reporting_entity_id ?? undefined,
        ...(cell.supply.filing_role ? { filing_role: cell.supply.filing_role } : {}),   // which of the entity's reports
        ...(cell.supply.member ? { breakdown_member: cell.supply.member } : {}),
        ...(!cell.supply.choices && !Number.isNaN(n) ? { value_num: n } : { value_text: val.trim() }) })
      toast.success('Sent for attestation by a second person.'); setVal(''); onSaved()
    } catch (e) { toast.error(apiMessage(e, 'Could not submit this value.')) } finally { setBusy(false) }
  }
  // the value frozen in the filing (raw), not its display text: '5000000' and '€5.0m' are the same figure
  const same = (a: string, b: unknown) => b != null && (a === String(b) || (a.trim() !== '' && !Number.isNaN(Number(a)) && Number(a) === Number(b)))
  const newer = supplied && !same(supplied.value, cell.frozen_value) ? supplied : null
  const choices = cell.supply?.choices
  const shown = (v: string) => choices?.[v] ?? v                       // a choice by its words, never its code
  return (
    <div className="inline-flex flex-col items-end gap-1">
      <span className="inline-flex items-center gap-1">{frozen !== '—' && <span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--color-viz,#a78bfa)' }} />}{frozen}</span>
      {newer && <span className="text-[10px] inline-flex items-center gap-0.5" style={{ color: newer.status === 'pending' ? 'var(--color-warn)' : 'var(--color-viz,#a78bfa)' }}>
        {newer.status === 'pending' ? <><Clock size={8} />{shown(newer.value)} awaiting attestation</> : <>{shown(newer.value)} attested · refresh the draft</>}</span>}
      {canEdit && choices && (
        <div className="flex items-center gap-1">
          <select value={val} onChange={e => setVal(e.target.value)} disabled={busy} aria-label="Choose the value you state"
            className="text-[11px] bg-[var(--color-panel)] border border-[var(--color-line)] rounded px-1 py-0.5 text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]">
            <option value="">Choose…</option>
            {Object.entries(choices).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
          {val && <button onClick={submit} disabled={busy} className="text-[10.5px] px-1.5 py-0.5 rounded" style={{ background: 'color-mix(in oklab, var(--color-sky) 16%, transparent)', color: 'var(--color-sky)' }}>Send</button>}
        </div>)}
      {canEdit && !choices && (
        <div className="flex items-center gap-1">
          <input value={val} onChange={e => setVal(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') submit() }} disabled={busy}
            placeholder="Enter…" aria-label="Value you supply" title="You supply this cell for the filing's period; a second person attests it"
            className="w-20 text-right tabular-nums text-[11px] bg-transparent border-0 border-b border-dashed border-[var(--color-line)] px-0.5 py-0 text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)] placeholder:text-[var(--color-faint)]" />
          {val.trim() && <button onClick={submit} disabled={busy} className="text-[10.5px] px-1.5 py-0.5 rounded" style={{ background: 'color-mix(in oklab, var(--color-sky) 16%, transparent)', color: 'var(--color-sky)' }}>Send</button>}
        </div>)}
    </div>
  )
}
