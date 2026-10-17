import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Columns3, FileText, ListX, SlidersHorizontal, Upload } from 'lucide-react'
import { api, apiDetail, apiMessage } from '../../lib/api'
import { SCENARIO_LABEL, scenarioLabel } from '../../lib/hazards'
import { toast } from '../../lib/toast'
import { Button, SectionHead } from '../../components/ui'
import { CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { HBar } from '../../components/Charts'
import { StatusChip } from '../../components/StatusChip'
import { DetailsBody, HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../../components/Details'
import { SplitBar } from './visuals'
import { lastYear, periodsWith, yearLabel } from './periods'
import type { Field, Kind, Report, Saved, Spec } from './types'

// One file's way in: choose it, see at a glance how many rows are valid, then save. Matching columns, the stated basis
// and the rows with problems open in a drawer; every message comes from the server's catalogue with its explanation.
const HORIZONS = ['current', '2030', '2050', '2100']

type Basis = Record<string, string>
const failure = (e: unknown, fallback: string): Message => ({ label: apiMessage(e, fallback), detail: apiDetail(e) })
const panel = 'w-full max-w-md h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5'
const control = 'mt-1 w-full rounded-lg border bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none'
const chip = 'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] transition hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]'

export function FileCheck({ orgId, kind, spec, onFile, onSaved }: {
  orgId: string; kind: Kind; spec: Spec; onFile: string[]; onSaved: () => void
}) {
  const qc = useQueryClient()
  const fields = kind === 'submission' ? spec.submission.cell_fields : spec.granular.row_fields
  const [file, setFile] = useState<File | null>(null)
  const [rep, setRep] = useState<Report | null>(null)
  const [mapping, setMapping] = useState<Record<string, string | null>>({})
  const [changed, setChanged] = useState(false)
  const [basis, setBasis] = useState<Basis>({})
  const [period, setPeriod] = useState(`FY${lastYear}`)
  const [busy, setBusy] = useState<'check' | 'save' | null>(null)
  const [err, setErr] = useState<Message | null>(null)
  const [open, setOpen] = useState<'columns' | 'problems' | null>(null)

  const check = async (f: File, m?: Record<string, string | null>) => {
    setBusy('check'); setErr(null)
    try {
      const fd = new FormData(); fd.append('file', f); if (m) fd.append('mapping', JSON.stringify(m))
      const r = await api.post<Report>(`/v1/supervisor/intake/${orgId}/${kind}/validate`, fd)
      setRep(r); setMapping(r.mapping); setChanged(false)
    } catch (e) { setRep(null); setErr(failure(e, 'The file could not be checked')) } finally { setBusy(null) }
  }
  const save = async () => {
    if (!file || !rep?.ok || changed) return
    setBusy('save'); setErr(null)
    try {
      const fd = new FormData(); fd.append('file', file); fd.append('mapping', JSON.stringify(mapping)); fd.append('period_label', period)
      if (kind === 'submission') fd.append('basis', JSON.stringify(basis))
      const r = await api.post<Saved>(`/v1/supervisor/intake/${orgId}/${kind}`, fd)
      toast.success(r.message.label)
      setFile(null); setRep(null); setBasis({})
      await qc.invalidateQueries({ queryKey: ['sup-intake', orgId] })
      onSaved()
    } catch (e) { setErr(failure(e, 'The file could not be saved')) } finally { setBusy(null) }
  }
  const closeColumns = () => { setOpen(null); if (changed && file) check(file, mapping) }
  const matched = fields.filter(f => mapping[f.id]).length
  const unmatched = fields.some(f => f.required && !mapping[f.id])
  const stated = [basis.scenario && scenarioLabel(basis.scenario), basis.horizon && yearLabel(basis.horizon)].filter(Boolean).join(' · ')

  return (
    <div className="border-t border-[var(--color-line)] pt-4 mt-auto space-y-3">
      <div className="flex items-center justify-between gap-2 text-[12.5px]">
        {file ? <span className="inline-flex items-center gap-1.5 min-w-0 text-[var(--color-ink)]"><FileText size={14} className="shrink-0 text-[var(--color-mute)]" /><span className="truncate">{file.name}</span></span> : <span />}
        <label className="inline-flex items-center gap-1.5 cursor-pointer text-[var(--color-sky)] hover:underline shrink-0">
          <Upload size={14} /> {file ? 'Replace' : 'Upload a file'}
          <input type="file" accept=".csv,.xlsx,.xls" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) { setFile(f); setRep(null); check(f) } }} />
        </label>
      </div>
      {busy === 'check' && <div className="text-[12px] text-[var(--color-faint)]">Checking…</div>}
      {rep && busy !== 'check' && (<>
        <SplitBar label="Rows checked" parts={[
          { label: `${rep.n_valid.toLocaleString()} valid`, value: rep.n_valid, color: 'var(--color-good)' },
          { label: `${rep.n_error.toLocaleString()} with problems`, value: rep.n_error, color: 'var(--color-warn)', onClick: rep.n_error ? () => setOpen('problems') : undefined },
        ]} />
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setOpen('columns')} className={chip}
            style={{ borderColor: unmatched ? 'var(--color-warn)' : 'var(--color-line-2)', color: unmatched ? 'var(--color-warn)' : undefined }}>
            <Columns3 size={13} /> {matched} of {fields.length} columns matched
          </button>
          {kind === 'submission' && (
            <button type="button" onClick={() => setOpen('columns')} className={chip} style={{ borderColor: 'var(--color-line-2)' }}>
              <SlidersHorizontal size={13} /> {stated ? `Basis · ${stated}` : 'No basis stated'}
            </button>)}
          {rep.n_error > 0 && (
            <button type="button" onClick={() => setOpen('problems')} className={chip} style={{ borderColor: 'var(--color-line-2)' }}>
              <ListX size={13} /> See problems
            </button>)}
        </div>
        {rep.status_message && <div className="text-[12.5px] text-[var(--color-warn)]"><MessageLine m={rep.status_message} /></div>}
        <div className="flex flex-wrap items-center gap-2">
          <select value={period} onChange={e => setPeriod(e.target.value)} aria-label="Financial year"
            className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2 py-2 text-[12.5px] text-[var(--color-ink)]">
            {periodsWith(onFile).map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <Button onClick={save} disabled={busy != null || !rep.ok || changed}>
            {busy === 'save' ? 'Saving…' : kind === 'submission' ? 'Save template' : 'Import and score'}
          </Button>
        </div>
      </>)}
      {err && <div className="text-[12.5px] text-[var(--color-bad)]"><MessageLine m={err} /></div>}
      {open === 'columns' && rep && file && (
        <Drawer label="Match columns" onClose={closeColumns} className={panel}>
          <div className="flex items-start justify-between gap-3">
            <div className="text-[16px] font-semibold text-[var(--color-ink)]">Match columns</div>
            <CloseButton onClick={closeColumns} />
          </div>
          <div className="flex items-center gap-2 text-[12px] text-[var(--color-mute)] mt-0.5 mb-4">
            <span className="truncate">{file.name}</span>
            {kind === 'granular' && <InfoButton compact details={{ title: 'How locations are found', sections: [
              { heading: HEADING.read, body: spec.granular.location_rule },
              { heading: HEADING.limits, body: spec.granular.precision_label },
            ] }} />}
          </div>
          <div className="space-y-3">
            {fields.map(f => <ColumnPick key={f.id} f={f} columns={rep.columns} value={mapping[f.id] ?? ''}
              onChange={v => { setMapping({ ...mapping, [f.id]: v || null }); setChanged(true) }} />)}
          </div>
          {kind === 'submission' && <BasisFields fields={spec.submission.basis_fields} basis={basis} setBasis={setBasis} />}
          <div className="mt-6"><Button onClick={closeColumns}>{changed ? 'Check again' : 'Done'}</Button></div>
        </Drawer>)}
      {open === 'problems' && rep && <Problems rep={rep} onClose={() => setOpen(null)} />}
    </div>
  )
}

