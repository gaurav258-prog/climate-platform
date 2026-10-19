import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { api, apiMessage, apiDetail } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../ui'
import { HEADING, InfoButton, MessageLine } from '../Details'
import { StatusChip } from '../StatusChip'
import { Meter, SidePanel } from '../sfdr/visuals'
import { ATTEST, GROUPS, groupOf, unitWord } from './words'

// The figures the undertaking states itself under the version governing the year: each group's progress on the main
// screen, the figures of a group in a side panel — each with its unit, and for an amount the currency it is stated in; a
// breakdown is stated member by member. Every value is attested by a second person before the statement uses it.

interface Providable {
  key: string; label: string; short?: string | null; unit: string; period: string | null; breakdown: string | null
  members: Record<string, string> | null; input_only: boolean; currency_required: boolean; always?: boolean
}
interface Provided {
  provided_id: string; datapoint_key: string; value_num: number | null; value_text: string | null; status: string
  reporting_period_end: string | null; reporting_entity_id: string | null; currency: string | null; breakdown_member: string | null
}
const input = 'rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]'
const PERIOD: Record<string, string> = { flow: 'Over the year', stock: 'At the year end' }

export default function EsrsFigures({ periodEnd, entity, closed }: { periodEnd: string; entity: string; closed: boolean }) {
  const cat = useQuery({ queryKey: ['esrs-providable', periodEnd], queryFn: () =>
    api.get<{ version: string; datapoints: Providable[] }>(`/v1/provided/catalog?framework=esrs&period_end=${periodEnd}`) })
  const prov = useQuery({ queryKey: ['provided', 'esrs'], queryFn: () => api.get<{ provided: Provided[] }>('/v1/provided?framework=esrs') })
  const [open, setOpen] = useState<string | null>(null)
  if (cat.isError) return <div className="px-5 py-4"><MessageLine m={{ label: apiMessage(cat.error, 'Not available.'), detail: apiDetail(cat.error) }} className="text-[12.5px] text-[var(--color-mute)]" /></div>
  const all = cat.data?.datapoints ?? []
  const mine = (prov.data?.provided ?? []).filter(p => p.reporting_period_end === periodEnd && (p.reporting_entity_id ?? '') === entity)
  const groups = GROUPS.map(g => {
    const rows = all.filter(d => groupOf(d.key) === g.label)
    return { ...g, rows, n: rows.filter(d => mine.some(p => p.datapoint_key === d.key)).length,
      pending: mine.filter(p => rows.some(d => d.key === p.datapoint_key) && p.status === 'pending').length }
  }).filter(g => g.rows.length)
  const group = groups.find(g => g.label === open)

  return (
    <div className="grid gap-2.5 p-5 sm:grid-cols-2 lg:grid-cols-3">
      {groups.map(g => (
        <button key={g.label} type="button" onClick={() => setOpen(g.label)}
          className="text-left rounded-lg border border-[var(--color-line-2)] px-3.5 py-3 hover:border-[var(--color-sky)] transition flex items-center justify-between gap-3">
          <span className="min-w-0 space-y-1.5">
            <span className="block text-[13px] text-[var(--color-ink)]">{g.label}</span>
            <span className="flex items-center gap-2 text-[11.5px] text-[var(--color-faint)]">
              <Meter value={(g.n / g.rows.length) * 100} width="w-16" bare /> {g.n} of {g.rows.length} stated
            </span>
            {g.pending > 0 && <StatusChip tone="warn" label={`${g.pending} awaiting attestation`} />}
          </span>
          <ChevronRight size={15} className="text-[var(--color-faint)] shrink-0" />
        </button>))}
      {group && (
        <SidePanel title={group.label} wide onClose={() => setOpen(null)}
          about={{ title: group.label, sections: [{ heading: HEADING.shows, body: group.about }, { heading: HEADING.read, body: 'A value is used once a second person attests it under Approvals. Once the period is closed, a new value is a restatement and says why.' }] }}>
          <div className="divide-y divide-[var(--color-line)] -mx-6">
            {group.rows.map(d => <Row key={d.key} d={d} vals={mine.filter(p => p.datapoint_key === d.key)} periodEnd={periodEnd} entity={entity} closed={closed} />)}
          </div>
        </SidePanel>)}
    </div>
  )
}

