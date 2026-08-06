import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, Check, Clock, AlertTriangle } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, Button } from './ui'

// Lane 2 — provided datapoints. A value calculated on the customer's or a vendor's side (own-operations GHG
// from a carbon tool, a Taxonomy alignment %, an audited PCAF figure) is submitted here, reconciled against
// Tellumen's own number where one exists, and attested through 4-eyes before it can land in a filing.

interface Req { framework: string; official_name?: string; label: string }
interface Providable { key: string; label: string; provider: string | null; note: string | null; kind: string }
interface Provided { provided_id: string; framework: string; datapoint_key: string; label: string; value_num: number | null; value_text: string | null; unit: string | null; source: string; provider_name: string | null; data_vintage: string | null; tellumen_value: number | null; delta_pct: number | null; within_tolerance: boolean | null; recon_note: string | null; status: string; submitted_by: string | null; decided_by: string | null }

export default function ProvidedData() {
  const { profile } = useAuth()
  const canAct = (profile?.permissions ?? []).includes('approvals.create')
  const rq = useQuery({ queryKey: ['requirements'], queryFn: () => api.get<{ requirements: Req[] }>('/v1/filings/requirements') })
  const pq = useQuery({ queryKey: ['provided'], queryFn: () => api.get<{ provided: Provided[] }>('/v1/provided') })
  const frameworks = rq.data?.requirements ?? []
  if (frameworks.length === 0) return null
  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
        <Upload size={15} className="text-[var(--color-sky)]" />
        <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Provided &amp; reconciled data · your inputs and vendor figures</span>
      </div>
      <div className="divide-y divide-[var(--color-line)]">
        {frameworks.map(f => <FrameworkBlock key={f.framework} framework={f.framework} label={f.official_name || f.label}
          provided={(pq.data?.provided ?? []).filter(p => p.framework === f.framework)} canAct={canAct} />)}
      </div>
    </Card>
  )
}

function FrameworkBlock({ framework, label, provided, canAct }: { framework: string; label: string; provided: Provided[]; canAct: boolean }) {
  const cq = useQuery({ queryKey: ['provided-catalog', framework], queryFn: () => api.get<{ datapoints: Providable[] }>(`/v1/provided/catalog?framework=${framework}`) })
  const dps = cq.data?.datapoints ?? []
  if (dps.length === 0) return null
  const byKey = Object.fromEntries(provided.map(p => [p.datapoint_key, p]))
  return (
    <div className="px-5 py-3">
      <div className="text-[13px] text-[var(--color-ink)] mb-2">{label}</div>
      <div className="space-y-1.5">
        {dps.map(dp => <Row key={dp.key} framework={framework} dp={dp} current={byKey[dp.key]} canAct={canAct} />)}
      </div>
    </div>
  )
}

const fmtNum = (n: number | null, unit: string | null) => n == null ? '—' : `${n >= 1e6 ? `${(n / 1e6).toFixed(2)}m` : n.toLocaleString('en-GB')}${unit ? ` ${unit}` : ''}`

function Row({ framework, dp, current, canAct }: { framework: string; dp: Providable; current?: Provided; canAct: boolean }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [val, setVal] = useState(''); const [unit, setUnit] = useState(''); const [source, setSource] = useState('client')
  const [provider, setProvider] = useState(''); const [vintage, setVintage] = useState(''); const [busy, setBusy] = useState(false)
  const save = async () => {
    if (!val.trim()) return
    setBusy(true)
    try {
      await api.post('/v1/provided', { framework, datapoint_key: dp.key, value_num: Number(val), unit: unit || undefined, source, provider_name: provider || undefined, data_vintage: vintage || undefined })
      setOpen(false); setVal(''); qc.invalidateQueries({ queryKey: ['provided'] })
    } catch (e) { alert(e instanceof ApiError ? e.message : 'Could not submit the value.') }
    finally { setBusy(false) }
  }
  const st = current?.status
  return (
    <div className="text-[12px]">
      <div className="flex items-start gap-3">
        <span className="mono text-[8px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 w-16 text-center"
          style={dp.kind === 'required' ? { color: '#f0a860', background: 'color-mix(in oklab, #f0a860 14%, transparent)' } : { color: 'var(--color-sky)', background: 'color-mix(in oklab, var(--color-sky) 14%, transparent)' }}>
          {dp.kind === 'required' ? 'provide' : 'reconcile'}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[var(--color-mute)]">{dp.label}</div>
          {current
            ? <div className="mono text-[10px] mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="text-[var(--color-ink)]">{fmtNum(current.value_num, current.unit)}</span>
                <span className="text-[var(--color-faint)]">{current.source}{current.provider_name ? ` · ${current.provider_name}` : ''}{current.data_vintage ? ` · ${current.data_vintage}` : ''}</span>
                {current.delta_pct != null && <span style={{ color: current.within_tolerance ? 'var(--color-good)' : 'var(--color-bad)' }}>{current.within_tolerance ? <Check size={10} className="inline" /> : <AlertTriangle size={10} className="inline" />} {current.delta_pct > 0 ? '+' : ''}{current.delta_pct}% vs ours</span>}
                <span className="inline-flex items-center gap-1" style={{ color: st === 'attested' ? 'var(--color-good)' : st === 'rejected' ? 'var(--color-bad)' : 'var(--color-warn)' }}>{st === 'attested' ? <Check size={10} /> : <Clock size={10} />} {st}{st === 'pending' ? ' · awaiting 4-eyes' : current.decided_by ? ` · ${current.decided_by.split('@')[0]}` : ''}</span>
              </div>
            : <div className="mono text-[9.5px] text-[var(--color-faint)] mt-0.5">{dp.provider}</div>}
        </div>
        {canAct && <button onClick={() => setOpen(o => !o)} className="mono text-[10px] text-[var(--color-sky)] hover:underline shrink-0">{current ? 'replace' : 'provide'}</button>}
      </div>
      {open && canAct && (
        <div className="mt-2 ml-[76px] flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] p-2.5">
          <input value={val} onChange={e => setVal(e.target.value)} type="number" step="any" placeholder="value"
            className="w-28 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] mono outline-none focus:border-[var(--color-sky)]" />
          <input value={unit} onChange={e => setUnit(e.target.value)} placeholder="unit"
            className="w-20 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] mono outline-none" />
          <select value={source} onChange={e => setSource(e.target.value)} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] outline-none"><option value="client">client</option><option value="vendor">vendor</option></select>
          <input value={provider} onChange={e => setProvider(e.target.value)} placeholder="source name (e.g. carbon tool)"
            className="flex-1 min-w-[140px] bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] outline-none" />
          <input value={vintage} onChange={e => setVintage(e.target.value)} type="date" title="Data vintage"
            className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] mono outline-none" />
          <Button variant="primary" onClick={save} disabled={busy || !val.trim()}><Check size={12} /> submit for attest</Button>
          <button onClick={() => setOpen(false)} className="text-[11px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">cancel</button>
        </div>
      )}
    </div>
  )
}
