import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../ui'

// The figures the undertaking states itself under the ESRS version governing the year (provided values, family
// 'esrs'): each with its unit, and for an amount the currency it is stated in; a breakdown is stated member by member.
// Every value is attested by a second person before the statement uses it.

interface Providable {
  key: string; label: string; unit: string; period: string | null; breakdown: string | null
  members: Record<string, string> | null; input_only: boolean; currency_required: boolean; always?: boolean
}
interface Provided {
  provided_id: string; datapoint_key: string; value_num: number | null; value_text: string | null; status: string
  reporting_period_end: string | null; reporting_entity_id: string | null; currency: string | null; breakdown_member: string | null
  submitted_by: string | null; decided_by: string | null
}
const STATUS: Record<string, string> = { attested: 'var(--color-good)', pending: 'var(--color-warn)', rejected: 'var(--color-bad)' }
const input = 'rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]'

export default function EsrsFigures({ periodEnd, entity, closed }: { periodEnd: string; entity: string; closed: boolean }) {
  const qc = useQueryClient()
  const cat = useQuery({ queryKey: ['esrs-providable', periodEnd], queryFn: () =>
    api.get<{ version: string; datapoints: Providable[] }>(`/v1/provided/catalog?framework=esrs&period_end=${periodEnd}`) })
  const prov = useQuery({ queryKey: ['provided', 'esrs'], queryFn: () => api.get<{ provided: Provided[] }>('/v1/provided?framework=esrs') })
  const [open, setOpen] = useState<string | null>(null)
  const [val, setVal] = useState(''), [ccy, setCcy] = useState('EUR'), [member, setMember] = useState(''), [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const mine = (prov.data?.provided ?? []).filter(p => p.reporting_period_end === periodEnd && (p.reporting_entity_id ?? '') === entity)
  const submit = async (d: Providable) => {
    setBusy(true)
    try {
      const n = d.unit === 'boolean' ? (val === 'yes' ? 1 : val === 'no' ? 0 : NaN) : Number(val)
      if (val === '' || Number.isNaN(n)) { toast.error('Enter the value.'); return }
      await api.post('/v1/provided', {
        framework: 'esrs', datapoint_key: d.key, value_num: n, source: 'client', reporting_period_end: periodEnd,
        reporting_entity_id: entity || null, ...(d.currency_required ? { currency: ccy.toUpperCase() } : {}),
        ...(d.breakdown ? { breakdown_member: member } : {}), ...(closed ? { restatement_reason: why } : {}),
      })
      toast.success('Submitted — a second person attests it under Approvals')
      setOpen(null); setVal(''); setMember(''); setWhy('')
      qc.invalidateQueries({ queryKey: ['provided', 'esrs'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not submit the value.')) } finally { setBusy(false) }
  }
  if (cat.isError) return <div className="px-5 py-4 text-[12.5px] text-[var(--color-mute)]">{apiMessage(cat.error, 'Not available.')}</div>
  const all = cat.data?.datapoints ?? []
  return (
    <div>
      {GROUPS.map(g => {
        const rows = all.filter(d => g.match(d.key))
        if (!rows.length) return null
        const n = rows.filter(d => mine.some(p => p.datapoint_key === d.key)).length
        return (
          <details key={g.label} open={g.open} className="border-t border-[var(--color-line)] first:border-t-0">
            <summary className="px-5 py-2.5 cursor-pointer text-[12.5px] text-[var(--color-ink)] flex items-center justify-between">
              <span>{g.label}</span><span className="mono text-[10.5px] text-[var(--color-faint)]">{n} of {rows.length} stated</span>
            </summary>
            <div className="divide-y divide-[var(--color-line)]">{rows.map(d => row(d))}</div>
          </details>
        )
      })}
    </div>
  )

  function row(d: Providable) {
        const vals = mine.filter(p => p.datapoint_key === d.key)
        return (
          <div key={d.key} className="px-5 py-2.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[12.5px] text-[var(--color-ink)]">{d.label}</div>
                <div className="mono text-[10.5px] text-[var(--color-faint)]">{d.key} · {d.unit}{d.period ? ` · ${d.period}` : ''}{d.breakdown ? ` · by ${d.breakdown}` : ''}{d.input_only ? ' · used to compute a ratio' : ''}</div>
              </div>
              {open !== d.key && <button onClick={() => { setOpen(d.key); setVal(''); setMember('') }} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline shrink-0">state it</button>}
            </div>
            {vals.length > 0 && <div className="mt-1 space-y-0.5">{vals.map(p => (
              <div key={p.provided_id} className="flex gap-2 text-[11.5px] tabular-nums">
                {p.breakdown_member && <span className="text-[var(--color-mute)]">{d.members?.[p.breakdown_member] ?? p.breakdown_member}:</span>}
                <span>{d.unit === 'boolean' ? (p.value_num ? 'yes' : 'no') : (p.value_num ?? p.value_text)?.toLocaleString()}{p.currency ? ` ${p.currency}` : ''}</span>
                <span className="mono text-[10px]" style={{ color: STATUS[p.status] ?? 'var(--color-mute)' }}>{p.status}</span>
              </div>))}</div>}
            {open === d.key && (
              <div className="mt-2 flex flex-wrap items-end gap-2">
                {d.breakdown && (d.members
                  ? <select aria-label="Member" value={member} onChange={e => setMember(e.target.value)} className={input}>
                      <option value="">member…</option>{Object.entries(d.members).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
                  : <input aria-label="Member" value={member} onChange={e => setMember(e.target.value)} className={input} placeholder={`name the ${d.breakdown.replace(/_/g, ' ')}`} />)}
                {d.unit === 'boolean'
                  ? <select aria-label="Value" value={val} onChange={e => setVal(e.target.value)} className={input}><option value="">—</option><option value="yes">yes</option><option value="no">no</option></select>
                  : <input aria-label="Value" type="number" step="any" value={val} onChange={e => setVal(e.target.value)} className={input} placeholder="value" />}
                {d.currency_required && <input aria-label="Currency" value={ccy} maxLength={3} onChange={e => setCcy(e.target.value)} className={`${input} w-16 uppercase`} />}
                {closed && <input aria-label="Restatement reason" value={why} onChange={e => setWhy(e.target.value)} className={`${input} w-64`} placeholder="the period is closed — why restate?" />}
                <Button variant="primary" onClick={() => submit(d)} disabled={busy || (!!d.breakdown && !member.trim())}>Submit</Button>
                <button onClick={() => setOpen(null)} className="mono text-[11px] text-[var(--color-mute)] hover:underline">cancel</button>
              </div>
            )}
          </div>
        )
  }
}

// who the undertaking is (Art. 5(2) facts) and its method first; the standards' own figures after
const GROUPS: { label: string; open: boolean; match: (k: string) => boolean }[] = [
  { label: 'The undertaking — size, status and publication (Art. 5(2); the deadline)', open: true, match: k => k.startsWith('csrd.') },
  { label: 'Method — the materiality level', open: true, match: k => k.startsWith('esrs.method.') },
  { label: 'Financial statements', open: false, match: k => k.startsWith('fs.') },
  { label: 'E1 Climate change', open: false, match: k => k.startsWith('e1.') },
  { label: 'E3 Water and marine resources', open: false, match: k => k.startsWith('e3.') },
  { label: 'E4 Biodiversity and ecosystems', open: false, match: k => k.startsWith('e4.') },
]
