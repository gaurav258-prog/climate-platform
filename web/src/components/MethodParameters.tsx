import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Scale, Send } from 'lucide-react'
import clsx from 'clsx'
import { api, apiDetail, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, SectionHead } from './ui'
import { HEADING, InfoButton, type Details } from './Details'
import { StatusChip } from './StatusChip'

// The institution's stated method for the financial year (E69): every parameter a money figure depends on that the
// platform cannot take from a fact, a quoted regulation or a validated model — its at-risk level, damage ratios, event
// probabilities, loadings, stranded shares, carbon prices… Each value is stated by one person and attested by a second
// (provided values, family 'method'); nothing has a default, and a figure that needs an unstated value is reported as
// missing. The server names every parameter, axis and member (services/governance/admin_view.method_view).

interface Axis { axis: string; title: string; names: Record<string, string> }
interface Param { key: string; name: string; about: string; unit: string; used_for?: string | null; breakdown: string | null
  members: Record<string, string> | null; axes: Axis[] | null; requires_source?: boolean }
interface Provided { provided_id: string; datapoint_key: string; value_num: number | null; status: string; breakdown_member: string | null
  reporting_period_end: string | null; submitted_by: string | null; decided_by: string | null }
interface Need { key: string; member: string | null; name: string; member_label: string | null }
interface Needed { period_end: string; needed: Need[] }

const UNIT: Record<string, string> = { ratio: 'a share between 0 and 1 (0.05 is 5 %)', score: 'a score from 0 to 100',
  'EUR/tCO2e': 'euro per tonne of CO₂e', 'tCO2e/EUR m': 'tonnes of CO₂e per million euro' }
const ABOUT: Details = {
  title: 'Your stated method', sections: [
    { heading: HEADING.shows, body: 'The values a money figure depends on that cannot come from a fact, a quoted rule or a tested model — your at-risk threshold, damage ratios, event probabilities, loadings and the like — stated for the financial year.' },
    { heading: HEADING.read, body: 'The platform supplies no default: a figure that needs a value you have not stated is reported as missing. Each value is stated by one person and takes effect once a second person attests it on Approvals.' },
  ],
}

// a member's parts, in the order its breakdown spells them ('flood/H', 'A01@baseline/2030')
function split(breakdown: string, m: string): string[] {
  if (breakdown === 'division_scenario_horizon') { const [d, rest] = m.split('@'); return [d, ...rest.split('/')] }
  return breakdown === 'peril_band' || breakdown === 'scenario_horizon' ? m.split('/') : [m]
}
function join(breakdown: string, p: string[]): string {
  return breakdown === 'division_scenario_horizon' ? `${p[0]}@${p[1]}/${p[2]}` : p.join('/')
}
const memberWords = (p: Param, m: string | null) => !m || !p.breakdown || !p.axes ? '—'
  : split(p.breakdown, m).map((v, i) => p.axes![i]?.names[v] ?? v).join(' · ')

