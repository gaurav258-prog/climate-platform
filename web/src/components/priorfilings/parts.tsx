import { useState } from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceDot } from 'recharts'
import { Trash2, Lock, Undo2, X, TrendingUp, FileCheck2 } from 'lucide-react'
import { toast } from '../../lib/toast'
import { api } from '../../lib/api'
import { Card, SectionHead, Button } from '../ui'
import { HEADING, InfoButton, messageDetails, type Message } from '../Details'
import { Dialog } from '../Dialog'
import { StatusChip } from '../StatusChip'
import { Said, Segments, errMessage, plural } from '../intake/parts'

// The parts of Prior filings (pages/PriorFilings.tsx): reviewing a report just read, the reported history with its
// projection, and stating an older upload's undertaking and period end.

export interface Figure {
  figure_id: string; template_ref: string | null; datapoint_key: string | null; datapoint_label?: string | null; label: string
  value_num: number | null; value_text: string | null; unit: string | null; read_method: string; confirmed: boolean
}
export interface Filing {
  filing_id: string; framework: string; framework_label: string; period_label: string
  entity_name: string | null; file_format: string; original_filename: string; status: string
  n_lines: number | null; uploaded_at: string | null; confirmed_at: string | null
  basis_note?: string | null; file_sha256?: string | null; figures?: Figure[]; period_end?: string | null
  entity_id?: string | null; undertaking_stated?: boolean; period_end_stated?: boolean
}
export interface Option { key: string; label: string }
interface TrendPoint { period: string; value: number | null; unit: string | null; basis_note: string | null; basis_break: boolean; unit_break?: boolean; mixed_units?: string[]; msg?: Message }
interface ProjPoint { period: string; value: number; projected: boolean }
export interface Series {
  framework: string; datapoint_key: string; label: string; points: TrendPoint[]; basis_changed: boolean; unit_changed?: boolean; mixed_units?: boolean
  projection: ProjPoint[]; proj_msg: Message | null; proj_reliable: boolean
}
export type Edit = { value_num?: number; drop?: boolean; datapoint_key?: string; unit?: string }

