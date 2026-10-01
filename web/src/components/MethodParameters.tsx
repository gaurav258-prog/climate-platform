import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Scale, Send, AlertTriangle, CheckCircle2, Clock } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button } from './ui'

// The institution's stated method for the financial year (E69): every parameter a money figure depends on that the
// platform cannot take from a fact, a quoted regulation or a validated model — its at-risk level, damage ratios, event
// probabilities, loadings, stranded shares, carbon prices… Each value is stated by one person and attested by a second
// (provided values, family 'method'); nothing has a default, and a figure that needs an unstated value is a named gap.

interface Param { key: string; label: string; unit: string; used_for?: string; breakdown: string | null; members: Record<string, string> | null }
interface Provided { provided_id: string; datapoint_key: string; value_num: number | null; status: string; breakdown_member: string | null
  reporting_period_end: string | null; submitted_by: string | null; decided_by: string | null }
interface Needed { period_end: string; basis: { scenario: string; horizon: string }; needed: { key: string; member: string | null }[] }

const UNIT_HINT: Record<string, string> = { ratio: 'a share between 0 and 1 (0.05 = 5%)', score: 'a headline score 0–100', 'EUR/tCO2e': 'euro per tonne CO₂e' }

// a breakdown's members, split into the axes a person picks from (peril × band, division @ scenario / horizon …)
function axes(breakdown: string): { names: string[]; split: (m: string) => string[]; join: (p: string[]) => string } {
  if (breakdown === 'peril_band' || breakdown === 'scenario_horizon')
    return { names: breakdown === 'peril_band' ? ['Peril', 'Hazard band'] : ['Scenario', 'Horizon'], split: m => m.split('/'), join: p => p.join('/') }
  if (breakdown === 'division_scenario_horizon')
    return { names: ['NACE division', 'Scenario', 'Horizon'], split: m => { const [d, rest] = m.split('@'); return [d, ...rest.split('/')] }, join: p => `${p[0]}@${p[1]}/${p[2]}` }
  return { names: [breakdown === 'band' ? 'Hazard band' : breakdown === 'peril' ? 'Peril' : breakdown === 'epc_grade' ? 'EPC grade' : 'Member'], split: m => [m], join: p => p[0] }
}

