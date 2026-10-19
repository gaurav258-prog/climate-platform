import { useMemo, useRef, useState } from 'react'
import { useCurrencies } from '../components/MoneyDeclaration'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { UploadCloud, Trash2, ChevronRight, Loader2, FileText, ShieldCheck, Download, X } from 'lucide-react'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, SectionHead, PageHeader, StatGrid } from '../components/ui'
import ReportTabs from '../components/ReportTabs'
import { pressable } from '../lib/pressable'
import { HEADING, InfoButton } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import { errMessage } from '../components/intake/parts'
import { fmtDate } from '../components/filing/words'
import { DraftReview, History, StateBasis, FORMAT, compact, ref, th, unitOf, type Edit, type Filing, type Option, type Series } from '../components/priorfilings/parts'

// Prior filings — bring in ESG reports already filed and accepted. Upload the submitted file itself; the engine reads
// it into its reported lines, the preparer confirms them, and the figures are kept as the organisation's reported
// track record for trends and follow-up questions. Every refusal is the server's catalogue message.

const field = 'mt-1 w-full bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[13.5px] outline-none focus:border-[var(--color-sky)]'

export default function PriorFilings() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [framework, setFramework] = useState('')
  const [period, setPeriod] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [fileCcy, setFileCcy] = useState('')
  const currencies = useCurrencies()
  const [entity, setEntity] = useState('')
  const [undertaking, setUndertaking] = useState('')       // 'organisation' or a reporting entity — stated, never inferred
  const [stating, setStating] = useState<Filing | null>(null)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<Filing | null>(null)          // the report just read, awaiting confirm
  const [edits, setEdits] = useState<Record<string, Edit>>({})
  const [basis, setBasis] = useState('')
  const [seriesKey, setSeriesKey] = useState('')
  const [horizon, setHorizon] = useState(3)   // projection years beyond the last filed value
  const [detailId, setDetailId] = useState<string | null>(null)   // a confirmed filing opened figure by figure

  const fw = useQuery({ queryKey: ['pf-frameworks'], queryFn: () => api.get<{ frameworks: Option[] }>('/v1/prior-filings/frameworks') })
  const ents = useQuery({ queryKey: ['entities'], queryFn: () => api.get<{ entities: { entity_id: string; name: string; kind: string }[] }>('/v1/filings/entities') })
  const undertakings = (ents.data?.entities ?? []).filter(e => e.kind !== 'group')
  const nameOf = (id?: string | null) => id ? undertakings.find(e => e.entity_id === id)?.name ?? 'An entity' : 'The organisation'
  const list = useQuery({ queryKey: ['pf-list'], queryFn: () => api.get<{ filings: Filing[] }>('/v1/prior-filings') })
  const trends = useQuery({ queryKey: ['pf-trends', horizon], queryFn: () => api.get<{ series: Series[] }>(`/v1/prior-filings/trends?horizon_years=${horizon}`) })
  const detail = useQuery({ enabled: !!detailId, queryKey: ['pf-detail', detailId], queryFn: () => api.get<Filing>(`/v1/prior-filings/${detailId}`) })
  // an ESRS statement maps to the concepts its year's version prints — the period end chooses the version
  const dps = useQuery({ enabled: !!draft, queryKey: ['pf-dps', draft?.framework, draft?.period_end], queryFn: () => api.get<{ datapoints: Option[] }>(`/v1/prior-filings/datapoints/${draft!.framework}${draft!.period_end ? `?period_end=${draft!.period_end}` : ''}`) })
  const frameworks = fw.data?.frameworks ?? []
  if (!framework && frameworks.length) setFramework(frameworks[0].key)
  const filings = list.data?.filings ?? []
  const series = trends.data?.series ?? []
  const selected = useMemo(() => series.find(s => s.datapoint_key === seriesKey) ?? series[0], [series, seriesKey])
  const refresh = () => { qc.invalidateQueries({ queryKey: ['pf-list'] }); qc.invalidateQueries({ queryKey: ['pf-trends'] }) }

  async function onFile(f: File) {
    if (!period.trim()) { toast.error('Enter the reporting period first.'); return }
    if (!periodEnd) { toast.error('State the date the reporting period ends.'); return }
    if (!undertaking) { toast.error('State whom the filed report is for.'); return }
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', f); fd.append('framework', framework); fd.append('period_label', period.trim())
      if (entity.trim()) fd.append('entity_name', entity.trim())
      if (fileCcy) fd.append('currency', fileCcy)
      fd.append('period_end', periodEnd); fd.append('undertaking', undertaking)
      const d = await api.post<Filing>('/v1/prior-filings/upload', fd)
      setDraft(d); setEdits({}); setBasis(d.basis_note ?? '')
    } catch (e) {
      toast.error(errMessage(e, 'Could not read that file').label)
    } finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }

  async function confirm() {
    if (!draft) return
    setBusy(true)
    try {
      const editList = Object.entries(edits).map(([figure_id, v]) => ({ figure_id, ...v }))
      await api.post(`/v1/prior-filings/${draft.filing_id}/confirm`, { edits: editList, basis_note: basis.trim() || null })
      toast.success(`${draft.framework_label} · ${draft.period_label} confirmed.`)
      setDraft(null); setEdits({}); refresh()
    } catch (e) {
      toast.error(errMessage(e, 'Could not confirm').label)
    } finally { setBusy(false) }
  }

  async function discardDraft() {
    if (draft) { try { await api.del(`/v1/prior-filings/${draft.filing_id}`) } catch { /* nothing to remove */ } }
    setDraft(null); setEdits({})
  }

  async function remove(f: Filing) {
    if (!window.confirm(`Remove ${f.framework_label} · ${f.period_label}?`)) return
    try {
      await api.del(`/v1/prior-filings/${f.filing_id}`)
      if (detailId === f.filing_id) setDetailId(null)
      refresh()
    } catch (e) { toast.error(errMessage(e, 'Could not remove the filing').label) }
  }

  const confirmed = filings.filter(f => f.status === 'confirmed')
  const periods = new Set(confirmed.map(f => f.period_label)).size
  const unstated = filings.filter(f => !(f.undertaking_stated && f.period_end_stated)).length

  return (
    <div className="fadeup space-y-6">
      <ReportTabs />
      <PageHeader eyebrow="Reported history" title="Prior filings" lead="Your filed reports, read into figures for trends."
        about={[
          { heading: HEADING.read, body: 'Upload the report you submitted. It is read into its reported lines; you check them, match each to a figure, and confirm. Confirmed figures are kept as your reported record, with the original file, for trends and follow-up questions.' },
          { heading: HEADING.limits, body: 'Reported figures are at portfolio level; trends are drawn per reported line. Figures in different units are never added together.' }]} />

      {list.data && (
        <StatGrid cols={4} items={[
          { label: 'Filings on file', value: filings.length },
          { label: 'Confirmed', value: confirmed.length, accent: confirmed.length ? 'var(--color-good)' : undefined },
          { label: 'Years covered', value: periods },
          { label: 'Figures with a history', value: series.length },
        ]} />)}

      {stating && <StateBasis f={stating} undertakings={undertakings} onClose={() => setStating(null)} onDone={() => { setStating(null); refresh() }} />}

      {!draft && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-2">
            <SectionHead icon={UploadCloud}>Bring in a filing</SectionHead>
            <InfoButton compact details={{ title: 'Bring in a filing', sections: [
              { heading: HEADING.read, body: 'Say which report it is, its period and the date the period ends, and whom it is for — then choose the file. XBRL and iXBRL are read automatically; a PDF or Excel is read and checked by you before anything is kept.' },
              { heading: 'Period end', body: 'Required: its figures are matched to a later period by it, and money converts at its rate.' },
              { heading: 'Currency', body: 'The currency the filing reports money in. Needed when it writes amounts with a symbol several currencies share ($, £, ¥).' }] }} />
          </div>
          <div className="p-5 space-y-4">
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <label className="text-[12px] text-[var(--color-mute)]">Report
                <select value={framework} onChange={e => setFramework(e.target.value)} className={field}>
                  {frameworks.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
                </select></label>
              <label className="text-[12px] text-[var(--color-mute)]">Reporting period
                <input value={period} onChange={e => setPeriod(e.target.value)} placeholder="2023" className={field} /></label>
              <label className="text-[12px] text-[var(--color-mute)]">Period end
                <input type="date" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)} className={field} /></label>
              <label className="text-[12px] text-[var(--color-mute)]">Currency
                <select value={fileCcy} onChange={e => setFileCcy(e.target.value)} className={field}>
                  <option value="">As written in the file</option>{currencies.map(c => <option key={c} value={c}>{c}</option>)}</select></label>
              <label className="text-[12px] text-[var(--color-mute)]">Whom it is for
                <select value={undertaking} onChange={e => setUndertaking(e.target.value)} aria-label="Whom the filed report is for" className={field}>
                  <option value="">Choose</option><option value="organisation">The organisation</option>
                  {undertakings.map(e => <option key={e.entity_id} value={e.entity_id}>{e.name}</option>)}
                </select></label>
              <label className="text-[12px] text-[var(--color-mute)]">Name printed on it (optional)
                <input value={entity} onChange={e => setEntity(e.target.value)} placeholder="As the report names it" className={field} /></label>
            </div>
            <button onClick={() => fileRef.current?.click()} disabled={busy || !framework}
              className="w-full border-[1.5px] border-dashed border-[var(--color-line-2)] rounded-xl bg-[var(--color-panel-2)] py-8 text-center hover:border-[var(--color-sky)] transition disabled:opacity-50">
              {busy ? <Loader2 size={22} className="mx-auto text-[var(--color-sky)] animate-spin" /> : <UploadCloud size={22} className="mx-auto text-[var(--color-sky)]" />}
              <div className="text-[14px] font-medium mt-2">{busy ? 'Reading the report…' : 'Choose the filed report'}</div>
              <div className="text-[12.5px] text-[var(--color-faint)] mt-1">XBRL, iXBRL, PDF or Excel</div>
            </button>
            <input ref={fileRef} type="file" accept=".xbrl,.xml,.html,.htm,.xhtml,.xlsx,.xls,.pdf" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }} />
          </div>
        </Card>
      )}

      {draft && <DraftReview draft={draft} options={dps.data?.datapoints ?? []} edits={edits} setEdits={setEdits} basis={basis} setBasis={setBasis}
        busy={busy} onConfirm={confirm} onDiscard={discardDraft} />}

      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-2">
          <SectionHead>Your filings</SectionHead>
          {unstated > 0 && <StatusChip tone="warn" label={`${unstated} to complete`} />}
        </div>
        {list.isLoading ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">Loading…</div>
          : filings.length === 0 ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">No prior filings brought in yet.</div>
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead><tr className="text-left text-[11.5px] text-[var(--color-faint)]">
                  {['Period', 'Report', 'Whom for', 'Format', 'Lines', 'Status', ''].map(h => <th key={h} className="font-normal px-4 py-2 border-b border-[var(--color-line)]">{h}</th>)}
                </tr></thead>
                <tbody>
                  {filings.map(f => (
                    <tr key={f.filing_id} {...pressable(() => setDetailId(f.filing_id), { row: true })}
                      className={`border-b border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)] transition ${detailId === f.filing_id ? 'bg-[var(--color-bg-2)]' : ''}`}>
                      <td className="px-4 py-2.5 tabular-nums text-[var(--color-ink)]">{f.period_label}</td>
                      <td className="px-4 py-2.5 text-[var(--color-mute)]">{f.framework_label}</td>
                      <td className="px-4 py-2.5 text-[var(--color-mute)]">{f.undertaking_stated && f.period_end_stated
                        ? <>{nameOf(f.entity_id)} <span className="text-[11.5px] text-[var(--color-faint)] tabular-nums">· {f.period_end}</span></>
                        : <button type="button" onClick={e => { e.stopPropagation(); setStating(f) }} className="text-[12px] text-[var(--color-warn)] hover:underline">State whom for and period end</button>}</td>
                      <td className="px-4 py-2.5 text-[12px] text-[var(--color-faint)]">{FORMAT[f.file_format] ?? 'File'}</td>
                      <td className="px-4 py-2.5 tabular-nums text-[var(--color-mute)]">{f.n_lines ?? '—'}</td>
                      <td className="px-4 py-2.5"><StatusChip tone={f.status === 'confirmed' ? 'good' : 'warn'} label={f.status === 'confirmed' ? 'Confirmed' : 'Draft'} /></td>
                      <td className="px-4 py-2.5 text-right whitespace-nowrap">
                        <button onClick={e => { e.stopPropagation(); setDetailId(f.filing_id) }} className="text-[var(--color-faint)] hover:text-[var(--color-sky)] mr-3" aria-label="Open"><ChevronRight size={15} /></button>
                        <button onClick={e => { e.stopPropagation(); remove(f) }} className="text-[var(--color-faint)] hover:text-[var(--color-bad)]" aria-label="Remove"><Trash2 size={14} /></button>
                      </td>
                    </tr>))}
                </tbody>
              </table>
            </div>)}
      </Card>

      {detailId && detail.data && <FilingDetail f={detail.data} onClose={() => setDetailId(null)} />}

      {series.length > 0 && selected && <History series={series} selected={selected} onSelect={setSeriesKey} horizon={horizon} setHorizon={setHorizon} />}
    </div>
  )
}

