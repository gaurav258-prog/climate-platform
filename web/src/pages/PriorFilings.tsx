import { useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceDot } from 'recharts'
import { UploadCloud, FileCheck2, Trash2, Lock, ChevronRight, X, TrendingUp, AlertTriangle, FileText, Download, ShieldCheck } from 'lucide-react'
import { api, ApiError, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, SectionHead, Button, PageHeader } from '../components/ui'
import ReportTabs from '../components/ReportTabs'

// Prior filings — bring in ESG reports already filed and accepted. Upload the submitted file itself;
// the engine reads it into its reported lines, the preparer confirms them, and the figures are stored as
// the organisation's reported track record for trends and follow-up questions.

interface Figure {
  figure_id: string; template_ref: string | null; datapoint_key: string | null; label: string
  value_num: number | null; value_text: string | null; unit: string | null
  read_method: string; confirmed: boolean
}
interface Filing {
  filing_id: string; framework: string; framework_label: string; period_label: string
  entity_name: string | null; file_format: string; original_filename: string; status: string
  n_lines: number | null; uploaded_at: string | null; confirmed_at: string | null
  basis_note?: string | null; file_sha256?: string | null; figures?: Figure[]
}
interface Framework { key: string; label: string }
interface TrendPoint { period: string; value: number; unit: string | null; basis_note: string | null; basis_break: boolean }
interface ProjPoint { period: string; value: number; projected: boolean }
interface Series {
  framework: string; datapoint_key: string; label: string; points: TrendPoint[]; basis_changed: boolean
  projection: ProjPoint[]; proj_method: string | null; proj_reliable: boolean
}

