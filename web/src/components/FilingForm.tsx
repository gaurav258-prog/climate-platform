import { useState, Fragment } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, FileSpreadsheet, Pencil, Check, X, Clock } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card } from './ui'
import { hazardLabel } from '../lib/hazards'
import { toast } from '../lib/toast'

// The final form — the frozen disclosure, shown two ways over ONE set of figures:
//   • Official form — the regulator's actual Annex / template layout (SFDR RTS Annex I Table 1, EU-Taxonomy
//     Art.8 GAR summary, ESRS E1 …) as it will be submitted.
//   • Datapoints — the flat labelled list, each cell showing its source (book / calc).
// A preparer can propose a MANUAL override of a numeric cell (with a reason) from either view; it needs
// 4-eyes approval before it lands, and an approved cell is visually distinct with its full provenance. The
// frozen snapshot itself is never mutated — overrides are a separate audited layer merged at read time.

interface Override { reason: string; by: string; at: string; approved_by: string; approved_at: string }
interface Pending { value: number; reason: string; by: string }
interface Dp {
  key: string; label: string; value: number | string | null; fmt: string; unit: string | null; source: string; note: string | null
  manual?: boolean; original_value?: number | null; override?: Override; pending?: Pending
}
interface Group { group: string; datapoints: Dp[] }
interface AnnexCell { text?: string; dp?: Dp; num?: boolean; source?: string }
interface AnnexRow { type: 'row' | 'subheader'; label?: string; cells?: AnnexCell[] }
interface AnnexSection { title: string; note: string | null; columns: string[]; col_sources?: string[]; rows: AnnexRow[]; key?: string }
interface Annex { official_name: string; authority: string | null; official_form: string | null; legal_basis: string | null; form_url: string | null; sections: AnnexSection[] }
interface Form { framework: string; label: string; period_label: string; status: string; snapshot_version: number | null; official_form_url: string | null; n_manual: number; n_pending: number; groups: Group[]; annex: Annex | null }

const eur = (n: number) => n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
function fmt(v: number | string | null, f: string): string {
  if (v == null) return '—'
  if (typeof v === 'string') return v
  switch (f) {
    case 'eur': return eur(v)
    case 'pct': return `${v}%`
    case 'tco2e': return Math.round(v).toLocaleString('en-GB')
    default: return Number.isInteger(v) ? v.toLocaleString('en-GB') : v.toLocaleString('en-GB', { maximumFractionDigits: 2 })
  }
}
const dpLabel = (d: Dp) => d.key.startsWith('hazard.') ? hazardLabel(d.label) : d.label
const EDITABLE_STATUS = ['draft', 'returned', 'in_review', 'approved']  // never edit a submitted/accepted/superseded filing

export default function FilingForm({ filingId }: { filingId: string }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['filing-form', filingId], queryFn: () => api.get<Form>(`/v1/filings/${filingId}/form`) })
  const cellsQ = useQuery({ queryKey: ['p3-cells'], queryFn: () => api.get<{ cells: Record<string, string> }>('/v1/filings/structured/p3esg-cells'),
    enabled: q.data?.framework === 'bank_p3esg' })
  const [edit, setEdit] = useState<string | null>(null)
  const [view, setView] = useState<'official' | 'datapoints'>('official')
  const d = q.data
  if (!d || d.groups.length === 0) return null
  const canEdit = (profile?.permissions ?? []).includes('approvals.create') && EDITABLE_STATUS.includes(d.status)
  const refresh = () => { qc.invalidateQueries({ queryKey: ['filing-form', filingId] }); qc.invalidateQueries({ queryKey: ['approvals'] }) }
  const editProps = { filingId, canEdit, edit, setEdit, onDone: () => { setEdit(null); refresh() } }
  const hasAnnex = !!d.annex && d.annex.sections.length > 0

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Final form · as it will be submitted
          {d.n_manual > 0 && <span className="ml-2" style={{ color: 'var(--color-warn)' }}>· {d.n_manual} manual</span>}
          {d.n_pending > 0 && <span className="ml-2" style={{ color: 'var(--color-sky)' }}>· {d.n_pending} pending 4-eyes</span>}
        </div>
        <div className="flex items-center gap-2">
          {hasAnnex && (
            <div className="flex gap-0.5 p-0.5 rounded-lg border border-[var(--color-line-2)]">
              {(['official', 'datapoints'] as const).map(v => (
                <button key={v} onClick={() => setView(v)} className={`px-2 py-0.5 rounded-md mono text-[10px] uppercase tracking-wide transition ${view === v ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)] hover:text-[var(--color-ink)]'}`}>{v === 'official' ? 'Official form' : 'Datapoints'}</button>
              ))}
            </div>
          )}
          {d.official_form_url && <a href={d.official_form_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 mono text-[10px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={11} /> official form <ExternalLink size={10} /></a>}
        </div>
      </div>

      {view !== 'official'
        ? <DatapointList groups={d.groups} {...editProps} />
        : d.framework === 'bank_p3esg'
          ? <P3FormTabs annex={d.annex!} cells={cellsQ.data?.cells ?? {}} onCells={() => qc.invalidateQueries({ queryKey: ['p3-cells'] })} {...editProps} />
          : hasAnnex
            ? <AnnexView annex={d.annex!} cells={cellsQ.data?.cells ?? {}} onCells={() => qc.invalidateQueries({ queryKey: ['p3-cells'] })} {...editProps} />
            : <DatapointList groups={d.groups} {...editProps} />}

      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2"><span className="text-[var(--color-sky)]">book</span> = uploaded book · <span className="text-[var(--color-mute)]">calc</span> = golden source · <span style={{ color: 'var(--color-warn)' }}>manual</span> = analyst override (4-eyes, audited)</div>
    </div>
  )
}