export default function MethodParameters() {
  const qc = useQueryClient()
  const cat = useQuery({ queryKey: ['method-catalog'], queryFn: () => api.get<{ datapoints: Param[] }>('/v1/provided/catalog?framework=method') })
  const prov = useQuery({ queryKey: ['method-provided'], queryFn: () => api.get<{ provided: Provided[] }>('/v1/provided?framework=method') })
  const need = useQuery({ queryKey: ['method-needed'], queryFn: () => api.get<Needed>('/v1/provided/method/needed') })
  const [open, setOpen] = useState<string | null>(null)
  const [prefill, setPrefill] = useState<{ key: string; member: string | null } | null>(null)
  const periodEnd = need.data?.period_end ?? ''
  const params = cat.data?.datapoints ?? []
  const byKey = useMemo(() => {
    const m: Record<string, Provided[]> = {}
    for (const p of prov.data?.provided ?? []) if (!p.reporting_period_end || p.reporting_period_end === periodEnd) (m[p.datapoint_key] ??= []).push(p)
    return m
  }, [prov.data, periodEnd])
  const needed = need.data?.needed ?? []
  const refresh = () => { qc.invalidateQueries({ queryKey: ['method-provided'] }); qc.invalidateQueries({ queryKey: ['method-needed'] }) }
  const startFrom = (n: Need) => {                // open the value's row and bring it into view
    setOpen(n.key); setPrefill({ key: n.key, member: n.member })
    requestAnimationFrame(() => document.getElementById(`method-${n.key}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b border-[var(--color-line)] flex flex-wrap items-center gap-3">
        <SectionHead icon={Scale} className="gap-1.5">Your stated method <InfoButton compact details={ABOUT} /></SectionHead>
        {periodEnd && <span className="text-[12.5px] text-[var(--color-mute)]">Financial year ending {periodEnd}</span>}
        {need.data && <span className="ml-auto">{needed.length === 0
          ? <StatusChip tone="good" label="Every value your figures need is stated" />
          : <StatusChip tone="warn" label={`${needed.length} values your figures need`} />}</span>}
      </div>
      {needed.length > 0 && (
        <div className="px-4 py-3 border-b border-[var(--color-line)] flex flex-wrap gap-1.5">
          {needed.slice(0, 40).map(n => (
            <button key={n.key + (n.member ?? '')} onClick={() => startFrom(n)}
              className="text-[12px] px-2.5 py-1 rounded-lg border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
              {n.name}{n.member_label ? ` · ${n.member_label}` : ''}
            </button>))}
          {needed.length > 40 && <span className="text-[12px] text-[var(--color-faint)] self-center">and {needed.length - 40} more</span>}
        </div>
      )}
      <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
        {params.map(p => {
          const stated = byKey[p.key] ?? []
          const attested = stated.filter(s => s.status === 'attested').length, waiting = stated.filter(s => s.status === 'pending').length
          const isOpen = open === p.key
          return (
            <li key={p.key} id={`method-${p.key}`} className="px-4 py-3 scroll-mt-24">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <button onClick={() => { setOpen(isOpen ? null : p.key); setPrefill(null) }} aria-expanded={isOpen}
                  className="inline-flex items-center gap-1.5 text-[13.5px] text-[var(--color-ink)] hover:text-[var(--color-sky)]">
                  <ChevronDown size={14} className={clsx('text-[var(--color-faint)] transition-transform', isOpen && 'rotate-180')} />{p.name}
                </button>
                <InfoButton compact details={{ title: p.name, sections: [
                  { heading: 'What it is', body: p.about },
                  { heading: 'Stated as', body: UNIT[p.unit] ?? p.unit },
                  ...(p.used_for ? [{ heading: 'Used for', body: p.used_for }] : []),
                ] }} />
                <span className="ml-auto flex flex-wrap gap-1.5">
                  {attested > 0 && <StatusChip tone="good" label={`${attested} attested`} />}
                  {waiting > 0 && <StatusChip tone="warn" label={`${waiting} awaiting approval`} />}
                  {!stated.length && <StatusChip tone="neutral" label="Not stated" />}
                </span>
              </div>
              {isOpen && (
                <div className="mt-3 space-y-3">
                  {stated.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="data-table w-full text-[12px]">
                        <thead><tr>{p.breakdown && <th>For</th>}<th>Value</th><th>Status</th><th>Stated by</th><th>Attested by</th></tr></thead>
                        <tbody>{stated.map(s => (
                          <tr key={s.provided_id}>
                            {p.breakdown && <td>{memberWords(p, s.breakdown_member)}</td>}
                            <td className="tabular-nums">{s.value_num}</td>
                            <td><StatusChip value={s.status} /></td>
                            <td className="text-[var(--color-mute)]">{s.submitted_by ?? '—'}</td>
                            <td className="text-[var(--color-mute)]">{s.decided_by ?? '—'}</td>
                          </tr>))}</tbody>
                      </table>
                    </div>
                  )}
                  {periodEnd && <StateForm param={p} periodEnd={periodEnd} initialMember={prefill?.key === p.key ? prefill.member : null} onDone={refresh} />}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

function StateForm({ param, periodEnd, initialMember, onDone }: { param: Param; periodEnd: string; initialMember: string | null; onDone: () => void }) {
  const axes = param.axes ?? []
  const members = useMemo(() => Object.keys(param.members ?? {}), [param.members])
  const [pick, setPick] = useState<string[]>(() => initialMember && param.breakdown ? split(param.breakdown, initialMember) : axes.map(a => Object.keys(a.names)[0]))
  const [value, setValue] = useState('')
  const [provider, setProvider] = useState('')
  const [vintage, setVintage] = useState('')
  const [busy, setBusy] = useState(false)
  const member = param.breakdown ? join(param.breakdown, pick) : null
  const valid = !param.breakdown || members.includes(member ?? '')
  const submit = async () => {
    const v = Number(value)
    if (value.trim() === '' || Number.isNaN(v)) { toast.error('Enter a number.'); return }
    if (param.requires_source && (!provider.trim() || !vintage)) { toast.error('Give the source this value is taken from and its date.'); return }
    setBusy(true)
    try {
      await api.post('/v1/provided', { framework: 'method', datapoint_key: param.key, value_num: v, reporting_period_end: periodEnd,
                                       ...(member ? { breakdown_member: member } : {}),
                                       ...(param.requires_source ? { provider_name: provider.trim(), data_vintage: vintage } : {}) })
      toast.success('Stated — it takes effect once a second person attests it on Approvals.')
      setValue(''); onDone()
    } catch (e) { toast.error(apiDetail(e)?.what ?? apiMessage(e, 'The value could not be stated.')) } finally { setBusy(false) }
  }
  const field = 'mt-1 block bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]'
  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-3.5 py-3 flex flex-wrap items-end gap-3">
      {axes.map((a, i) => (
        <label key={a.axis} className="text-[12px] text-[var(--color-mute)]">{a.title}
          <select value={pick[i] ?? ''} onChange={e => setPick(p => { const q = [...p]; q[i] = e.target.value; return q })} className={clsx(field, 'max-w-[260px]')}>
            {Object.entries(a.names).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select></label>))}
      <label className="text-[12px] text-[var(--color-mute)]">Value, {UNIT[param.unit] ?? param.unit}
        <input value={value} onChange={e => setValue(e.target.value)} inputMode="decimal" className={clsx(field, 'w-40 tabular-nums')} /></label>
      {param.requires_source && <>
        <label className="text-[12px] text-[var(--color-mute)]">Source
          <input value={provider} onChange={e => setProvider(e.target.value)} placeholder="The published source you use" className={clsx(field, 'w-56')} /></label>
        <label className="text-[12px] text-[var(--color-mute)]">Source date
          <input type="date" value={vintage} onChange={e => setVintage(e.target.value)} className={field} /></label>
      </>}
      <Button variant="primary" onClick={submit} disabled={busy || !valid}><Send size={13} /> {busy ? 'Sending…' : 'State for approval'}</Button>
      {!valid && <span className="text-[12px] text-[var(--color-warn)]">That combination cannot be stated.</span>}
    </div>
  )
}
