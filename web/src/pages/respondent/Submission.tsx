import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Upload } from 'lucide-react'
import clsx from 'clsx'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { horizonLabel, scenarioLabel } from '../../lib/labels'
import { SCENARIO_LABEL } from '../../lib/hazards'
import { Button, Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton, MessageLine, type Message } from '../../components/Details'
import { day, field, useCan } from './common'

// The template the supervisor requires, submitted from our side: the same intake the supervisor keys in. The file is
// checked before anything is sent; the columns, the column matching and any problem rows open in pop-ups.
interface Field { id: string; label: string; required?: boolean; type?: string }
interface OnFile { period_label: string; created_at: string; n_cells: number; basis: Record<string, string> | null }
interface Spec { regulator: string; available: boolean; message?: Message; label?: string; fields?: Field[]; basis_fields?: Field[]
  at_risk_level?: number | null; level_message?: Message; on_file: OnFile[] }
interface Check { fields: Field[]; mapping: Record<string, string | null>; columns: string[]; n_total: number; n_valid: number; n_error: number
  missing_required: string[]; errors: { row: number; problems: string[] }[] }

const HORIZONS = ['current', '2030', '2050', '2100']
const BASIS: Record<string, string> = { scenario: 'Scenario', horizon: 'Horizon', method_note: 'Method note', at_risk_level: 'At-risk threshold' }

export function TemplateSubmission() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const isReg = profile?.org?.type === 'regulator'
  const canSubmit = useCan('reports.publish', 'respondent.portal')
  const sups = useQuery({ queryKey: ['my-supervisors'], enabled: !isReg, queryFn: () => api.get<{ supervisors: { supervision_id: string; regulator: string }[] }>('/v1/me/supervisors') })
  const [sid, setSid] = useState('')
  const active = sid || sups.data?.supervisors[0]?.supervision_id || ''
  const spec = useQuery({ queryKey: ['submission-spec', active], enabled: !!active, queryFn: () => api.get<Spec>(`/v1/me/supervisors/${active}/submission-spec`) })
  const [file, setFile] = useState<File | null>(null)
  const [check, setCheck] = useState<Check | null>(null)
  const [period, setPeriod] = useState(`FY${new Date().getFullYear() - 1}`)
  const [basis, setBasis] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  if (isReg || !sups.data || sups.data.supervisors.length === 0) return null
  const s = spec.data
  const form = (extra: Record<string, string>) => { const fd = new FormData(); fd.append('file', file!); for (const [k, v] of Object.entries(extra)) fd.append(k, v); return fd }
  const run = async () => {
    if (!file) return
    setBusy(true)
    try { setCheck(await api.post<Check>(`/v1/me/supervisors/${active}/submissions/validate`, form({}))) }
    catch (e) { toast.error(apiMessage(e, 'Could not check the file.')) } finally { setBusy(false) }
  }
  const submit = async () => {
    if (!file || !check) return
    setBusy(true)
    try {
      const stated = Object.fromEntries(Object.entries(basis).filter(([, v]) => v.trim() !== ''))
      const r = await api.post<{ regulator: string; n_valid: number }>(`/v1/me/supervisors/${active}/submissions`,
        form({ mapping: JSON.stringify(check.mapping), period_label: period, ...(Object.keys(stated).length ? { basis: JSON.stringify(stated) } : {}) }))
      toast.success(`Submitted to ${r.regulator}: ${r.n_valid} rows for ${period}.`); setFile(null); setCheck(null)
      await qc.invalidateQueries({ queryKey: ['submission-spec', active] })
    } catch (e) { toast.error(apiMessage(e, 'Could not submit.')) } finally { setBusy(false) }
  }
  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <SectionHead icon={Upload} hint="checked before it is sent">Submit to your supervisor</SectionHead>
        {sups.data.supervisors.length > 1 && (
          <select value={active} onChange={e => { setSid(e.target.value); setCheck(null) }} aria-label="Supervisor" className={clsx(field, 'ml-auto')}>
            {sups.data.supervisors.map(x => <option key={x.supervision_id} value={x.supervision_id}>{x.regulator}</option>)}
          </select>)}
      </div>
      {!s ? <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div> : !s.available ? (s.message && <div className="text-[12.5px] text-[var(--color-mute)]"><MessageLine m={s.message} /></div>) : (<>
        <div className="flex items-center gap-2 flex-wrap text-[13px]">
          <span className="text-[var(--color-ink)]">{s.label}</span>
          <InfoButton label="Columns" details={{ title: 'Template columns', sections: [
            { heading: HEADING.shows, body: `The columns ${s.regulator} expects in the file. Required columns must be present; the others are read when given.` },
            { heading: 'Columns', body: <ul className="m-0 pl-4 space-y-0.5">{(s.fields ?? []).map(f => <li key={f.id}>{f.label}{f.required ? <span className="text-[var(--color-warn)]"> · required</span> : null}</li>)}</ul> },
          ] }} />
        </div>
        {s.on_file.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap text-[12px]">
            <span className="text-[var(--color-mute)]">On file with {s.regulator}</span>
            {s.on_file.map(o => <StatusChip key={o.period_label + o.created_at} label={o.period_label} tone="good" />)}
            <InfoButton compact details={{ title: 'Submissions on file', sections: s.on_file.map(o => ({ heading: o.period_label,
              body: `Received ${day(o.created_at)} · ${o.n_cells} rows${o.basis?.scenario ? ` · stated basis ${scenarioLabel(o.basis.scenario)}, ${horizonLabel(o.basis.horizon)}` : ''}` })) }} />
          </div>)}
        {!canSubmit ? <div className="text-[12px] text-[var(--color-faint)]">Submitting needs the release permission.</div> : (<>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-[12px] text-[var(--color-mute)] flex flex-col gap-1">File
              <input type="file" accept=".csv,.xlsx,.xls" onChange={e => { setFile(e.target.files?.[0] ?? null); setCheck(null) }} className="text-[12.5px] text-[var(--color-ink)]" /></label>
            <label className="text-[12px] text-[var(--color-mute)] flex flex-col gap-1">Period
              <input value={period} onChange={e => setPeriod(e.target.value)} className={clsx(field, 'w-28')} /></label>
            <Button variant="ghost" onClick={run} disabled={!file || busy}>Check the file</Button>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {(s.basis_fields ?? []).map(b => (
              <label key={b.id} className="text-[12px] text-[var(--color-mute)] flex flex-col gap-1">{BASIS[b.id] ?? b.label}
                {b.id === 'scenario' ? (
                  <select value={basis.scenario ?? ''} onChange={e => setBasis({ ...basis, scenario: e.target.value })} className={field}>
                    <option value="">Not stated</option>{Object.keys(SCENARIO_LABEL).map(k => <option key={k} value={k}>{scenarioLabel(k)}</option>)}</select>
                ) : b.id === 'horizon' ? (
                  <select value={basis.horizon ?? ''} onChange={e => setBasis({ ...basis, horizon: e.target.value })} className={field}>
                    <option value="">Not stated</option>{HORIZONS.map(h => <option key={h} value={h}>{h === 'current' ? 'Today' : h}</option>)}</select>
                ) : <input value={basis[b.id] ?? ''} onChange={e => setBasis({ ...basis, [b.id]: e.target.value })} title={b.label}
                    type={b.id === 'at_risk_level' ? 'number' : 'text'} min={0} max={100} placeholder={b.id === 'at_risk_level' && s.at_risk_level != null ? String(s.at_risk_level) : ''}
                    className={clsx(field, b.id === 'at_risk_level' ? 'w-28' : 'w-64')} />}
              </label>))}
          </div>
          {s.level_message && <div className="text-[12.5px] text-[var(--color-mute)]"><MessageLine m={s.level_message} /></div>}
          {check && <CheckResult c={check} busy={busy} regulator={s.regulator} period={period} onSubmit={submit} />}
        </>)}
      </>)}
    </Card>
  )
}

