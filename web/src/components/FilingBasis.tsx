import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { SlidersHorizontal, Check, X } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, Button } from './ui'

// The reporting-basis panel: the parameters every new filing freezes — scenario, horizon, materiality and
// reporting period. Read for everyone; editable for reports.publish, routed through the org's config
// governance (so a 4-eyes org gets an approval request instead of a direct change). Frozen filings are
// untouched — this only affects filings prepared AFTER the change.

interface Basis { scenario: string; horizon: string; materiality_threshold: number; reporting_period_end: string; is_override: boolean }

const SCENARIOS: [string, string][] = [['baseline', 'Today'], ['orderly_1_5c', 'Orderly 1.5°C'], ['disorderly_2c', 'Disorderly 2°C'], ['hot_house_3_5c', 'Hot-house 3.5°C']]
const HORIZONS: [string, string][] = [['current', 'Now'], ['2030', '2030'], ['2050', '2050'], ['2100', '2100']]
const scenLabel = (s: string) => SCENARIOS.find(x => x[0] === s)?.[1] ?? s
const horLabel = (h: string) => HORIZONS.find(x => x[0] === h)?.[1] ?? h

export default function FilingBasis() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canEdit = (profile?.permissions ?? []).includes('reports.publish')
  const q = useQuery({ queryKey: ['reporting-basis'], queryFn: () => api.get<Basis>('/v1/filings/reporting-basis') })
  const [edit, setEdit] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [form, setForm] = useState<Partial<Basis>>({})

  const b = q.data
  if (!b) return null
  const cur = { ...b, ...form }

  const save = async () => {
    setBusy(true); setMsg(null)
    try {
      const r = await api.patch<{ status: string; message?: string }>('/v1/filings/reporting-basis', {
        scenario: cur.scenario, horizon: cur.horizon,
        materiality_threshold: cur.materiality_threshold, reporting_period_end: cur.reporting_period_end,
      })
      qc.invalidateQueries({ queryKey: ['reporting-basis'] })
      setMsg(r.status === 'pending_approval' ? (r.message ?? 'Sent for approval (4-eyes).') : 'Basis updated. New filings will use it.')
      if (r.status !== 'pending_approval') setEdit(false)
      setForm({})
    } catch (e) { setMsg(e instanceof ApiError ? e.message : 'Could not update the basis.') }
    finally { setBusy(false) }
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]">
        <div className="flex items-center gap-2">
          <SlidersHorizontal size={15} className="text-[var(--color-sky)]" />
          <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Reporting basis · what new filings freeze</span>
        </div>
        {canEdit && !edit && <button onClick={() => setEdit(true)} className="mono text-[11px] text-[var(--color-sky)] hover:underline">change</button>}
        {edit && <button onClick={() => { setEdit(false); setForm({}); setMsg(null) }} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={15} /></button>}
      </div>

      {!edit ? (
        <div className="px-5 py-3 flex flex-wrap gap-x-8 gap-y-2 text-[13px]">
          <Fact k="Scenario" v={scenLabel(b.scenario)} />
          <Fact k="Horizon" v={horLabel(b.horizon)} />
          <Fact k="Materiality" v={`${b.materiality_threshold}/100`} />
          <Fact k="Period end" v={b.reporting_period_end} />
          {!canEdit && <span className="text-[11px] text-[var(--color-faint)] self-center">set by a reporting admin</span>}
        </div>
      ) : (
        <div className="px-5 py-4 space-y-3">
          <Segmented label="Scenario" options={SCENARIOS} value={cur.scenario} onChange={v => setForm(f => ({ ...f, scenario: v }))} />
          <Segmented label="Horizon" options={HORIZONS} value={cur.horizon} onChange={v => setForm(f => ({ ...f, horizon: v }))} />
          <div className="flex items-center gap-3">
            <span className="w-24 text-[12px] text-[var(--color-mute)]">Materiality</span>
            <input type="range" min={0} max={100} value={cur.materiality_threshold} onChange={e => setForm(f => ({ ...f, materiality_threshold: Number(e.target.value) }))} className="flex-1 accent-[var(--color-sky)]" />
            <span className="w-12 text-right mono text-[13px]">{cur.materiality_threshold}/100</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-24 text-[12px] text-[var(--color-mute)]">Period end</span>
            <input type="date" value={cur.reporting_period_end} onChange={e => setForm(f => ({ ...f, reporting_period_end: e.target.value }))}
              className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]" />
          </div>
          <div className="flex items-center gap-3 pt-1">
            <Button variant="primary" onClick={save} disabled={busy}><Check size={14} /> Save basis</Button>
            <span className="text-[11px] text-[var(--color-faint)]">Applies to filings prepared after this. Frozen filings are unchanged.</span>
          </div>
        </div>
      )}
      {msg && <div className="px-5 pb-3 text-[12px] text-[var(--color-mute)]">{msg}</div>}
    </Card>
  )
}

function Fact({ k, v }: { k: string; v: string }) {
  return <div><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mr-2">{k}</span><span className="text-[var(--color-ink)]">{v}</span></div>
}

function Segmented({ label, options, value, onChange }: { label: string; options: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-24 text-[12px] text-[var(--color-mute)]">{label}</span>
      <div className="flex flex-wrap gap-1">
        {options.map(([k, lbl]) => (
          <button key={k} onClick={() => onChange(k)} className={`px-2.5 py-1 rounded-md text-[12px] transition ${value === k ? 'bg-[var(--color-sky)] text-[#08111f]' : 'border border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{lbl}</button>
        ))}
      </div>
    </div>
  )
}
