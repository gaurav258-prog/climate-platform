import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, CheckCircle2, AlertTriangle, Snowflake } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { Card, Button } from './ui'

// The confirm-data step: before a filing is frozen, the preparer reviews the basis, the data coverage and
// the headline figures, sees any gaps honestly, and ticks "I confirm this is the data to file". Only then
// is the snapshot frozen. This is the gate between "the live book" and an immutable filing.

interface Preflight {
  framework: string; label: string; period_label: string
  basis: { scenario: string; horizon: string; materiality_threshold: number; reporting_period_end: string }
  can_generate: boolean; existing_status: string | null
  coverage: { label: string; done: number; total: number; pct: number } | null
  total_value_eur: number | null; value_at_risk_eur?: number | null; noun: string; positions?: number; gaps: string[]
}

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`

export default function FilingPreflight({ framework, onClose, onGenerated }: { framework: string; onClose: () => void; onGenerated: (id: string) => void }) {
  const q = useQuery({ queryKey: ['preflight', framework], queryFn: () => api.get<Preflight>(`/v1/filings/preflight?framework=${framework}`) })
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const d = q.data

  const freeze = async () => {
    setBusy(true); setErr(null)
    try {
      const f = await api.post<{ filing_id: string }>('/v1/filings', { framework, confirmed: true })
      onGenerated(f.filing_id)
    } catch (e) { setErr(e instanceof ApiError ? e.message : 'Could not freeze the filing.') }
    finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <Card className="relative w-full max-w-lg p-0 overflow-hidden" >
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]" onClick={e => e.stopPropagation()}>
          <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Confirm the data before filing</span>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={17} /></button>
        </div>
        <div className="p-5 space-y-4" onClick={e => e.stopPropagation()}>
          {!d ? <div className="text-[13px] text-[var(--color-faint)]">checking the book…</div> : (<>
            <div>
              <h3 className="display text-lg font-semibold">{d.label}</h3>
              <div className="mono text-[11px] text-[var(--color-faint)]">{d.period_label} · basis {d.basis.scenario}/{d.basis.horizon} · materiality {d.basis.materiality_threshold}</div>
            </div>

            {!d.can_generate && (
              <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-warn)]">
                <AlertTriangle size={14} /> A live {d.label} for {d.period_label} already exists ({d.existing_status}). Supersede it to restate.
              </div>
            )}

            <div className="grid grid-cols-3 gap-3">
              {d.coverage
                ? <Stat big={`${d.coverage.pct}%`} label={d.coverage.label} sub={`${d.coverage.done}/${d.coverage.total}`} />
                : <Stat big="—" label="coverage" sub={`from your ${d.noun}`} />}
              {d.total_value_eur != null
                ? <Stat big={eur(d.total_value_eur)} label={d.noun === 'positions' ? 'NAV in scope' : 'book value'} sub={d.positions != null ? `${d.positions} positions` : (d.coverage ? `${d.coverage.total} ${d.noun}` : '')} />
                : <div />}
              {d.value_at_risk_eur != null ? <Stat big={eur(d.value_at_risk_eur)} label="value at risk" /> : <div />}
            </div>

            {d.gaps.length > 0 && (
              <div className="rounded-lg border border-[var(--color-line-2)] p-3">
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Known gaps — will be disclosed as-is</div>
                <ul className="space-y-1">
                  {d.gaps.map((g, i) => <li key={i} className="flex items-start gap-1.5 text-[12px] text-[var(--color-mute)]"><AlertTriangle size={12} className="mt-0.5 text-[var(--color-warn)] shrink-0" />{g}</li>)}
                </ul>
              </div>
            )}

            {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}

            <label className="flex items-start gap-2 text-[12.5px] text-[var(--color-ink)] cursor-pointer">
              <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5 accent-[var(--color-sky)]" disabled={!d.can_generate} />
              I confirm this is the data to file — freeze it as an immutable filing.
            </label>
            <div className="flex items-center gap-3">
              <Button variant="primary" onClick={freeze} disabled={busy || !confirmed || !d.can_generate}><Snowflake size={14} /> Confirm & freeze filing</Button>
              {confirmed && <span className="inline-flex items-center gap-1 text-[11px]" style={{ color: '#34d399' }}><CheckCircle2 size={12} /> ready</span>}
            </div>
          </>)}
        </div>
      </Card>
    </div>
  )
}

function Stat({ big, label, sub }: { big: string; label: string; sub?: string }) {
  return (
    <div>
      <div className="display text-xl">{big}</div>
      <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-1">{label}</div>
      {sub && <div className="mono text-[10px] text-[var(--color-faint)]">{sub}</div>}
    </div>
  )
}