export default function MethodParameters() {
  const qc = useQueryClient()
  const cat = useQuery({ queryKey: ['method-catalog'], queryFn: () => api.get<{ datapoints: Param[] }>('/v1/provided/catalog?framework=method') })
  const prov = useQuery({ queryKey: ['method-provided'], queryFn: () => api.get<{ provided: Provided[] }>('/v1/provided?framework=method') })
  const need = useQuery({ queryKey: ['method-needed'], queryFn: () => api.get<Needed>('/v1/provided/method/needed') })
  const [open, setOpen] = useState<string | null>(null)
  const [prefill, setPrefill] = useState<{ key: string; member: string | null } | null>(null)

  const periodEnd = need.data?.period_end ?? ''
  const params = cat.data?.datapoints ?? []
  const forYear = (prov.data?.provided ?? []).filter(p => !p.reporting_period_end || p.reporting_period_end === periodEnd)
  const byKey = useMemo(() => {
    const m: Record<string, Provided[]> = {}
    for (const p of forYear) (m[p.datapoint_key] ??= []).push(p)
    return m
  }, [forYear])
  const needed = need.data?.needed ?? []

  const startFrom = (key: string, member: string | null) => { setOpen(key); setPrefill({ key, member }) }
  const refresh = () => { qc.invalidateQueries({ queryKey: ['method-provided'] }); qc.invalidateQueries({ queryKey: ['method-needed'] }) }

  return (
    <Card className="p-5 space-y-4">
      <div>
        <div className="flex items-center gap-2"><Scale size={16} className="text-[var(--color-sky)]" />
          <h2 className="display text-xl font-semibold">Your stated method{periodEnd ? ` · financial year ending ${periodEnd}` : ''}</h2></div>
        <p className="text-[12.5px] text-[var(--color-mute)] max-w-3xl mt-1">
          Every money figure rests only on your data, a quoted regulation, a model validated for that figure — or a parameter you state here.
          The platform supplies no default: what is not stated makes the figure that needs it a named gap. Each value is stated by one person and
          takes effect when a second person attests it (Approvals).
        </p>
      </div>

      {need.data && (
        needed.length === 0
          ? <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-good)]"><CheckCircle2 size={14} /> Your current figures find every parameter they need for this year (basis {need.data.basis.scenario} · {need.data.basis.horizon}).</div>
          : <div className="rounded-lg border border-[var(--color-warn)]/40 px-3.5 py-3">
              <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-ink)] mb-2"><AlertTriangle size={14} className="text-[var(--color-warn)]" />
                {needed.length} parameter value{needed.length === 1 ? '' : 's'} your current figures need {needed.length === 1 ? 'is' : 'are'} not stated — click one to state it</div>
              <div className="flex flex-wrap gap-1.5">
                {needed.slice(0, 40).map(n => (
                  <button key={n.key + (n.member ?? '')} onClick={() => startFrom(n.key, n.member)}
                    className="mono text-[10.5px] px-2 py-1 rounded border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
                    {n.key.replace('method.', '')}{n.member ? ` · ${n.member}` : ''}
                  </button>))}
                {needed.length > 40 && <span className="mono text-[10.5px] text-[var(--color-faint)] self-center">+{needed.length - 40} more</span>}
              </div>
            </div>
      )}

      <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
        {params.map(p => {
          const stated = byKey[p.key] ?? []
          const isOpen = open === p.key
          return (
            <div key={p.key} className="py-3">
              <button onClick={() => { setOpen(isOpen ? null : p.key); setPrefill(null) }} className="w-full text-left flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-[13px] font-semibold text-[var(--color-ink)]">{p.label}</span>
                <span className="mono text-[10.5px] text-[var(--color-faint)]">{p.key} · {p.unit}{p.breakdown ? ` · by ${p.breakdown.replace(/_/g, ' ')}` : ''}</span>
                <span className="ml-auto mono text-[10.5px] text-[var(--color-mute)]">{stated.length ? `${stated.filter(s => s.status === 'attested').length} attested · ${stated.filter(s => s.status !== 'attested').length} pending` : 'not stated'}</span>
              </button>
              {p.used_for && <div className="text-[11.5px] text-[var(--color-faint)] mt-0.5">Used for: {p.used_for}</div>}
              {isOpen && (
                <div className="mt-3 space-y-3">
                  {stated.length > 0 && (
                    <table className="w-full text-[12px]">
                      <thead><tr className="mono text-[9.5px] uppercase text-[var(--color-faint)] text-left"><th className="py-1">{p.breakdown ? 'Member' : ''}</th><th>Value</th><th>Status</th><th>Stated by</th><th>Attested by</th></tr></thead>
                      <tbody>{stated.map(s => (
                        <tr key={s.provided_id} className="border-t border-[var(--color-line)]">
                          <td className="py-1.5 mono">{s.breakdown_member ?? '—'}</td>
                          <td className="mono tabular-nums">{s.value_num}</td>
                          <td>{s.status === 'attested' ? <span className="text-[var(--color-good)] inline-flex items-center gap-1"><CheckCircle2 size={12} /> attested</span>
                            : <span className="text-[var(--color-warn)] inline-flex items-center gap-1"><Clock size={12} /> {s.status.replace(/_/g, ' ')}</span>}</td>
                          <td className="text-[var(--color-mute)]">{s.submitted_by ?? '—'}</td>
                          <td className="text-[var(--color-mute)]">{s.decided_by ?? '—'}</td>
                        </tr>))}</tbody>
                    </table>
                  )}
                  {periodEnd && <StateForm param={p} periodEnd={periodEnd} initialMember={prefill?.key === p.key ? prefill.member : null} onDone={refresh} />}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function StateForm({ param, periodEnd, initialMember, onDone }: { param: Param; periodEnd: string; initialMember: string | null; onDone: () => void }) {
  const members = useMemo(() => Object.keys(param.members ?? {}), [param.members])
  const ax = useMemo(() => (param.breakdown ? axes(param.breakdown) : null), [param.breakdown])
  const choices = useMemo(() => {
    if (!ax) return []
    const parts = members.map(ax.split)
    return ax.names.map((_, i) => [...new Set(parts.map(p => p[i]))].sort((a, b) => (a === 'any' ? -1 : b === 'any' ? 1 : a.localeCompare(b))))
  }, [ax, members])
  const [pick, setPick] = useState<string[]>(() => initialMember && ax ? ax.split(initialMember) : (ax ? choices.map(c => c[0]) : []))
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const member = ax ? ax.join(pick) : null
  const valid = !ax || members.includes(member ?? '')

  const submit = async () => {
    const v = Number(value)
    if (value.trim() === '' || Number.isNaN(v)) { toast.error('Enter a number.'); return }
    setBusy(true)
    try {
      await api.post('/v1/provided', { framework: 'method', datapoint_key: param.key, value_num: v, reporting_period_end: periodEnd,
                                       ...(member ? { breakdown_member: member } : {}) })
      toast.success('Stated — it takes effect when a second person attests it (Approvals).')
      setValue(''); onDone()
    } catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not submit the value.') } finally { setBusy(false) }
  }

  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-3.5 py-3 flex flex-wrap items-end gap-3">
      {ax?.names.map((n, i) => (
        <label key={n} className="text-[11px] text-[var(--color-faint)]">{n}
          <select value={pick[i] ?? ''} onChange={e => setPick(p => { const q = [...p]; q[i] = e.target.value; return q })}
            className="mt-1 block bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12.5px] text-[var(--color-ink)] max-w-[220px]">
            {choices[i]?.map(c => <option key={c} value={c}>{c === 'any' ? 'any (every one you do not state separately)' : c}</option>)}
          </select></label>))}
      <label className="text-[11px] text-[var(--color-faint)]">Value ({UNIT_HINT[param.unit] ?? param.unit})
        <input value={value} onChange={e => setValue(e.target.value)} inputMode="decimal" placeholder={param.unit === 'score' ? 'e.g. 60' : param.unit === 'ratio' ? 'e.g. 0.05' : ''}
          className="mt-1 block w-40 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] tabular-nums" /></label>
      <Button variant="primary" onClick={submit} disabled={busy || !valid}><Send size={13} /> {busy ? 'Submitting…' : 'State for 4-eyes'}</Button>
      {!valid && <span className="text-[11px] text-[var(--color-warn)]">That combination is not a member of this breakdown.</span>}
    </div>
  )
}