export const FORMAT: Record<string, string> = { xbrl: 'XBRL', ixbrl: 'iXBRL', excel: 'Excel', pdf: 'PDF' }
// compact axis/label formatter — handles EUR/tCO2e magnitudes and sub-1 ratios alike
export const compact = (n: number | null) => {
  if (n == null) return '—'
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}bn`
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}m`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}k`
  if (a > 0 && a < 10) return n.toFixed(3).replace(/\.?0+$/, '')
  return n.toLocaleString()
}
export const unitOf = (u: string | null | undefined) => u && u !== 'pure' ? ` ${u}` : ''
export const ref = (f: Figure) => f.template_ref
  ? <InfoButton compact details={{ title: f.label, sections: [{ heading: 'Where the report prints it', body: f.template_ref }] }} /> : null
export const th = 'text-[11.5px] text-[var(--color-faint)] font-normal px-4 py-2 border-b border-[var(--color-line)] text-left'

// A report just read, line by line: match each line to a figure, correct a value or its unit, drop a line — then lock.
export function DraftReview({ draft, options, edits, setEdits, basis, setBasis, busy, onConfirm, onDiscard }: {
  draft: Filing; options: Option[]; edits: Record<string, Edit>; setEdits: (f: (p: Record<string, Edit>) => Record<string, Edit>) => void
  basis: string; setBasis: (v: string) => void; busy: boolean; onConfirm: () => void; onDiscard: () => void
}) {
  const kept = (draft.figures ?? []).filter(fig => !edits[fig.figure_id]?.drop)
  const mapped = kept.filter(fig => edits[fig.figure_id]?.datapoint_key ?? fig.datapoint_key).length
  const set = (id: string, v: Edit) => setEdits(p => ({ ...p, [id]: { ...p[id], ...v } }))
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-3 flex-wrap">
        <SectionHead icon={FileCheck2}>{draft.framework_label}</SectionHead>
        <StatusChip tone="neutral" label={draft.period_label} />
        <StatusChip tone="neutral" label={FORMAT[draft.file_format] ?? 'File'} />
        <InfoButton compact details={{ title: 'Check what was read', sections: [
          { heading: HEADING.shows, body: 'Every reported line read from your file, and the figure each one was matched to.' },
          { heading: HEADING.read, body: 'Match a line to a figure, correct a value or its unit, or drop a line. Figures in different units are never added together. Confirming locks the filing as your reported record.' }] }} />
        <button onClick={onDiscard} className="ml-auto text-[var(--color-faint)] hover:text-[var(--color-ink)]" aria-label="Discard"><X size={17} /></button>
      </div>
      <div className="px-5 py-3 border-b border-[var(--color-line)]">
        <Segments parts={[{ n: mapped, tone: 'good', label: 'matched to a figure' }, { n: kept.length - mapped, tone: 'warn', label: 'unmatched' },
          { n: (draft.figures?.length ?? 0) - kept.length, tone: 'faint', label: 'dropped' }]} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead><tr><th className={th}>From the report</th><th className={th}>Figure</th><th className={th}>Value</th><th className={th} /></tr></thead>
          <tbody>
            {(draft.figures ?? []).map(fig => {
              const dropped = edits[fig.figure_id]?.drop
              return (
                <tr key={fig.figure_id} className={`border-b border-[var(--color-line)] ${dropped ? 'opacity-40' : ''}`}>
                  <td className="px-4 py-2.5"><span className={`text-[var(--color-ink)] ${dropped ? 'line-through' : ''}`}>{fig.label}</span> {ref(fig)}</td>
                  <td className="px-4 py-2.5">
                    <select disabled={dropped} aria-label="Figure it reports" value={edits[fig.figure_id]?.datapoint_key ?? fig.datapoint_key ?? ''}
                      onChange={e => set(fig.figure_id, { datapoint_key: e.target.value })}
                      className="max-w-[240px] bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-md px-2 py-1 text-[12px] text-[var(--color-mute)] outline-none focus:border-[var(--color-sky)] disabled:opacity-50">
                      <option value="">Unmatched</option>
                      {options.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
                    </select>
                  </td>
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    {fig.value_num != null || edits[fig.figure_id]?.value_num != null ? (
                      <input type="number" defaultValue={fig.value_num ?? undefined} disabled={dropped} aria-label="Value"
                        onChange={e => set(fig.figure_id, { value_num: e.target.value === '' ? undefined : Number(e.target.value) })}
                        className="w-32 bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-md px-2 py-1 text-[12.5px] tabular-nums text-right outline-none focus:border-[var(--color-sky)]" />
                    ) : <span className="text-[12px] text-[var(--color-mute)]">{fig.value_text ?? '—'}</span>}
                    <input defaultValue={fig.unit ?? ''} disabled={dropped} placeholder="unit" aria-label="Unit"
                      onChange={e => set(fig.figure_id, { unit: e.target.value })}
                      className="text-[11.5px] ml-1.5 w-16 bg-transparent border-b border-[var(--color-line-2)] text-[var(--color-faint)] outline-none focus:border-[var(--color-sky)]" />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => set(fig.figure_id, { drop: !dropped })} aria-label={dropped ? 'Keep the line' : 'Drop the line'}
                      className="text-[var(--color-faint)] hover:text-[var(--color-bad)]">{dropped ? <Undo2 size={14} /> : <Trash2 size={14} />}</button>
                  </td>
                </tr>)
            })}
          </tbody>
        </table>
      </div>
      <div className="px-5 py-4 border-t border-[var(--color-line)] space-y-3">
        <label className="block">
          <span className="text-[12px] text-[var(--color-mute)] inline-flex items-center gap-1.5">Preparation basis (optional)
            <InfoButton compact details={{ title: 'Preparation basis', sections: [{ heading: HEADING.shows, body: 'The methodology and boundary this period was prepared on — for example the accounting standard, or what the boundary leaves out. A change between years is flagged on the history, so a trend is never drawn as continuous across it.' }] }} /></span>
          <input value={basis} onChange={e => setBasis(e.target.value)} aria-label="Preparation basis"
            className="mt-1 w-full bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        </label>
        <div className="flex items-center gap-3">
          <Button onClick={onConfirm} disabled={busy}><Lock size={14} /> Confirm and lock {draft.period_label}</Button>
          <button onClick={onDiscard} className="text-[13px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">Discard</button>
        </div>
      </div>
    </Card>
  )
}

// A filed figure across the years you have confirmed, with a projection from the last filed value.
export function History({ series, selected, onSelect, horizon, setHorizon }: {
  series: Series[]; selected: Series; onSelect: (key: string) => void; horizon: number; setHorizon: (h: number) => void
}) {
  const pts = selected.points
  const last = pts[pts.length - 1]
  const unit = unitOf(last?.unit)
  // one dataset: reported points carry `value`, projected years carry `proj`; the last reported point also carries
  // `proj` so the dashed line starts exactly where the solid line ends
  const data: Record<string, number | string | boolean | null>[] = [
    ...pts.map(p => ({ period: p.period, value: p.value, basis_break: p.basis_break })),
    ...selected.projection.map(p => ({ period: p.period, proj: p.value })),
  ]
  if (selected.projection.length && last) {
    const anchor = data.find(r => r.period === last.period)
    if (anchor) anchor.proj = last.value
  }
  const unitNotes = pts.filter(p => p.msg)
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center gap-3">
        <SectionHead icon={TrendingUp}>Reported history</SectionHead>
        <InfoButton compact details={{ title: 'Reported history', sections: [
          { heading: HEADING.shows, body: 'A figure you filed, across the years you have confirmed, and where it would go if it kept its own past trend.' },
          { heading: HEADING.read, body: 'The solid line is what you reported; the dashed line is the projection. An amber point marks a year whose preparation basis differs from the year before.' },
          ...(selected.proj_msg ? messageDetails(selected.proj_msg).sections : [])] }} />
        <select value={selected.datapoint_key} onChange={e => onSelect(e.target.value)} aria-label="Figure"
          className="ml-auto bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-mute)] outline-none focus:border-[var(--color-sky)] max-w-[60%]">
          {series.map(s => <option key={s.datapoint_key} value={s.datapoint_key}>{s.label}</option>)}
        </select>
      </div>
      <div className="p-5 space-y-3">
        {pts.length < 2 ? (
          <div className="text-[13px] text-[var(--color-mute)]">One year on file — <span className="tabular-nums text-[var(--color-ink)]">{pts[0]?.period}: {compact(pts[0]?.value ?? null)}{unitOf(pts[0]?.unit)}</span>. Bring in earlier years to see the trend.</div>
        ) : (<>
          <div className="flex items-center justify-end gap-2">
            <span className="text-[12px] text-[var(--color-faint)]">Project</span>
            <div className="flex gap-1 p-0.5 rounded-lg border border-[var(--color-line-2)]">
              {[1, 3, 5].map(h => (
                <button key={h} onClick={() => setHorizon(h)} aria-pressed={horizon === h}
                  className={`px-2.5 py-1 rounded-md text-[11.5px] transition ${horizon === h ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{plural(h, 'year')}</button>))}
            </div>
          </div>
          <div className="h-[220px] -ml-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} axisLine={{ stroke: 'var(--color-line-2)' }} tickLine={false} />
                <YAxis tickFormatter={compact} width={54} tick={{ fontSize: 11, fill: 'var(--color-faint)' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: 'var(--color-panel)', border: '1px solid var(--color-line-2)', borderRadius: 10, fontSize: 12 }}
                  labelStyle={{ color: 'var(--color-mute)' }} formatter={(v, name) => [`${compact(Number(v))}${unit}`, name === 'proj' ? 'Projected' : 'Reported']} />
                <Line type="monotone" dataKey="value" name="value" stroke="var(--color-sky)" strokeWidth={2.25} dot={{ r: 3, fill: 'var(--color-sky)' }} isAnimationActive={false} />
                <Line type="monotone" dataKey="proj" name="proj" stroke="var(--color-mute)" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 2.5, fill: 'var(--color-mute)' }} connectNulls isAnimationActive={false} />
                {pts.map((p, i) => p.basis_break && <ReferenceDot key={i} x={p.period} y={p.value ?? undefined} r={5} fill="var(--color-warn)" stroke="var(--color-bg-2)" strokeWidth={2} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
          {selected.proj_msg && (
            <div className="text-[11.5px] text-[var(--color-faint)] flex items-center gap-1.5">
              <span className="inline-block w-4 border-t-2 border-dashed border-[var(--color-mute)]" /><Said m={selected.proj_msg} /></div>)}
        </>)}
        {unitNotes.length > 0 && (
          <div className="flex flex-wrap gap-2">{unitNotes.map(p => <span key={p.period} className="text-[12px] inline-flex items-center gap-1.5">
            <StatusChip tone="warn" label={p.period} /><Said m={p.msg!} tone="warn" /></span>)}</div>)}
        {selected.basis_changed && (
          <div className="text-[12px] flex items-center gap-1.5" style={{ color: 'var(--color-warn)' }}>Preparation basis changed across these years
            <InfoButton compact details={{ title: 'Preparation basis changed', sections: [
              { heading: HEADING.shows, body: 'The marked years were prepared on a different basis from the year before, so they are not directly comparable, and the projection should be read as indicative.' },
              ...pts.filter(p => p.basis_break).map(p => ({ heading: p.period, body: p.basis_note || 'No basis stated' }))] }} /></div>)}
      </div>
    </Card>
  )
}