function ColumnPick({ f, columns, value, onChange }: { f: Field; columns: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="flex items-center gap-2 text-[12px] text-[var(--color-ink)]">
        {f.label}{f.required && <StatusChip label="Required" tone={value ? 'neutral' : 'warn'} />}
      </span>
      <select value={value} onChange={e => onChange(e.target.value)} className={control}
        style={{ borderColor: f.required && !value ? 'var(--color-warn)' : 'var(--color-line-2)' }}>
        <option value="">Not in the file</option>
        {columns.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    </label>
  )
}

// What the entity says its template rests on: the lens rebuilds at this basis too, so scenario and year are chosen
// from the ones it can rebuild at, never typed.
function BasisFields({ fields, basis, setBasis }: { fields: Field[]; basis: Basis; setBasis: (b: Basis) => void }) {
  const set = (id: string, v: string) => setBasis({ ...basis, [id]: v })
  const style = { borderColor: 'var(--color-line-2)' }
  return (
    <div className="mt-6 space-y-3">
      <div className="flex items-center gap-2">
        <SectionHead>Stated basis</SectionHead>
        <InfoButton compact details={{ title: 'Stated basis', sections: [
          { heading: HEADING.shows, body: 'The scenario, year and at-risk level the entity names in its narrative.' },
          { heading: HEADING.read, body: 'The independent lens rebuilds the template at this basis as well as at yours, so a difference in basis is told apart from a difference in scoring. Leave a field empty when the entity states none.' },
        ] }} />
      </div>
      {fields.map(b => (
        <label key={b.id} className="block text-[12px] text-[var(--color-ink)]">{b.label}
          {b.id === 'scenario' ? (
            <select value={basis.scenario ?? ''} onChange={e => set('scenario', e.target.value)} className={control} style={style}>
              <option value="">Not stated</option>
              {Object.keys(SCENARIO_LABEL).map(s => <option key={s} value={s}>{scenarioLabel(s)}</option>)}
            </select>
          ) : b.id === 'horizon' ? (
            <select value={basis.horizon ?? ''} onChange={e => set('horizon', e.target.value)} className={control} style={style}>
              <option value="">Not stated</option>
              {HORIZONS.map(h => <option key={h} value={h}>{yearLabel(h)}</option>)}
            </select>
          ) : (
            <input value={basis[b.id] ?? ''} onChange={e => set(b.id, e.target.value)} className={control} style={style}
              type={b.id === 'at_risk_level' ? 'number' : 'text'} min={0} max={100} />
          )}
        </label>
      ))}
    </div>
  )
}

// The rows with problems, by kind: a bar per problem (every row counted), its explanation, and the rows to correct.
function Problems({ rep, onClose }: { rep: Report; onClose: () => void }) {
  const [pick, setPick] = useState(0)
  const t = rep.problem_types[pick]
  const values = new Map<number, string | null>()
  if (t) for (const e of rep.errors) for (const i of e.issues) if (i.code === t.code && i.field === t.field) values.set(e.row, i.value)
  return (
    <Drawer label="Rows with problems" onClose={onClose} className={panel}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-[16px] font-semibold text-[var(--color-ink)]">Rows with problems</div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="text-[12px] text-[var(--color-mute)] mt-0.5 mb-4 tabular-nums">{rep.n_error.toLocaleString()} of {rep.n_total.toLocaleString()} rows</div>
      <HBar data={rep.problem_types.map((p, i) => ({ label: p.label, value: p.count, color: i === pick ? 'var(--color-warn)' : 'var(--color-slate)' }))}
        format={n => n.toLocaleString()} onBar={setPick} labelWidth="w-48" />
      {t && (
        <div className="mt-5 rounded-lg border border-[var(--color-line-2)] p-4">
          <div className="text-[13.5px] font-semibold text-[var(--color-ink)] mb-3">{t.label}</div>
          <DetailsBody sections={messageDetails({ label: t.label, detail: t.detail }).sections} />
          <div className="mt-4 text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)]">Rows</div>
          <div className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[12.5px] tabular-nums">
            {t.rows.map(r => [
              <span key={`r${r}`} className="text-[var(--color-mute)]">Row {r}</span>,
              <span key={`v${r}`} className="text-[var(--color-ink)] truncate">{values.get(r) ?? '—'}</span>,
            ])}
          </div>
          {t.count > t.rows.length && <div className="text-[11.5px] text-[var(--color-faint)] mt-2">The first {t.rows.length} of {t.count.toLocaleString()} rows.</div>}
        </div>
      )}
    </Drawer>
  )
}
