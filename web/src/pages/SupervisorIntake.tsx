import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { Button, Card, PageHeader, StatGrid } from '../components/ui'

// Tier-2 intake — the data steward's screen. Two files per entity and period, each mapped column-by-column to the
// canonical fields the supervision profile declares for the entity's sector; nothing is saved until the import.
interface Field { id: string; label: string; required?: boolean; type?: string }
interface Spec { submission: { framework: string; template: string; label: string; cell_fields: Field[]; basis_fields: Field[] }
  granular: { source: string; label: string; row_fields: Field[]; location_rule: string; precision_label: string } }
interface Status { entity: string; sector_type: string; intake: Spec
  shadow_book: { n_rows: number; n_located: number; value_eur: number; coverage_value_pct: number | null }
  submissions: { framework: string; template: string; period_label: string; n_cells: number; source_file: string | null; created_at: string; basis: Record<string, string> }[] }
interface Report { kind: string; fields: Field[]; mapping: Record<string, string | null>; columns: string[]; n_total: number; n_valid: number; n_error: number
  errors: { row: number; problems: string[] }[]; missing_required: string[]; ok: boolean }
const eur = (v: number) => v >= 1e9 ? `€${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${(v / 1e3).toFixed(0)}k`

export default function SupervisorIntake() {
  const { orgId = '' } = useParams()
  const q = useQuery({ queryKey: ['sup-intake', orgId], queryFn: () => api.get<Status>(`/v1/supervisor/intake/${orgId}`) })
  const d = q.data
  if (q.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">loading intake…</div>
  if (!d) return <div className="h-[60vh] grid place-items-center text-[var(--color-bad)] text-sm">No Tier-2 intake is configured for this entity's sector in your profile.</div>
  const sb = d.shadow_book
  return (
    <div className="fadeup space-y-6">
      <Link to={`/supervised/${orgId}`} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><ChevronLeft size={13} /> Entity file</Link>
      <PageHeader eyebrow="Intake · Tier 2" title="What you hold about this entity"
        lead="The template the entity submitted, and your own granular data. Each file is mapped to the canonical fields your profile declares; rows that cannot be placed are listed, never dropped silently. Your data only — the entity never sees it." />
      <StatGrid cols={3} items={[
        { label: 'Shadow book', value: sb.n_rows.toLocaleString(), sub: sb.n_rows ? `${eur(sb.value_eur)} · ${sb.n_located} located` : 'no granular data yet' },
        { label: 'Value with a location', value: sb.coverage_value_pct != null ? `${sb.coverage_value_pct}%` : '—', sub: d.intake.granular.precision_label },
        { label: 'Submissions on file', value: String(d.submissions.filter(s => s.framework !== 'granular').length), sub: d.intake.submission.label },
      ]} />
      <IntakeCard orgId={orgId} kind="submission" title={d.intake.submission.label} fields={d.intake.submission.cell_fields} basisFields={d.intake.submission.basis_fields}
        hint="the cells as filed — geography × sector, gross amount, of which sensitive" />
      <IntakeCard orgId={orgId} kind="granular" title={d.intake.granular.label} fields={d.intake.granular.row_fields}
        hint={d.intake.granular.location_rule} />
      {d.submissions.length > 0 && (
        <Card className="p-5">
          <div className="text-[14px] font-semibold mb-2">On file</div>
          <div className="divide-y divide-[var(--color-line)]">{d.submissions.map((s, i) => (
            <div key={i} className="py-1.5 flex items-center justify-between gap-3 text-[12.5px]">
              <span className="text-[var(--color-ink)]">{s.framework === 'granular' ? 'Granular extract (shadow book)' : `${s.framework} · ${s.template}`} <span className="mono text-[10.5px] text-[var(--color-faint)]">· {s.period_label}{s.basis?.scenario ? ` · stated basis ${s.basis.scenario} ${s.basis.horizon ?? ''}` : ''}</span></span>
              <span className="mono text-[11px] text-[var(--color-faint)]">{s.source_file ?? ''} · {s.created_at.slice(0, 16).replace('T', ' ')}</span>
            </div>))}</div>
          <Link to={`/supervised/${orgId}/lens`} className="inline-block mt-3 text-[12px] font-medium text-[var(--color-sky)] hover:underline">Open the independent lens →</Link>
        </Card>
      )}
    </div>
  )
}

function IntakeCard({ orgId, kind, title, basisFields, hint }:
  { orgId: string; kind: 'submission' | 'granular'; title: string; fields: Field[]; basisFields?: Field[]; hint: string }) {
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [rep, setRep] = useState<Report | null>(null)
  const [mapping, setMapping] = useState<Record<string, string | null>>({})
  const [period, setPeriod] = useState('FY2025')
  const [basis, setBasis] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<'check' | 'import' | null>(null)
  const [msg, setMsg] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)
  const check = async (f: File, m?: Record<string, string | null>) => {
    setBusy('check'); setMsg(null)
    try {
      const fd = new FormData(); fd.append('file', f); if (m) fd.append('mapping', JSON.stringify(m))
      const r = await api.post<Report>(`/v1/supervisor/intake/${orgId}/${kind}/validate`, fd)
      setRep(r); setMapping(r.mapping)
    } catch (e) { setMsg({ tone: 'bad', text: (e as Error).message }) } finally { setBusy(null) }
  }
  const doImport = async () => {
    if (!file || !rep?.ok) return
    setBusy('import'); setMsg(null)
    try {
      const fd = new FormData(); fd.append('file', file); fd.append('mapping', JSON.stringify(mapping)); fd.append('period_label', period)
      if (kind === 'submission') fd.append('basis', JSON.stringify(basis))
      const r = await api.post<{ n_valid: number; result: Record<string, unknown> }>(`/v1/supervisor/intake/${orgId}/${kind}`, fd)
      setMsg({ tone: 'ok', text: kind === 'submission' ? `Saved ${r.n_valid} rows as template cells for ${period}.` : `Shadow book rebuilt: ${r.n_valid} rows · ${JSON.stringify((r.result as { located?: unknown }).located)} · scoring started.` })
      await qc.invalidateQueries({ queryKey: ['sup-intake', orgId] })
    } catch (e) { setMsg({ tone: 'bad', text: (e as Error).message }) } finally { setBusy(null) }
  }
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between flex-wrap gap-2 mb-2">
        <div><div className="text-[14px] font-semibold">{title}</div><div className="text-[12px] text-[var(--color-mute)]">{hint}</div></div>
        <label className="inline-flex items-center gap-1.5 cursor-pointer text-[12.5px] text-[var(--color-sky)] hover:underline">
          <Upload size={14} /> {file ? file.name : 'Choose CSV / Excel'}
          <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); check(f) } }} />
        </label>
      </div>
      {rep && (
        <div className="mt-2">
          <div className="mono text-[11px] text-[var(--color-faint)] mb-2">{rep.n_total} rows · {rep.n_valid} valid · {rep.n_error} with problems · map each canonical field to a column, then re-check</div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {rep.fields.map(f => (
              <label key={f.id} className="text-[11.5px] text-[var(--color-mute)]">{f.label}{f.required ? ' *' : ''}
                <select value={mapping[f.id] ?? ''} onChange={e => setMapping({ ...mapping, [f.id]: e.target.value || null })}
                  className={`mt-0.5 w-full bg-[var(--color-panel)] border rounded-lg px-2 py-1 text-[12px] text-[var(--color-ink)] outline-none ${f.required && !mapping[f.id] ? 'border-[var(--color-warn)]' : 'border-[var(--color-line)]'}`}>
                  <option value="">— not in file —</option>
                  {rep.columns.map(c => <option key={c} value={c}>{c}</option>)}
                </select></label>))}
          </div>
          {kind === 'submission' && basisFields && (
            <div className="grid sm:grid-cols-3 gap-2 mt-3">
              {basisFields.map(b => <label key={b.id} className="text-[11.5px] text-[var(--color-mute)]">{b.label}
                <input value={basis[b.id] ?? ''} onChange={e => setBasis({ ...basis, [b.id]: e.target.value })} placeholder={b.id === 'scenario' ? 'e.g. disorderly_2c' : b.id === 'horizon' ? 'e.g. 2030' : ''}
                  className="mt-0.5 w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] text-[var(--color-ink)] outline-none" /></label>)}
            </div>)}
          {rep.errors.length > 0 && (
            <div className="mt-2 text-[11.5px] text-[var(--color-warn)]">{rep.errors.slice(0, 5).map(e => <div key={e.row}>row {e.row}: {e.problems.join(' · ')}</div>)}{rep.errors.length > 5 && <div>… {rep.errors.length - 5} more</div>}</div>)}
          <div className="mt-3 flex items-center gap-3 flex-wrap">
            <label className="text-[11.5px] text-[var(--color-mute)]">Period <input value={period} onChange={e => setPeriod(e.target.value)} className="ml-1 w-24 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] text-[var(--color-ink)] outline-none" /></label>
            <Button onClick={() => file && check(file, mapping)} disabled={busy != null}>{busy === 'check' ? 'Checking…' : 'Re-check with this mapping'}</Button>
            <Button onClick={doImport} disabled={busy != null || !rep.ok}>{busy === 'import' ? 'Importing…' : kind === 'submission' ? 'Save template cells' : 'Build shadow book & score'}</Button>
            {!rep.ok && <span className="text-[11.5px] text-[var(--color-warn)]">{rep.missing_required.length ? `map the required fields: ${rep.missing_required.join(', ')}` : 'no valid rows'}</span>}
          </div>
        </div>)}
      {msg && <div className={`mt-3 text-[12.5px] ${msg.tone === 'ok' ? 'text-[var(--color-good)]' : 'text-[var(--color-bad)]'}`}>{msg.text}</div>}
    </Card>
  )
}