// A filing uploaded before its undertaking and period end had to be stated (E123): stated once, with an audit entry.
export function StateBasis({ f, undertakings, onClose, onDone }: {
  f: Filing; undertakings: { entity_id: string; name: string }[]; onClose: () => void; onDone: () => void
}) {
  const [who, setWho] = useState(f.undertaking_stated ? (f.entity_id ?? 'organisation') : '')
  const [end, setEnd] = useState(f.period_end_stated ? (f.period_end ?? '') : '')
  const [busy, setBusy] = useState(false)
  const box = 'mt-1 w-full bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-3 py-2 text-[13.5px] outline-none focus:border-[var(--color-sky)]'
  async function save() {
    setBusy(true)
    try { await api.post(`/v1/prior-filings/${f.filing_id}/basis`, { undertaking: who, period_end: end }); toast.success('Stated.'); onDone() }
    catch (e) { toast.error(errMessage(e, 'Not saved').label) }
    finally { setBusy(false) }
  }
  return (
    <Dialog title={`${f.framework_label} · ${f.period_label}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-[12.5px] text-[var(--color-mute)] m-0">Its figures are compared with a later period only once both are stated{f.entity_name ? ` (the report names “${f.entity_name}”)` : ''}. They are stated once, and recorded in the audit log.</p>
        <label className="block text-[12px] text-[var(--color-mute)]">Whom it is for
          <select className={box} value={who} onChange={e => setWho(e.target.value)} aria-label="Whom the filed report is for">
            <option value="">Choose</option><option value="organisation">The organisation</option>
            {undertakings.map(e => <option key={e.entity_id} value={e.entity_id}>{e.name}</option>)}
          </select></label>
        <label className="block text-[12px] text-[var(--color-mute)]">Period end
          <input type="date" className={box} value={end} onChange={e => setEnd(e.target.value)} /></label>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy || !who || !end}>{busy ? 'Saving…' : 'State'}</Button>
        </div>
      </div>
    </Dialog>
  )
}