function Row({ d, vals, periodEnd, entity, closed }: { d: Providable; vals: Provided[]; periodEnd: string; entity: string; closed: boolean }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [val, setVal] = useState(''), [ccy, setCcy] = useState('EUR'), [member, setMember] = useState(''), [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try {
      const n = d.unit === 'boolean' ? (val === 'yes' ? 1 : val === 'no' ? 0 : NaN) : Number(val)
      if (val === '' || Number.isNaN(n)) { toast.error('Enter the value.'); return }
      await api.post('/v1/provided', {
        framework: 'esrs', datapoint_key: d.key, value_num: n, source: 'client', reporting_period_end: periodEnd,
        reporting_entity_id: entity || null, ...(d.currency_required ? { currency: ccy.toUpperCase() } : {}),
        ...(d.breakdown ? { breakdown_member: member } : {}), ...(closed ? { restatement_reason: why } : {}),
      })
      toast.success('Sent — a second person attests it under Approvals')
      setOpen(false); setVal(''); setMember(''); setWhy('')
      qc.invalidateQueries({ queryKey: ['provided', 'esrs'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not send the value.')) } finally { setBusy(false) }
  }
  const unit = unitWord(d.unit)
  return (
    <div className="px-6 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-ink)]">
            {d.short ?? d.label}
            <InfoButton compact details={{ title: d.short ?? d.label, sections: [
              { heading: 'Definition', body: d.label },
              { heading: 'How it is stated', body: [unit && `In ${unit}`, d.period && PERIOD[d.period], d.breakdown && 'One value for each part of its breakdown', d.input_only && 'Used to compute a share; not printed by itself'].filter(Boolean).join('. ') + '.' }] }} />
          </div>
          {vals.length > 0 && <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">{vals.map(p => (
            <span key={p.provided_id} className="inline-flex items-center gap-1.5 text-[12px] tabular-nums">
              {p.breakdown_member && <span className="text-[var(--color-mute)]">{d.members?.[p.breakdown_member] ?? p.breakdown_member}:</span>}
              <span className="text-[var(--color-ink)]">{d.unit === 'boolean' ? (p.value_num ? 'Yes' : 'No') : (p.value_num ?? p.value_text)?.toLocaleString()}{p.currency ? ` ${p.currency}` : ''}</span>
              <StatusChip tone={ATTEST[p.status]?.tone ?? 'neutral'} label={ATTEST[p.status]?.label ?? 'Recorded'} />
            </span>))}</div>}
        </div>
        {!open && <Button variant="ghost" onClick={() => setOpen(true)}>{vals.length ? 'Restate' : 'State it'}</Button>}
      </div>
      {open && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          {d.breakdown && (d.members
            ? <select aria-label="Part" value={member} onChange={e => setMember(e.target.value)} className={input}>
                <option value="">Which part…</option>{Object.entries(d.members).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
            : <input aria-label="Part" value={member} onChange={e => setMember(e.target.value)} className={input} placeholder="Name the part" />)}
          {d.unit === 'boolean'
            ? <select aria-label="Value" value={val} onChange={e => setVal(e.target.value)} className={input}><option value="">—</option><option value="yes">Yes</option><option value="no">No</option></select>
            : <input aria-label="Value" type="number" step="any" value={val} onChange={e => setVal(e.target.value)} className={input} placeholder="Value" />}
          {d.currency_required && <input aria-label="Currency" value={ccy} maxLength={3} onChange={e => setCcy(e.target.value)} className={`${input} w-16 uppercase`} />}
          {closed && <input aria-label="Why it is restated" value={why} onChange={e => setWhy(e.target.value)} className={`${input} w-64`} placeholder="The period is closed — why restate?" />}
          <Button variant="primary" onClick={submit} disabled={busy || (!!d.breakdown && !member.trim())}>Send for attestation</Button>
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      )}
    </div>
  )
}