const FMT: Record<string, string> = { xbrl: 'XBRL', ixbrl: 'iXBRL', excel: 'Excel', pdf: 'PDF' }
// compact axis/label formatter — handles EUR/tCO2e magnitudes and sub-1 ratios alike
const compact = (n: number) => {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}bn`
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}m`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}k`
  if (a > 0 && a < 10) return n.toFixed(3).replace(/\.?0+$/, '')
  return n.toLocaleString()
}

export default function PriorFilings() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [framework, setFramework] = useState('')
  const [period, setPeriod] = useState('')
  const [entity, setEntity] = useState('')
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<Filing | null>(null)          // the report just read, awaiting confirm
  const [edits, setEdits] = useState<Record<string, { value_num?: number; drop?: boolean; datapoint_key?: string }>>({})
  const [basis, setBasis] = useState('')

  const [seriesKey, setSeriesKey] = useState('')
  const [horizon, setHorizon] = useState(3)   // projection years beyond the last filed value
  const [detailId, setDetailId] = useState<string | null>(null)   // a confirmed filing opened cell-by-cell

  const fw = useQuery({ queryKey: ['pf-frameworks'], queryFn: () => api.get<{ frameworks: Framework[] }>('/v1/prior-filings/frameworks') })
  const list = useQuery({ queryKey: ['pf-list'], queryFn: () => api.get<{ filings: Filing[] }>('/v1/prior-filings') })
  const trends = useQuery({ queryKey: ['pf-trends', horizon], queryFn: () => api.get<{ series: Series[] }>(`/v1/prior-filings/trends?horizon_years=${horizon}`) })
  const detail = useQuery({ enabled: !!detailId, queryKey: ['pf-detail', detailId], queryFn: () => api.get<Filing>(`/v1/prior-filings/${detailId}`) })
  const dps = useQuery({ enabled: !!draft, queryKey: ['pf-dps', draft?.framework], queryFn: () => api.get<{ datapoints: Framework[] }>(`/v1/prior-filings/datapoints/${draft!.framework}`) })
  const datapointOpts = dps.data?.datapoints ?? []
  const frameworks = fw.data?.frameworks ?? []
  if (!framework && frameworks.length) setFramework(frameworks[0].key)

  const series = trends.data?.series ?? []
  const selected = useMemo(() => series.find(s => s.datapoint_key === seriesKey) ?? series[0], [series, seriesKey])

  const pickFile = () => fileRef.current?.click()

  async function onFile(f: File) {
    if (!period.trim()) { toast.error('Enter the reporting period first.'); return }
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', f); fd.append('framework', framework); fd.append('period_label', period.trim())
      if (entity.trim()) fd.append('entity_name', entity.trim())
      const d = await api.post<Filing>('/v1/prior-filings/upload', fd)
      setDraft(d); setEdits({}); setBasis(d.basis_note ?? '')
    } catch (e) {
      toast.error(e instanceof ApiError ? String((e.body as { message?: string })?.message ?? 'Could not read that file.') : 'Upload failed.')
    } finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }

  async function confirm() {
    if (!draft) return
    setBusy(true)
    try {
      const editList = Object.entries(edits).map(([figure_id, v]) => ({ figure_id, ...v }))
      await api.post(`/v1/prior-filings/${draft.filing_id}/confirm`, { edits: editList, basis_note: basis.trim() || null })
      toast.success(`${draft.framework_label} · ${draft.period_label} confirmed.`)
      setDraft(null); setEdits({})
      qc.invalidateQueries({ queryKey: ['pf-list'] }); qc.invalidateQueries({ queryKey: ['pf-trends'] })
    } catch (e) {
      toast.error(e instanceof ApiError ? String((e.body as { message?: string })?.message ?? 'Could not confirm.') : 'Confirm failed.')
    } finally { setBusy(false) }
  }

  async function discardDraft() {
    if (draft) { try { await api.del(`/v1/prior-filings/${draft.filing_id}`) } catch { /* noop */ } }
    setDraft(null); setEdits({})
  }

  async function remove(f: Filing) {
    if (!confirm2(`Remove ${f.framework_label} · ${f.period_label}?`)) return
    try {
      await api.del(`/v1/prior-filings/${f.filing_id}`)
      if (detailId === f.filing_id) setDetailId(null)
      qc.invalidateQueries({ queryKey: ['pf-list'] }); qc.invalidateQueries({ queryKey: ['pf-trends'] })
    } catch { toast.error('Could not remove the filing.') }
  }

  const kept = (draft?.figures ?? []).filter(fig => !edits[fig.figure_id]?.drop)
  const mapped = kept.filter(fig => fig.datapoint_key).length

  return (
    <div className="fadeup space-y-6">
      <ReportTabs />
      <PageHeader eyebrow="Reported history" title="Prior filings"
        lead="Bring in the ESG reports you have already filed and had accepted. Upload the report you submitted — it is read into its reported lines for you to confirm, then kept as your reported record for trends and follow-up questions." />

      {/* import */}
      {!draft && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead icon={UploadCloud}>Import a filing</SectionHead></div>
          <div className="p-5 space-y-4">
            <div className="flex flex-wrap gap-4">
              <label className="flex-1 min-w-[200px]">
                <div className="mono text-[10px] tracking-[0.14em] uppercase text-[var(--color-faint)] mb-1.5">Framework</div>
                <select value={framework} onChange={e => setFramework(e.target.value)}
                  className="w-full bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[13.5px] outline-none focus:border-[var(--color-sky)]">
                  {frameworks.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
                </select>
              </label>
              <label className="w-[140px]">
                <div className="mono text-[10px] tracking-[0.14em] uppercase text-[var(--color-faint)] mb-1.5">Reporting period</div>
                <input value={period} onChange={e => setPeriod(e.target.value)} placeholder="2023"
                  className="w-full bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[13.5px] outline-none focus:border-[var(--color-sky)]" />
              </label>
              <label className="flex-1 min-w-[200px]">
                <div className="mono text-[10px] tracking-[0.14em] uppercase text-[var(--color-faint)] mb-1.5">Reporting entity <span className="normal-case tracking-normal">(optional)</span></div>
                <input value={entity} onChange={e => setEntity(e.target.value)} placeholder="e.g. parent entity"
                  className="w-full bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[13.5px] outline-none focus:border-[var(--color-sky)]" />
              </label>
            </div>
            <button onClick={pickFile} disabled={busy || !framework}
              className="w-full border-[1.5px] border-dashed border-[var(--color-line-2)] rounded-xl bg-[var(--color-panel-2)] py-8 text-center hover:border-[var(--color-sky)] transition disabled:opacity-50">
              <UploadCloud size={22} className="mx-auto text-[var(--color-sky)]" />
              <div className="text-[14px] font-medium mt-2">{busy ? 'Reading the report…' : 'Choose the filed report'}</div>
              <div className="text-[12.5px] text-[var(--color-faint)] mt-1">XBRL / iXBRL is read automatically · a PDF or Excel is read and confirmed before saving</div>
            </button>
            <input ref={fileRef} type="file" accept=".xbrl,.xml,.html,.htm,.xhtml,.xlsx,.xls,.pdf" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }} />
          </div>
        </Card>
      )}

      {/* review & confirm the read report */}
      {draft && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
            <SectionHead icon={FileCheck2} hint={`${draft.period_label} · ${FMT[draft.file_format] ?? draft.file_format}`}>{draft.framework_label}</SectionHead>
            <button onClick={discardDraft} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]" title="Discard"><X size={17} /></button>
          </div>
          <div className="px-5 py-3 border-b border-[var(--color-line)] text-[12.5px] text-[var(--color-mute)]">
            {kept.length} reported {kept.length === 1 ? 'line' : 'lines'} read · {mapped} matched to a datapoint. Adjust any value, drop any line, then confirm.
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead><tr className="text-left">
                {['From the report', 'Datapoint', 'Value', 'Read', ''].map(h =>
                  <th key={h} className="mono text-[11px] tracking-[0.12em] uppercase text-[var(--color-faint)] font-medium px-4 py-2 border-b border-[var(--color-line)]">{h}</th>)}
              </tr></thead>
              <tbody>
                {(draft.figures ?? []).map(fig => {
                  const dropped = edits[fig.figure_id]?.drop
                  const ev = edits[fig.figure_id]?.value_num
                  return (
                    <tr key={fig.figure_id} className={`border-b border-[var(--color-line)] ${dropped ? 'opacity-40' : ''}`}>
                      <td className="px-4 py-2.5">
                        <div className={`text-[var(--color-ink)] ${dropped ? 'line-through' : ''}`}>{fig.label}</div>
                        {fig.template_ref && <div className="mono text-[10px] text-[var(--color-faint)]">{fig.template_ref}</div>}
                      </td>
                      <td className="px-4 py-2.5">
                        <select disabled={dropped}
                          value={edits[fig.figure_id]?.datapoint_key ?? fig.datapoint_key ?? ''}
                          onChange={e => setEdits(p => ({ ...p, [fig.figure_id]: { ...p[fig.figure_id], datapoint_key: e.target.value } }))}
                          className="max-w-[220px] bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-md px-2 py-1 text-[12px] text-[var(--color-mute)] outline-none focus:border-[var(--color-sky)] disabled:opacity-50">
                          <option value="">— unmatched —</option>
                          {datapointOpts.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
                        </select>
                      </td>
                      <td className="px-4 py-2.5">
                        {fig.value_num != null || ev != null ? (
                          <input type="number" defaultValue={fig.value_num ?? undefined} disabled={dropped}
                            onChange={e => setEdits(p => ({ ...p, [fig.figure_id]: { ...p[fig.figure_id], value_num: e.target.value === '' ? undefined : Number(e.target.value) } }))}
                            className="w-32 bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-md px-2 py-1 mono text-[12.5px] tabular-nums text-right outline-none focus:border-[var(--color-sky)]" />
                        ) : <span className="mono text-[12px] text-[var(--color-mute)]">{fig.value_text ?? '—'}</span>}
                        {fig.unit && <span className="mono text-[11px] text-[var(--color-faint)] ml-1.5">{fig.unit}</span>}
                      </td>
                      <td className="px-4 py-2.5"><span className="mono text-[10px] px-1.5 py-0.5 rounded bg-[color-mix(in_oklab,var(--color-sky)_12%,transparent)] text-[var(--color-sky)]">auto</span></td>
                      <td className="px-4 py-2.5 text-right">
                        <button onClick={() => setEdits(p => ({ ...p, [fig.figure_id]: { ...p[fig.figure_id], drop: !dropped } }))}
                          className="text-[var(--color-faint)] hover:text-[var(--color-bad)]" title={dropped ? 'Keep' : 'Drop line'}>
                          {dropped ? <ChevronRight size={14} /> : <Trash2 size={14} />}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="px-5 py-4 border-t border-[var(--color-line)] space-y-3">
            <label className="block">
              <div className="mono text-[10px] tracking-[0.14em] uppercase text-[var(--color-faint)] mb-1.5">Preparation basis <span className="normal-case tracking-normal">(optional — methodology, boundary for this period)</span></div>
              <input value={basis} onChange={e => setBasis(e.target.value)} placeholder="e.g. PCAF v2 · boundary excludes trading book"
                className="w-full bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
            </label>
            <div className="flex items-center gap-3">
              <Button onClick={confirm} disabled={busy}><Lock size={14} /> Confirm &amp; lock {draft.period_label}</Button>
              <button onClick={discardDraft} className="text-[13px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">Discard</button>
            </div>
          </div>
        </Card>
      )}

      {/* imported filings */}
      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead>Your filings</SectionHead></div>
        {list.isLoading ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">loading…</div>
          : (list.data?.filings ?? []).length === 0
            ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">No prior filings imported yet.</div>
            : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead><tr className="text-left">
                    {['Period', 'Framework', 'Entity', 'Format', 'Lines', 'Status', ''].map(h =>
                      <th key={h} className="mono text-[11px] tracking-[0.12em] uppercase text-[var(--color-faint)] font-medium px-4 py-2 border-b border-[var(--color-line)]">{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {(list.data?.filings ?? []).map(f => (
                      <tr key={f.filing_id} onClick={() => setDetailId(f.filing_id)}
                        className={`border-b border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)] transition ${detailId === f.filing_id ? 'bg-[var(--color-bg-2)]' : ''}`}>
                        <td className="px-4 py-2.5 mono tabular-nums text-[var(--color-ink)]">{f.period_label}</td>
                        <td className="px-4 py-2.5 text-[var(--color-mute)]">{f.framework_label}</td>
                        <td className="px-4 py-2.5 text-[var(--color-mute)]">{f.entity_name ?? '—'}</td>
                        <td className="px-4 py-2.5 mono text-[11px] text-[var(--color-faint)]">{FMT[f.file_format] ?? f.file_format}</td>
                        <td className="px-4 py-2.5 mono tabular-nums text-[var(--color-mute)]">{f.n_lines ?? '—'}</td>
                        <td className="px-4 py-2.5">
                          {f.status === 'confirmed'
                            ? <span className="inline-flex items-center gap-1 text-[12px] text-[var(--color-good)]"><Lock size={11} /> Confirmed</span>
                            : <span className="text-[12px] text-[var(--color-warn)]">Draft</span>}
                        </td>
                        <td className="px-4 py-2.5 text-right whitespace-nowrap">
                          <button onClick={e => { e.stopPropagation(); setDetailId(f.filing_id) }} className="text-[var(--color-faint)] hover:text-[var(--color-sky)] mr-3" title="Open"><ChevronRight size={15} /></button>
                          <button onClick={e => { e.stopPropagation(); remove(f) }} className="text-[var(--color-faint)] hover:text-[var(--color-bad)]" title="Remove"><Trash2 size={14} /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        <div className="px-5 py-3 border-t border-[var(--color-line)] text-[11.5px] text-[var(--color-faint)]">
          Reported figures are portfolio-level; trends are shown at reporting-line level.
        </div>
      </Card>

      {/* regulator follow-up — open any filing cell-by-cell, with the original file attached */}
      {detailId && detail.data && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
            <SectionHead icon={FileText} hint={`${detail.data.period_label} · ${FMT[detail.data.file_format] ?? detail.data.file_format}`}>{detail.data.framework_label}</SectionHead>
            <div className="flex items-center gap-3">
              <button onClick={() => download(`/v1/prior-filings/${detailId}/file`, detail.data!.original_filename).catch(() => toast.error('Could not download the file.'))}
                className="inline-flex items-center gap-1.5 mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-sky)]" title="Download the report exactly as filed">
                <Download size={13} /> Original file
              </button>
              <button onClick={() => setDetailId(null)} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]" title="Close"><X size={17} /></button>
            </div>
          </div>
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap gap-x-6 gap-y-1 text-[12px]">
            <span className="text-[var(--color-mute)]">Entity: <span className="text-[var(--color-ink)]">{detail.data.entity_name ?? '—'}</span></span>
            <span className="inline-flex items-center gap-1 text-[var(--color-good)]"><Lock size={11} /> {detail.data.status === 'confirmed' ? 'Confirmed' : 'Draft'}{detail.data.confirmed_at ? ` · ${detail.data.confirmed_at.slice(0, 10)}` : ''}</span>
            <span className="inline-flex items-center gap-1 text-[var(--color-faint)] mono text-[10.5px]" title={`SHA-256 of the submitted file: ${detail.data.file_sha256 ?? ''}`}><ShieldCheck size={11} /> {(detail.data.file_sha256 ?? '').slice(0, 12)}…</span>
          </div>
          {detail.data.basis_note && (
            <div className="px-5 py-2.5 border-b border-[var(--color-line)] text-[12px] text-[var(--color-mute)]">Preparation basis: <span className="text-[var(--color-ink)]">{detail.data.basis_note}</span></div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead><tr className="text-left">
                {['From the report', 'Datapoint', 'Value'].map(h =>
                  <th key={h} className="mono text-[11px] tracking-[0.12em] uppercase text-[var(--color-faint)] font-medium px-4 py-2 border-b border-[var(--color-line)]">{h}</th>)}
              </tr></thead>
              <tbody>
                {(detail.data.figures ?? []).map(fig => (
                  <tr key={fig.figure_id} className="border-b border-[var(--color-line)]">
                    <td className="px-4 py-2.5">
                      <div className="text-[var(--color-ink)]">{fig.label}</div>
                      {fig.template_ref && <div className="mono text-[10px] text-[var(--color-faint)]">{fig.template_ref}</div>}
                    </td>
                    <td className="px-4 py-2.5 text-[12px] text-[var(--color-mute)]">{fig.datapoint_key ?? <span className="text-[var(--color-faint)]">unmatched</span>}</td>
                    <td className="px-4 py-2.5 mono tabular-nums text-[var(--color-ink)] whitespace-nowrap">
                      {fig.value_num != null ? compact(fig.value_num) : (fig.value_text ?? '—')}
                      {fig.unit && fig.unit !== 'pure' && <span className="text-[var(--color-faint)] ml-1.5">{fig.unit}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-5 py-3 border-t border-[var(--color-line)] text-[11.5px] text-[var(--color-faint)]">
            The figures above are exactly as reported for {detail.data.period_label}; the original submitted file is retained for verification.
          </div>
        </Card>
      )}

      {/* reported history — a filed figure across the years you have confirmed */}
      {series.length > 0 && selected && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center justify-between gap-3">
            <SectionHead icon={TrendingUp} hint="your filed figures over time">Reported history</SectionHead>
            <select value={selected.datapoint_key} onChange={e => setSeriesKey(e.target.value)}
              className="bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-mute)] outline-none focus:border-[var(--color-sky)] max-w-[60%]">
              {series.map(s => <option key={s.datapoint_key} value={s.datapoint_key}>{s.label}</option>)}
            </select>
          </div>
          <div className="p-5">
            {selected.points.length < 2 ? (
              <div className="text-[13px] text-[var(--color-mute)]">
                One year on file — <span className="mono text-[var(--color-ink)]">{selected.points[0].period}: {compact(selected.points[0].value)}{selected.points[0].unit && selected.points[0].unit !== 'pure' ? ` ${selected.points[0].unit}` : ''}</span>. Import earlier years to see the trend.
              </div>
            ) : (() => {
              const unit = selected.points[0].unit && selected.points[0].unit !== 'pure' ? ` ${selected.points[0].unit}` : ''
              // one dataset: reported points carry `value`, projected years carry `proj`; the last reported
              // point also carries `proj` so the dashed line starts exactly where the solid line ends.
              const data: Record<string, number | string | boolean>[] = [
                ...selected.points.map(p => ({ period: p.period, value: p.value, basis_break: p.basis_break })),
                ...selected.projection.map(p => ({ period: p.period, proj: p.value })),
              ]
              if (selected.projection.length) {
                const lastP = selected.points[selected.points.length - 1]
                const anchor = data.find(r => r.period === lastP.period)
                if (anchor) anchor.proj = lastP.value
              }
              return (
              <>
                <div className="flex items-center justify-end gap-2 mb-2">
                  <span className="mono text-[10px] tracking-[0.14em] uppercase text-[var(--color-faint)]">Project</span>
                  <div className="flex gap-1 p-0.5 rounded-lg border border-[var(--color-line-2)]">
                    {[1, 3, 5].map(h => (
                      <button key={h} onClick={() => setHorizon(h)}
                        className={`px-2.5 py-1 rounded-md text-[11.5px] transition ${horizon === h ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>+{h}y</button>
                    ))}
                  </div>
                </div>
                <div className="h-[220px] -ml-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
                      <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="period" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} axisLine={{ stroke: 'var(--color-line-2)' }} tickLine={false} />
                      <YAxis tickFormatter={compact} width={54} tick={{ fontSize: 11, fill: 'var(--color-faint)' }} axisLine={false} tickLine={false} />
                      <Tooltip
                        contentStyle={{ background: 'var(--color-panel)', border: '1px solid var(--color-line-2)', borderRadius: 10, fontSize: 12 }}
                        labelStyle={{ color: 'var(--color-mute)' }}
                        formatter={(v, name) => [`${compact(Number(v))}${unit}`, name === 'proj' ? 'Projected' : 'Reported']} />
                      <Line type="monotone" dataKey="value" name="value" stroke="var(--color-sky)" strokeWidth={2.25} dot={{ r: 3, fill: 'var(--color-sky)' }} isAnimationActive={false} />
                      <Line type="monotone" dataKey="proj" name="proj" stroke="var(--color-mute)" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 2.5, fill: 'var(--color-mute)' }} connectNulls isAnimationActive={false} />
                      {selected.points.map((p, i) => p.basis_break && (
                        <ReferenceDot key={i} x={p.period} y={p.value} r={5} fill="var(--color-warn)" stroke="var(--color-bg-2)" strokeWidth={2} />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                {selected.projection.length > 0 && (
                  <div className="mt-2 text-[11.5px] text-[var(--color-faint)]">
                    <span className="inline-block w-4 border-t-2 border-dashed border-[var(--color-mute)] align-middle mr-1.5" />
                    Dashed = projected from your last filed value{selected.proj_method ? ` — ${selected.proj_method}` : ''}.
                  </div>
                )}
                {selected.basis_changed && (
                  <div className="mt-3 flex items-start gap-2 text-[12px] text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_10%,transparent)] border border-[color-mix(in_oklab,var(--color-warn)_35%,transparent)] rounded-lg px-3 py-2">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                    <div>
                      Preparation basis changed across these years — the marked points are not directly comparable, and the projection should be read as indicative.
                      <div className="mt-1 text-[var(--color-mute)]">
                        {selected.points.filter(p => p.basis_break).map(p => `${p.period}: ${p.basis_note || '—'}`).join(' · ')}
                      </div>
                    </div>
                  </div>
                )}
              </>
              )
            })()}
          </div>
        </Card>
      )}
    </div>
  )
}

// native confirm() shadowed by our confirm handler above — small wrapper keeps the browser dialog available
function confirm2(msg: string): boolean { return window.confirm(msg) }
