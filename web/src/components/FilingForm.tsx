import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, FileSpreadsheet, ClipboardList, Scale } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useLabels, type Labels } from '../lib/labels'
import { toast } from '../lib/toast'
import { Card, SectionHead } from './ui'
import { HEADING, InfoButton } from './Details'
import { StatusChip } from './StatusChip'
import FilingFx, { type Fx } from './FilingFx'
import FilingConsolidation, { type Consolidation } from './FilingConsolidation'
import { AnnexView, CurrencyCtx, DatapointList, FormName, suppliedKey, type Annex, type EditProps, type Group, type Supplied } from './filing/formParts'
import { EARLIER, p3Group, type P3Group } from './filing/words'

// The final form — the frozen disclosure, two ways over one set of figures: the regulator's own template layout as it
// will be submitted, and the flat list of figures, each with where it comes from. A preparer can propose a manual change
// of a figure (with its reason); a second person approves it before it lands, and the frozen report itself never
// changes — the change is a separate, audited layer read over it.

interface Form { framework: string; period_end: string | null; status: string; official_form_url: string | null; n_manual: number; n_pending: number; groups: Group[]; annex: Annex | null; currency?: string; fx?: Fx | null; consolidation?: Consolidation | null; reporting_entity_id?: string | null; elections?: Election[] | null }
interface Election { key: string; label: string; value: unknown; value_label?: string | null; stated: boolean }
interface ProvidedItem { datapoint_key: string; value_num: number | null; value_text: string | null; status: string; submitted_by: string | null; reporting_period_end: string | null; reporting_entity_id?: string | null; breakdown_member?: string | null }
const EDITABLE = ['draft', 'returned', 'in_review', 'approved']   // a submitted, accepted or superseded filing never changes