// One confirmed filing, figure by figure, with the original file — for a regulator's follow-up question.
function FilingDetail({ f, onClose }: { f: Filing; onClose: () => void }) {
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-2 flex-wrap">
        <SectionHead icon={FileText}>{f.framework_label}</SectionHead>
        <StatusChip tone="neutral" label={f.period_label} />
        <StatusChip tone={f.status === 'confirmed' ? 'good' : 'warn'} label={f.status === 'confirmed' ? `Confirmed${f.confirmed_at ? ` ${fmtDate(f.confirmed_at)}` : ''}` : 'Draft'} />
        {f.file_sha256 && <span className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)]"><ShieldCheck size={12} /> File fingerprint
          <InfoButton compact details={{ title: 'File fingerprint', sections: [
            { heading: HEADING.shows, body: 'A fingerprint of the file exactly as submitted. The same file always gives the same fingerprint, so anyone can confirm the kept file is the one filed.' },
            { heading: 'Fingerprint', body: f.file_sha256 }] }} /></span>}
        <div className="ml-auto flex items-center gap-3">
          <button onClick={() => download(`/v1/prior-filings/${f.filing_id}/file`, f.original_filename).catch(e => toast.error(errMessage(e, 'Could not download the file').label))}
            className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={13} /> Original file</button>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]" aria-label="Close"><X size={17} /></button>
        </div>
      </div>
      <div className="px-5 py-2.5 border-b border-[var(--color-line)] flex flex-wrap items-center gap-x-5 gap-y-1 text-[12.5px] text-[var(--color-mute)]">
        <span>Name printed: <span className="text-[var(--color-ink)]">{f.entity_name ?? '—'}</span></span>
        {f.basis_note && <span className="inline-flex items-center gap-1">Preparation basis stated
          <InfoButton compact details={{ title: 'Preparation basis', sections: [{ heading: HEADING.shows, body: f.basis_note }] }} /></span>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead><tr><th className={th}>From the report</th><th className={th}>Figure</th><th className={`${th} text-right`}>Value</th></tr></thead>
          <tbody>
            {(f.figures ?? []).map(fig => (
              <tr key={fig.figure_id} className="border-b border-[var(--color-line)]">
                <td className="px-4 py-2.5 text-[var(--color-ink)]">{fig.label} {ref(fig)}</td>
                <td className="px-4 py-2.5 text-[12.5px] text-[var(--color-mute)]">{fig.datapoint_label ?? <span className="text-[var(--color-faint)]">Unmatched</span>}</td>
                <td className="px-4 py-2.5 tabular-nums text-right text-[var(--color-ink)] whitespace-nowrap">
                  {fig.value_num != null ? compact(fig.value_num) : (fig.value_text ?? '—')}<span className="text-[var(--color-faint)]">{unitOf(fig.unit)}</span></td>
              </tr>))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