// What the check found: valid rows as a bar, missing columns as chips, the matching and problem rows behind ⓘ.
function CheckResult({ c, busy, regulator, period, onSubmit }: { c: Check; busy: boolean; regulator: string; period: string; onSubmit: () => void }) {
  const label = (id: string) => c.fields.find(f => f.id === id)?.label ?? 'A required column'
  const ok = c.missing_required.length === 0 && c.n_error === 0
  const pct = c.n_total ? (c.n_valid / c.n_total) * 100 : 0
  return (
    <div className="rounded-lg border border-[var(--color-line)] p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
        <span className="text-[var(--color-ink)] flex items-center gap-1.5">{ok && <CheckCircle2 size={14} className="text-[var(--color-good)]" />}{c.n_valid} of {c.n_total} rows valid</span>
        <span className="flex items-center gap-3">
          <InfoButton label="Column matching" details={{ title: 'How your columns were matched', sections: [
            { heading: HEADING.shows, body: 'Each template column, and the column of your file it is read from.' },
            { heading: 'Matching', body: <table className="text-[12.5px]"><tbody>{c.fields.map(f => (
              <tr key={f.id}><td className="pr-4 py-0.5 text-[var(--color-mute)]">{f.label}</td>
                <td className="py-0.5" style={{ color: c.mapping[f.id] ? 'var(--color-ink)' : f.required ? 'var(--color-warn)' : 'var(--color-faint)' }}>{c.mapping[f.id] ?? 'Not found'}</td></tr>))}</tbody></table> },
          ] }} />
          {c.errors.length > 0 && <InfoButton label={`Rows with problems · ${c.n_error}`} details={{ title: 'Rows with problems', sections: c.errors.slice(0, 25).map(e => ({ heading: `Row ${e.row}`, body: e.problems.join('; ') })) }} />}
        </span>
      </div>
      <div className="h-2.5 rounded-full bg-[var(--color-panel-2)] overflow-hidden flex">
        <div style={{ width: `${pct}%`, background: 'var(--color-good)' }} />
        <div style={{ width: `${100 - pct}%`, background: c.n_error ? 'var(--color-bad)' : 'transparent' }} />
      </div>
      {c.missing_required.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap text-[12px]"><span className="text-[var(--color-mute)]">Not found in your file</span>
          {c.missing_required.map(id => <StatusChip key={id} label={label(id)} tone="warn" />)}</div>)}
      <Button onClick={onSubmit} disabled={busy || !ok}>{busy ? 'Submitting…' : `Submit ${period} to ${regulator}`}</Button>
    </div>
  )
}