type EditProps = { filingId: string; canEdit: boolean; edit: string | null; setEdit: (k: string | null) => void; onDone: () => void }

// ── the regulator's official Annex / template layout ──────────────────────────────────────────────────────
const SRC_META: Record<string, { label: string; short: string; color: string }> = {
  computed:   { label: 'Tellumen-computed',     short: 'Tellumen', color: 'var(--color-sky)' },
  integrated: { label: 'Integrated (bank systems)', short: 'Integrated', color: 'var(--color-warn)' },
  manual:     { label: 'Manual (you author)',   short: 'Manual', color: 'var(--color-viz, #a78bfa)' },
}
function SrcDot({ source }: { source?: string }) {
  const m = source ? SRC_META[source] : undefined
  if (!m) return null
  return <span className="inline-block w-[6px] h-[6px] rounded-full align-middle" style={{ background: m.color }} title={m.label} />
}
function SrcLegend({ sources }: { sources: string[] }) {
  const uniq = Array.from(new Set(sources.filter(Boolean)))
  if (!uniq.length) return null
  return (
    <div className="px-4 py-1.5 flex flex-wrap gap-x-4 gap-y-1 border-b border-[var(--color-line)] bg-[var(--color-bg-2)]">
      {uniq.map(s => (
        <span key={s} className="inline-flex items-center gap-1.5 mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">
          <SrcDot source={s} />{SRC_META[s]?.label ?? s}
        </span>
      ))}
    </div>
  )
}

// A bank-fed ('integrated') cell with no connected feed shows '—'; a preparer may enter an aggregate value
// manually here (audited overlay on the frozen annex). Saved values carry a violet 'manual' dot.
function ManualCell({ cellKey, saved, placeholder, canEdit, onSaved }:
  { cellKey: string; saved?: string; placeholder: string; canEdit: boolean; onSaved: () => void }) {
  const [val, setVal] = useState(saved ?? '')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    if ((val || '') === (saved ?? '')) return
    setBusy(true)
    try { await api.patch('/v1/filings/structured/p3esg-cells', { key: cellKey, value: val }); onSaved() }
    catch { toast.error('Could not save this entry.'); setVal(saved ?? '') } finally { setBusy(false) }
  }
  if (!canEdit) return <span className="inline-flex items-center gap-1 justify-end w-full">
    {saved ? <><span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--color-viz,#a78bfa)' }} />{saved}</> : <span className="text-[var(--color-faint)]">{placeholder}</span>}</span>
  return (
    <input value={val} onChange={e => setVal(e.target.value)} onBlur={save} disabled={busy}
      placeholder={placeholder} title="Manual entry — no bank feed connected for this cell"
      className="w-16 text-right mono tabular-nums text-[11px] bg-transparent border-0 border-b border-dashed border-[var(--color-line)] px-0.5 py-0 text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)] focus:border-solid placeholder:text-[var(--color-faint)]"
      style={saved ? { color: 'var(--color-viz,#a78bfa)' } : undefined} />
  )
}