export default function FilingForm({ filingId }: { filingId: string }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const labels = useLabels()
  const q = useQuery({ queryKey: ['filing-form', filingId], queryFn: () => api.get<Form>(`/v1/filings/${filingId}/form`) })
  // the values supplied for this filing's period (template cells the institution enters), from the one supplied-value store
  const suppliedQ = useQuery({ queryKey: ['provided', q.data?.framework], enabled: !!q.data?.framework,
    queryFn: () => api.get<{ provided: ProvidedItem[] }>(`/v1/provided?framework=${q.data!.framework}`) })
  const [edit, setEdit] = useState<string | null>(null)
  const [view, setView] = useState<'official' | 'datapoints'>('official')
  const d = q.data
  if (!d || d.groups.length === 0) return null
  const supplied: Record<string, Supplied> = {}
  for (const p of suppliedQ.data?.provided ?? []) {
    if (p.reporting_period_end !== d.period_end || !['pending', 'attested'].includes(p.status)) continue
    if ((p.reporting_entity_id ?? null) !== (d.reporting_entity_id ?? null)) continue   // the filing's own entity's values
    // a value stated per member (a group's method for each related undertaking) is keyed by its member too
    supplied[suppliedKey(p.datapoint_key, p.breakdown_member)] = { value: String(p.value_num ?? p.value_text ?? ''), status: p.status as Supplied['status'], by: p.submitted_by }
  }
  const onSupplied = () => qc.invalidateQueries({ queryKey: ['provided', d.framework] })
  const canEdit = (profile?.permissions ?? []).includes('approvals.create') && EDITABLE.includes(d.status)
  const ep: EditProps = { filingId, canEdit, edit, setEdit, onDone: () => { setEdit(null); qc.invalidateQueries({ queryKey: ['filing-form', filingId] }); qc.invalidateQueries({ queryKey: ['approvals'] }) } }
  const hasAnnex = !!d.annex && d.annex.sections.length > 0
  const common = { supplied, periodEnd: d.period_end, onSupplied, labels, ...ep }

  return (
    <CurrencyCtx.Provider value={d.currency ?? 'EUR'}>
      <div className="space-y-3">
        {d.consolidation && <FilingConsolidation c={d.consolidation} />}
        {d.elections && d.elections.length > 0 && <Elections e={d.elections} />}
        {d.fx && <FilingFx fx={d.fx} />}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <SectionHead icon={ClipboardList}>Final form</SectionHead>
            {d.n_manual > 0 && <StatusChip tone="warn" label={`${d.n_manual} changed by hand`} />}
            {d.n_pending > 0 && <StatusChip tone="neutral" label={`${d.n_pending} awaiting approval`} />}
            <InfoButton compact details={{ title: 'Final form', sections: [
              { heading: HEADING.shows, body: 'The frozen report as it will be submitted: the official template, or the same figures as a list.' },
              { heading: HEADING.read, body: 'Each figure says where it comes from: your book, calculated by the platform, or changed by hand. A change by hand needs a second person to approve it, and the original stays on record.' }] }} />
          </div>
          <div className="flex items-center gap-2">
            {hasAnnex && (
              <div className="flex gap-0.5 p-0.5 rounded-lg border border-[var(--color-line-2)]" role="tablist">
                {(['official', 'datapoints'] as const).map(v => (
                  <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
                    className={`px-2.5 py-0.5 rounded-md text-[12px] transition ${view === v ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)] hover:text-[var(--color-ink)]'}`}>{v === 'official' ? 'Official form' : 'Figures'}</button>))}
              </div>)}
            {d.official_form_url && <a href={d.official_form_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={12} /> Official template <ExternalLink size={11} /></a>}
          </div>
        </div>
        {view !== 'official' || !hasAnnex ? <DatapointList groups={d.groups} labels={labels} {...ep} />
          : d.framework === 'bank_p3esg' ? <P3FormTabs annex={d.annex!} entityId={d.reporting_entity_id ?? null} {...common} />
          : <AnnexView annex={d.annex!} {...common} />}
      </div>
    </CurrencyCtx.Provider>
  )
}

// The Pillar 3 forms grouped into four tabs by the EBA's own risk themes, so a preparer lands on the group they own.
const P3_TABS: { k: P3Group; label: string; holds: string }[] = [
  { k: 'qual', label: 'Qualitative', holds: 'Tables 1 to 3' }, { k: 'trans', label: 'Transition risk', holds: 'Templates 1 to 4' },
  { k: 'phys', label: 'Physical risk', holds: 'Template 5' }, { k: 'tax', label: 'Taxonomy and green asset ratio', holds: 'Templates 6 to 10' },
]
interface QData { tables: { table: string; title: string; rows: QRow[] }[]; total_rows: number; authored: number; period_end: string }
interface QRow { key: string; row: string; group: string; prompt: string; value: string; basis?: string; required_when?: string }
const qualUrl = (entityId: string | null, periodEnd: string | null) =>
  `/v1/filings/qualitative/p3esg?undertaking=${entityId ?? 'organisation'}${periodEnd ? `&period_end=${periodEnd}` : ''}`

function P3FormTabs({ annex, entityId, ...common }: { annex: Annex; entityId: string | null; supplied: Record<string, Supplied>; periodEnd: string | null; onSupplied: () => void; labels: Labels } & EditProps) {
  const [tab, setTab] = useState<P3Group>('qual')
  const qual = useQuery({ queryKey: ['p3-qualitative', entityId, common.periodEnd], queryFn: () => api.get<QData>(qualUrl(entityId, common.periodEnd)) })
  const of = (g: P3Group): Annex => ({ ...annex, sections: annex.sections.filter(s => p3Group(s.spec?.template, s.title) === g) })
  const tabs = annex.sections.some(s => p3Group(s.spec?.template, s.title) === 'earlier') ? [...P3_TABS, { k: 'earlier' as P3Group, label: EARLIER, holds: 'Figures no template prints' }] : P3_TABS
  const badge = (g: P3Group): { t: string; tone: 'good' | 'warn' | 'neutral' } | null => {
    if (g === 'earlier') return null
    if (g === 'qual') return qual.data ? { t: `${qual.data.authored} of ${qual.data.total_rows}`, tone: qual.data.authored === qual.data.total_rows ? 'good' : 'warn' } : null
    const secs = of(g).sections
    if (secs.some(s => s.rows.some(r => (r.cells ?? []).some(c => c.supply && common.supplied[suppliedKey(c.supply.key, c.supply.member)])))) return { t: 'In progress', tone: 'good' }
    return g !== 'phys' && secs.some(s => (s.col_sources ?? []).includes('integrated')) ? { t: 'Awaiting your systems', tone: 'warn' } : { t: 'Calculated', tone: 'neutral' }
  }
  return (
    <div>
      <div className="flex items-center gap-1.5 px-1 pb-2"><FormName annex={annex} />
        <InfoButton compact details={{ title: 'The four groups', sections: P3_TABS.map(t => ({ heading: t.label, body: t.holds })) }} /></div>
      <div className="flex gap-1.5 flex-wrap border-b border-[var(--color-line)] mb-3" role="tablist">
        {tabs.map(t => {
          const b = badge(t.k), on = tab === t.k
          return (
            <button key={t.k} role="tab" aria-selected={on} onClick={() => setTab(t.k)}
              className={`px-4 pt-2.5 pb-2.5 rounded-t-lg border border-b-0 transition flex items-center gap-2.5 whitespace-nowrap ${on ? 'bg-[var(--color-panel)] border-[var(--color-line)] -mb-px' : 'border-transparent hover:bg-[var(--color-bg-2)]'}`}>
              <span className={`text-[13px] font-medium ${on ? 'text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>{t.label}</span>
              {b && <StatusChip tone={b.tone} label={b.t} />}
            </button>)
        })}
      </div>
      {tab === 'qual' && (common.canEdit ? <P3Qualitative entityId={entityId} periodEnd={common.periodEnd} />
        : of('qual').sections.length ? <AnnexView annex={of('qual')} hideName {...common} />
        : <Card className="p-4 mt-3 text-[12.5px] text-[var(--color-mute)]">This filing was prepared before the qualitative tables were frozen with it.</Card>)}
      {tab !== 'qual' && <AnnexView annex={of(tab)} hideName {...common} />}
    </div>
  )
}

// Pillar 3 qualitative Tables 1 to 3: free text the institution writes for one institution and reference date. A draft
// freezes the text when it is prepared or refreshed; once out of draft the form shows the frozen copy.
function P3Qualitative({ entityId, periodEnd }: { entityId: string | null; periodEnd: string | null }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['p3-qualitative', entityId, periodEnd], queryFn: () => api.get<QData>(qualUrl(entityId, periodEnd)) })
  const d = q.data
  if (!d) return null
  return (
    <Card className="p-0 overflow-hidden mt-3">
      <div className="px-4 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <span className="text-[13px] text-[var(--color-ink)]">Qualitative disclosures</span>
          <InfoButton compact details={{ title: 'Qualitative disclosures', sections: [
            { heading: HEADING.shows, body: `The text you write for Tables 1 to 3 and the narrative of Template 1, for this filing's institution and its reference date (${d.period_end}).` },
            { heading: HEADING.read, body: 'The text is frozen with the draft when it is refreshed.' }] }} />
        </div>
        <StatusChip tone={d.authored === d.total_rows ? 'good' : 'warn'} label={`${d.authored} of ${d.total_rows} written`} />
      </div>
      {d.tables.map(t => {
        let lastGroup = ''
        return (
          <div key={t.table} className="border-b border-[var(--color-line)] last:border-0">
            <div className="px-4 py-2 bg-[var(--color-bg-2)] text-[12px] font-medium text-[var(--color-ink)]">{t.title}</div>
            <div className="divide-y divide-[var(--color-line-2)]">
              {t.rows.map(r => {
                const showGroup = r.group !== lastGroup; lastGroup = r.group
                const about = [...(r.required_when ? [{ heading: 'When it is required', body: r.required_when }] : []), ...(r.basis ? [{ heading: 'Legal basis', body: r.basis }] : [])]
                return (
                  <div key={r.key}>
                    {showGroup && <div className="px-4 pt-2.5 pb-1 text-[11px] font-medium text-[var(--color-sky)]">{r.group}</div>}
                    <div className="px-4 py-2">
                      <div className="text-[12.5px] text-[var(--color-mute)] mb-1 flex items-start gap-1.5"><span className="text-[11px] text-[var(--color-faint)] shrink-0">{r.row}</span><span>{r.prompt}</span>
                        {about.length > 0 && <InfoButton compact details={{ title: r.prompt, sections: about }} />}</div>
                      <QCell row={r} entityId={entityId} periodEnd={periodEnd} onSaved={() => qc.invalidateQueries({ queryKey: ['p3-qualitative'] })} />
                    </div>
                  </div>)
              })}
            </div>
          </div>)
      })}
    </Card>
  )
}

function QCell({ row, entityId, periodEnd, onSaved }: { row: QRow; entityId: string | null; periodEnd: string | null; onSaved: () => void }) {
  const [val, setVal] = useState(row.value)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const save = async () => {
    if (val === row.value) return
    setSaving(true); setSaved(false)
    try { await api.patch('/v1/filings/qualitative/p3esg', { values: { [row.key]: val }, undertaking: entityId ?? 'organisation', period_end: periodEnd ?? undefined }); setSaved(true); onSaved() }
    catch { toast.error('Could not save this disclosure.') } finally { setSaving(false) }
  }
  return (
    <div>
      <textarea value={val} onChange={e => { setVal(e.target.value); setSaved(false) }} onBlur={save} rows={2} placeholder="Write this disclosure…" aria-label={row.prompt}
        className="w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)] resize-y" />
      <div className="text-[11px] mt-0.5 h-3">{saving ? <span className="text-[var(--color-faint)]">Saving…</span> : saved ? <span style={{ color: 'var(--color-good)' }}>Saved</span> : null}</div>
    </div>
  )
}

// The interpretations the regulation leaves to the organisation, as frozen with this filing (inside its fingerprint).
function Elections({ e }: { e: Election[] }) {
  const [open, setOpen] = useState(false)
  const stated = e.filter(x => x.stated).length
  return (
    <Card className="p-4">
      <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open} className="flex w-full items-center justify-between gap-3 text-left">
        <span className="flex items-center gap-2"><Scale size={15} className="text-[var(--color-blue)]" /><span className="text-[13.5px] font-medium text-[var(--color-ink)]">Your interpretations</span></span>
        <StatusChip tone={stated === e.length ? 'good' : 'warn'} label={`${stated} of ${e.length} stated`} />
      </button>
      {open && <div className="mt-2 divide-y divide-[var(--color-line-2)]">{e.map(x => (
        <div key={x.key} className="flex justify-between gap-4 py-1.5 text-[12.5px]">
          <span className="text-[var(--color-mute)]">{x.label}</span>
          <span className="text-right">{x.value_label == null ? <span className="text-[var(--color-warn)]">Not stated</span> : x.value_label}<span className="text-[var(--color-faint)]"> · {x.stated ? 'stated' : 'default'}</span></span>
        </div>))}</div>}
    </Card>
  )
}