// The 13 Pillar 3 forms grouped into 4 tabs by the EBA's own risk themes, so a preparer lands on the group they
// own (qualitative author / risk team / taxonomy team) instead of scrolling one 13-form page. bank_p3esg only.
type P3Group = 'qual' | 'trans' | 'phys' | 'tax'
function p3Group(title: string): P3Group {
  if (/\btable\b/i.test(title)) return 'qual'
  const m = title.match(/template[s]?\s*(\d+)/i)
  const n = m ? parseInt(m[1], 10) : 0
  if (n >= 1 && n <= 4) return 'trans'
  if (n === 5) return 'phys'
  return 'tax'   // Templates 6–10 (GAR, BTAR, other actions)
}
const P3_TABS: { k: P3Group; label: string; sub: string }[] = [
  { k: 'qual', label: 'Qualitative', sub: 'Tables 1–3' },
  { k: 'trans', label: 'Transition risk', sub: 'Templates 1–4' },
  { k: 'phys', label: 'Physical risk', sub: 'Template 5' },
  { k: 'tax', label: 'Taxonomy & GAR', sub: 'Templates 6–10' },
]

function P3FormTabs({ annex, cells, onCells, ...ep }: { annex: Annex; cells: Record<string, string>; onCells: () => void } & EditProps) {
  const [tab, setTab] = useState<P3Group>('qual')
  const qual = useQuery({ queryKey: ['p3-qualitative'], queryFn: () => api.get<QData>('/v1/filings/qualitative/p3esg') })
  const sectionsOf = (g: P3Group): Annex => ({ ...annex, sections: annex.sections.filter(s => p3Group(s.title) === g) })

  const badge = (g: P3Group): { t: string; c: string } | null => {
    if (g === 'qual') return qual.data ? { t: `${qual.data.authored}/${qual.data.total_rows}`, c: 'var(--color-viz,#a78bfa)' } : null
    const secs = annex.sections.filter(s => p3Group(s.title) === g)
    const keys = secs.map(s => s.key).filter(Boolean) as string[]
    const filled = keys.length > 0 && Object.keys(cells).some(ck => keys.some(k => ck.startsWith(k + '.')))
    if (filled) return { t: 'in progress', c: 'var(--color-good,#34d399)' }
    const hasIntegrated = secs.some(s => (s.col_sources ?? []).includes('integrated'))
    if (g === 'phys') return { t: 'engine', c: 'var(--color-sky)' }
    return hasIntegrated ? { t: 'feed pending', c: 'var(--color-warn)' } : { t: 'engine', c: 'var(--color-sky)' }
  }

  return (
    <div>
      <div className="px-1 pb-2">
        <div className="text-[13px] text-[var(--color-ink)]">{annex.official_name}</div>
        <div className="mono text-[9.5px] text-[var(--color-faint)] mt-0.5">{[annex.official_form, annex.authority].filter(Boolean).join(' · ')}</div>
      </div>
      {/* form-group tabs — each holds only its templates, with a readiness badge */}
      <div className="flex gap-1.5 flex-wrap border-b border-[var(--color-line)] mb-3">
        {P3_TABS.map(t => {
          const b = badge(t.k); const on = tab === t.k
          return (
            <button key={t.k} onClick={() => setTab(t.k)}
              className={`text-left px-4 pt-2.5 pb-3 rounded-t-lg border border-b-0 transition ${on ? 'bg-[var(--color-panel)] border-[var(--color-line)] -mb-px' : 'border-transparent hover:bg-[var(--color-bg-2)]'}`}>
              <div className="flex items-center gap-2.5 whitespace-nowrap">
                <span className={`text-[13px] font-medium ${on ? 'text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>{t.label}</span>
                {b && <span className="mono text-[8.5px] px-1.5 py-0.5 rounded-full shrink-0" style={{ color: b.c, background: 'color-mix(in oklab, ' + b.c + ' 14%, transparent)' }}>{b.t}</span>}
              </div>
              <div className="mono text-[8.5px] uppercase tracking-wide text-[var(--color-faint)] mt-0.5">{t.sub}</div>
            </button>
          )
        })}
      </div>
      {tab === 'qual' && <P3Qualitative canEdit={ep.canEdit} />}
      {tab === 'trans' && <AnnexView annex={sectionsOf('trans')} cells={cells} onCells={onCells} hideName {...ep} />}
      {tab === 'phys' && <AnnexView annex={sectionsOf('phys')} cells={cells} onCells={onCells} hideName {...ep} />}
      {tab === 'tax' && <div className="space-y-3"><AnnexView annex={sectionsOf('tax')} cells={cells} onCells={onCells} hideName {...ep} /><P3Template10 canEdit={ep.canEdit} /></div>}
    </div>
  )
}

function AnnexView({ annex, cells: cellVals, onCells, hideName, ...ep }: { annex: Annex; cells: Record<string, string>; onCells: () => void; hideName?: boolean } & EditProps) {
  return (
    <Card className="p-0 overflow-hidden">
      {!hideName && (
        <div className="px-4 py-3 border-b border-[var(--color-line)]">
          <div className="text-[13px] text-[var(--color-ink)]">{annex.official_name}</div>
          <div className="mono text-[9.5px] text-[var(--color-faint)] mt-0.5">{[annex.official_form, annex.authority].filter(Boolean).join(' · ')}</div>
        </div>
      )}
      {annex.sections.map((s, si) => (
        <div key={si} className={si > 0 ? 'border-t border-[var(--color-line)]' : ''}>
          <div className="px-4 py-2 bg-[var(--color-bg-2)] mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{s.title}</div>
          {s.col_sources && <SrcLegend sources={s.col_sources} />}
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-left">
                  {s.columns.map((c, ci) => {
                    const src = s.col_sources?.[ci]
                    return (
                      <th key={ci} className={`px-4 py-1.5 mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] font-medium align-bottom ${ci >= s.columns.length - 1 ? 'text-right' : ''}`}>
                        <div className={`flex items-center gap-1 ${ci >= s.columns.length - 1 ? 'justify-end' : ''}`}>{src && <SrcDot source={src} />}<span>{c}</span></div>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {s.rows.map((r, ri) => {
                  if (r.type === 'subheader') return (
                    <tr key={ri}><td colSpan={s.columns.length} className="px-4 pt-3 pb-1 mono text-[10px] uppercase tracking-wide text-[var(--color-sky)]">{r.label}</td></tr>
                  )
                  const cells = r.cells ?? []
                  const dpCells = cells.map(c => c.dp).filter(Boolean) as Dp[]
                  const dpCell = dpCells.find(d => d.key === ep.edit) ?? dpCells[0]
                  const editingHere = !!dpCell && ep.edit === dpCell.key
                  return (
                    <Fragment key={ri}>
                      <tr className="border-t border-[var(--color-line)]" style={dpCell?.manual ? { background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' } : undefined}>
                        {cells.map((c, ci) => {
                          const last = ci === cells.length - 1
                          if (c.dp) return <td key={ci} className="px-4 py-1.5 text-right align-top"><CellValue dp={c.dp} {...ep} /></td>
                          // an integrated / manual grid cell in a keyed section → preparer can enter a value by hand
                          if (s.key && (c.source === 'integrated' || c.source === 'manual')) {
                            const ck = `${s.key}.${ri}.${ci}`
                            return <td key={ci} className="px-4 py-1.5 align-top text-right"><ManualCell cellKey={ck} saved={cellVals[ck]} placeholder={c.text ?? '—'} canEdit={ep.canEdit} onSaved={onCells} /></td>
                          }
                          return <td key={ci} className={`px-4 py-1.5 align-top ${c.num ? 'text-right mono tabular-nums text-[11.5px] text-[var(--color-ink)]' : last ? 'text-right mono text-[11px] text-[var(--color-faint)]' : 'text-[var(--color-ink)]'}`}>{c.text}</td>
                        })}
                      </tr>
                      {editingHere && dpCell && (
                        <tr><td colSpan={s.columns.length} className="px-4 pb-2"><OverrideEditor filingId={ep.filingId} dp={dpCell} onClose={() => ep.setEdit(null)} onDone={ep.onDone} /></td></tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          {s.note && <div className="px-4 py-2 mono text-[9.5px] text-[var(--color-faint)] leading-relaxed border-t border-[var(--color-line)]">{s.note}</div>}
        </div>
      ))}
    </Card>
  )
}

// a value cell — the merged datapoint with its source/manual badge, a pending marker, and (when editable) the
// override pencil. Shared by the official form and the datapoint list.
function CellValue({ dp, canEdit, edit, setEdit }: { dp: Dp } & EditProps) {
  const editable = canEdit && dp.fmt !== 'text' && typeof dp.value === 'number'
  return (
    <span className="inline-flex items-center gap-1.5 justify-end">
      {dp.pending && <span className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded inline-flex items-center gap-1" style={{ color: 'var(--color-sky)', background: 'color-mix(in oklab, var(--color-sky) 14%, transparent)' }}><Clock size={9} /> pending → {fmt(dp.pending.value, dp.fmt)}</span>}
      {dp.manual
        ? <span title={`Manual override · was ${fmt(dp.original_value ?? null, dp.fmt)} · ${dp.override?.reason} · by ${dp.override?.by}, approved by ${dp.override?.approved_by}`}
            className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 16%, transparent)' }}>manual ⓘ</span>
        : dp.value != null && <span className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: dp.source === 'book' ? 'var(--color-sky)' : 'var(--color-mute)', background: 'color-mix(in oklab, var(--color-line) 60%, transparent)' }}>{dp.source === 'book' ? 'book' : 'calc'}</span>}
      <span className="mono text-[12.5px] tabular-nums" style={{ color: dp.manual ? 'var(--color-warn)' : 'var(--color-ink)' }}>{fmt(dp.value, dp.fmt)}</span>
      {dp.unit && <span className="mono text-[9px] text-[var(--color-faint)]">{dp.unit}</span>}
      {editable && edit !== dp.key && <button onClick={() => setEdit(dp.key)} title="Propose a manual override (4-eyes)" className="text-[var(--color-faint)] hover:text-[var(--color-sky)]"><Pencil size={11} /></button>}
    </span>
  )
}

// ── the flat labelled datapoint list ──────────────────────────────────────────────────────────────────────
function DatapointList({ groups, ...ep }: { groups: Group[] } & EditProps) {
  return (
    <Card className="p-0 overflow-hidden">
      {groups.map((g, gi) => (
        <div key={gi} className={gi > 0 ? 'border-t border-[var(--color-line)]' : ''}>
          <div className="px-4 py-2 bg-[var(--color-bg-2)] mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{g.group}</div>
          <div className="divide-y divide-[var(--color-line)]">
            {g.datapoints.map(dp => {
              const isEditing = ep.edit === dp.key
              return (
                <div key={dp.key} className="px-4 py-2 text-[12.5px]" style={dp.manual ? { background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' } : undefined}>
                  <div className="flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <span className="text-[var(--color-ink)]">{dpLabel(dp)}</span>
                      {dp.note && <span className="mono text-[10px] text-[var(--color-faint)] ml-1.5">· {dp.note}</span>}
                    </div>
                    <CellValue dp={dp} {...ep} />
                  </div>
                  {isEditing && <OverrideEditor filingId={ep.filingId} dp={dp} onClose={() => ep.setEdit(null)} onDone={ep.onDone} />}
                  {dp.manual && dp.override && (
                    <div className="mono text-[10px] text-[var(--color-faint)] mt-1">was {fmt(dp.original_value ?? null, dp.fmt)} · “{dp.override.reason}” · {dp.override.by} → approved {dp.override.approved_by}</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </Card>
  )
}

function OverrideEditor({ filingId, dp, onClose, onDone }: { filingId: string; dp: Dp; onClose: () => void; onDone: () => void }) {
  const [value, setValue] = useState(String(typeof dp.value === 'number' ? dp.value : ''))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const save = async () => {
    const v = Number(value)
    if (!isFinite(v)) { setErr('Enter a number.'); return }
    if (!reason.trim()) { setErr('A reason is required.'); return }
    setBusy(true); setErr(null)
    try {
      await api.post(`/v1/filings/${filingId}/overrides`, { datapoint_key: dp.key, value: v, reason: reason.trim() })
      onDone()
    } catch (e) { setErr(e instanceof ApiError ? String((e.body as { message?: string })?.message ?? e.message) : 'Could not propose the override.') }
    finally { setBusy(false) }
  }
  const box = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
  return (
    <div className="mt-2 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] p-2.5 space-y-2 text-left">
      {err && <div className="text-[11.5px] text-[var(--color-bad)]">{err}</div>}
      <div className="mono text-[10px] text-[var(--color-faint)]">Override · {dpLabel(dp)}</div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="mono text-[10px] text-[var(--color-faint)]">value ({dp.fmt}):</span>
        <input value={value} onChange={e => setValue(e.target.value)} className={`${box} w-40 mono`} placeholder="new value (raw)" />
        <input value={reason} onChange={e => setReason(e.target.value)} className={`${box} flex-1 min-w-[200px]`} placeholder="Reason (required · audited)" />
        <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-sky)] text-[var(--color-on-accent)] px-3 py-1.5 text-[12px] font-medium disabled:opacity-50"><Check size={13} /> Propose</button>
        <button onClick={onClose} className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)]"><X size={13} /></button>
      </div>
      <div className="mono text-[9.5px] text-[var(--color-faint)]">This needs a second pair of eyes to approve before it lands on the form; the original stays on record.</div>
    </div>
  )
}

// ── Pillar 3 ESG qualitative Tables 1-3 (Annex XXXIX) — free-format narrative the institution AUTHORS in-app.
// These forms have nothing to compute; the user types them here and they are versioned + attested with the filing.
interface QRow { key: string; row: string; group: string; prompt: string; value: string }
interface QTable { table: string; title: string; rows: QRow[] }
interface QData { tables: QTable[]; total_rows: number; authored: number }

function P3Qualitative({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['p3-qualitative'], queryFn: () => api.get<QData>('/v1/filings/qualitative/p3esg') })
  const d = q.data
  if (!d) return null
  return (
    <Card className="p-0 overflow-hidden mt-3">
      <div className="px-4 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
        <div>
          <div className="text-[13px] text-[var(--color-ink)]">Qualitative ESG risk disclosures · Tables 1–3 (Annex XXXIX)</div>
          <div className="mono text-[9.5px] text-[var(--color-faint)] mt-0.5">Free-format narrative · <span style={{ color: 'var(--color-sky)' }}>you author</span> · versioned + attested with the filing</div>
        </div>
        <div className="mono text-[10px] text-[var(--color-faint)]">{d.authored}/{d.total_rows} authored</div>
      </div>
      {d.tables.map(t => {
        let lastGroup = ''
        return (
          <div key={t.table} className="border-b border-[var(--color-line)] last:border-0">
            <div className="px-4 py-2 bg-[var(--color-bg-2)] mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{t.title}</div>
            <div className="divide-y divide-[var(--color-line-2)]">
              {t.rows.map(r => {
                const showGroup = r.group !== lastGroup; lastGroup = r.group
                return (
                  <div key={r.key}>
                    {showGroup && <div className="px-4 pt-2.5 pb-1 mono text-[10px] uppercase tracking-wide text-[var(--color-sky)]">{r.group}</div>}
                    <div className="px-4 py-2">
                      <div className="text-[12px] text-[var(--color-mute)] mb-1"><span className="mono text-[10px] text-[var(--color-faint)] mr-1.5">({r.row})</span>{r.prompt}</div>
                      <QCell row={r} canEdit={canEdit} onSaved={() => qc.invalidateQueries({ queryKey: ['p3-qualitative'] })} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </Card>
  )
}

function QCell({ row, canEdit, onSaved }: { row: QRow; canEdit: boolean; onSaved: () => void }) {
  const [val, setVal] = useState(row.value)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const save = async () => {
    if (val === row.value) return
    setSaving(true); setSaved(false)
    try { await api.patch('/v1/filings/qualitative/p3esg', { values: { [row.key]: val } }); setSaved(true); onSaved() }
    catch { toast.error('Could not save this disclosure.') } finally { setSaving(false) }
  }
  if (!canEdit) return <div className="text-[12.5px] text-[var(--color-ink)] whitespace-pre-wrap">{val || <span className="text-[var(--color-faint)] italic">Not authored yet.</span>}</div>
  return (
    <div>
      <textarea value={val} onChange={e => { setVal(e.target.value); setSaved(false) }} onBlur={save} rows={2}
        placeholder="Author this disclosure…"
        className="w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)] resize-y" />
      <div className="mono text-[9px] mt-0.5 h-3">{saving ? <span className="text-[var(--color-faint)]">saving…</span> : saved ? <span style={{ color: 'var(--color-good)' }}>✓ saved</span> : null}</div>
    </div>
  )
}

// ── Pillar 3 ESG Template 10 (Annex XXXIX) — the preparer-authored register of climate-mitigating instruments
// NOT covered by the EU Taxonomy (green/sustainability bonds + specialised green lending). Every field is manual.
interface T10Field { key: string; label: string; options: string[] | null }
interface T10Data { fields: T10Field[]; rows: Record<string, string>[]; count: number }

function P3Template10({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['p3-template10'], queryFn: () => api.get<T10Data>('/v1/filings/structured/p3esg-template10') })
  const [rows, setRows] = useState<Record<string, string>[] | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const d = q.data
  const model = rows ?? d?.rows ?? []
  if (!d) return null

  const commit = async (next: Record<string, string>[]) => {
    setRows(next); setSaved(false); setSaving(true)
    try { await api.patch('/v1/filings/structured/p3esg-template10', { rows: next }); setSaved(true); qc.invalidateQueries({ queryKey: ['p3-template10'] }) }
    catch { toast.error('Could not save the Template 10 register.') } finally { setSaving(false) }
  }
  const addRow = (kind: string) => commit([...model, { kind, instrument: '', counterparty: '', gross_eur: '', risk: '', qualitative: '' }])
  const editRow = (i: number, key: string, val: string) => { const n = model.map((r, j) => j === i ? { ...r, [key]: val } : r); setRows(n); setSaved(false) }
  const delRow = (i: number) => commit(model.filter((_, j) => j !== i))
  const cols = d.fields.filter(f => f.key !== 'kind')

  return (
    <Card className="p-0 overflow-hidden mt-3">
      <div className="px-4 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
        <div>
          <div className="text-[13px] text-[var(--color-ink)]">Template 10 — other climate-mitigating actions not covered by the EU Taxonomy</div>
          <div className="mono text-[9.5px] text-[var(--color-faint)] mt-0.5">Green / sustainability bonds + specialised green lending · <span style={{ color: 'var(--color-viz, #a78bfa)' }}>you author</span> · versioned + attested with the filing</div>
        </div>
        <div className="mono text-[10px] text-[var(--color-faint)]">{model.length} instrument{model.length === 1 ? '' : 's'}</div>
      </div>
      {['Bond', 'Loan'].map(kind => {
        const group = model.map((r, i) => ({ r, i })).filter(x => x.r.kind === kind)
        return (
          <div key={kind} className="border-b border-[var(--color-line)] last:border-0">
            <div className="px-4 py-2 bg-[var(--color-bg-2)] flex items-center justify-between">
              <span className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{kind === 'Bond' ? 'Bonds (banking book)' : 'Loans (banking book)'}</span>
              {canEdit && <button onClick={() => addRow(kind)} className="mono text-[10px] text-[var(--color-sky)] hover:underline">+ add {kind.toLowerCase()}</button>}
            </div>
            {group.length === 0
              ? <div className="px-4 py-2.5 mono text-[10px] text-[var(--color-faint)] italic">No {kind.toLowerCase()} instruments recorded.</div>
              : group.map(({ r, i }) => (
                <div key={i} className="px-4 py-2.5 border-t border-[var(--color-line-2)] grid gap-2" style={{ gridTemplateColumns: '1.4fr 1fr 0.8fr 1fr 1.6fr auto' }}>
                  {cols.map(f => (
                    <div key={f.key}>
                      <div className="mono text-[8.5px] uppercase tracking-wide text-[var(--color-faint)] mb-0.5">{f.label}</div>
                      {canEdit
                        ? <input value={r[f.key] ?? ''} onChange={e => editRow(i, f.key, e.target.value)} onBlur={() => rows && commit(rows)}
                            placeholder="—" className="w-full rounded-md border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[11.5px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]" />
                        : <div className="text-[11.5px] text-[var(--color-ink)]">{r[f.key] || <span className="text-[var(--color-faint)]">—</span>}</div>}
                    </div>
                  ))}
                  {canEdit && <button onClick={() => delRow(i)} className="mono text-[10px] text-[var(--color-faint)] hover:text-[var(--color-bad,#fb7185)] self-end pb-1" title="Remove">✕</button>}
                </div>
              ))}
          </div>
        )
      })}
      <div className="px-4 py-1.5 mono text-[9px] h-5">{saving ? <span className="text-[var(--color-faint)]">saving…</span> : saved ? <span style={{ color: 'var(--color-good)' }}>✓ saved</span> : null}</div>
    </Card>
  )
}
