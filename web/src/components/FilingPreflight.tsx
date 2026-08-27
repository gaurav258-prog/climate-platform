import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, CheckCircle2, AlertTriangle, Snowflake } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { Card, Button, SectionHead, StatGrid, type StatItem } from './ui'

// The confirm-data step: before a filing is frozen, the preparer reviews the basis, the data coverage and
// the headline figures, sees any gaps honestly, and ticks "I confirm this is the data to file". Only then
// is the snapshot frozen. This is the gate between "the live book" and an immutable filing.

interface Preflight {
  framework: string; label: string; period_label: string
  basis: { scenario: string; horizon: string; materiality_threshold: number; reporting_period_end: string }
  can_generate: boolean; existing_status: string | null; entity_scoped: boolean
  coverage: { label: string; done: number; total: number; pct: number } | null
  total_value_eur: number | null; value_at_risk_eur?: number | null; noun: string; positions?: number; gaps: string[]
}
interface Ent { entity_id: string; name: string; kind: string; parent_entity_id: string | null; n_assets: number }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`

export default function FilingPreflight({ framework, onClose, onGenerated }: { framework: string; onClose: () => void; onGenerated: (id: string) => void }) {
  const q = useQuery({ queryKey: ['preflight', framework], queryFn: () => api.get<Preflight>(`/v1/filings/preflight?framework=${framework}`) })
  const ents = useQuery({ queryKey: ['filing-entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/filings/entities') })
  const [confirmed, setConfirmed] = useState(false)
  const [entityId, setEntityId] = useState<string>('')   // '' = whole organisation
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const d = q.data
  const entities = ents.data?.entities ?? []

  const freeze = async () => {
    setBusy(true); setErr(null)
    try {
      const f = await api.post<{ filing_id: string }>('/v1/filings', { framework, confirmed: true, entity_id: entityId || null })
      onGenerated(f.filing_id)
    } catch (e) { setErr(e instanceof ApiError ? e.message : 'Could not freeze the filing.') }
    finally { setBusy(false) }
  }
  // when a specific entity is chosen the backend's own (entity-aware) guard decides; only block whole-org
  // generation when a whole-org filing already exists.
  const blockedByExisting = entityId === '' && !d?.can_generate

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <Card className="relative w-full max-w-lg p-0 overflow-hidden" >
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]" onClick={e => e.stopPropagation()}>
          <SectionHead>Confirm the data before filing</SectionHead>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={17} /></button>
        </div>
        <div className="p-5 space-y-4" onClick={e => e.stopPropagation()}>
          {!d ? <div className="text-[13px] text-[var(--color-faint)]">checking the book…</div> : (<>
            <div>
              <h3 className="display text-lg font-semibold">{d.label}</h3>
              <div className="mono text-[11px] text-[var(--color-faint)]">{d.period_label} · basis {d.basis.scenario}/{d.basis.horizon} · materiality {d.basis.materiality_threshold}</div>
            </div>

            {entities.length > 0 && d.entity_scoped && (
              <div>
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Reporting scope</div>
                <select value={entityId} onChange={e => setEntityId(e.target.value)}
                  className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
                  <option value="">Whole organisation</option>
                  {entities.filter(e => e.kind === 'group').map(e => <option key={e.entity_id} value={e.entity_id}>Consolidated — {e.name} (group)</option>)}
                  {entities.filter(e => e.kind !== 'group').map(e => <option key={e.entity_id} value={e.entity_id}>{e.name} ({e.n_assets} assets)</option>)}
                </select>
                <div className="mono text-[10px] text-[var(--color-faint)] mt-1">a group consolidates its whole subtree (proportional lines ownership‑weighted); a legal entity files its own book.</div>
              </div>
            )}
            {entities.length > 0 && !d.entity_scoped && (
              <div className="mono text-[10px] text-[var(--color-faint)]">Files at whole-organisation level{d.framework === 'sfdr_pai' ? ' — per-fund SFDR statements are in the Funds workspace.' : '.'}</div>
            )}

            {blockedByExisting && (
              <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-warn)]">
                <AlertTriangle size={14} /> A live {d.label} for {d.period_label} (whole organisation) already exists ({d.existing_status}). Supersede it, or file a specific entity instead.
              </div>
            )}

            {(() => {
              const metrics: StatItem[] = [
                d.coverage
                  ? { label: d.coverage.label, value: `${d.coverage.pct}%`, sub: `${d.coverage.done}/${d.coverage.total}` }
                  : { label: 'coverage', value: '—', sub: `from your ${d.noun}` },
              ]
              if (d.total_value_eur != null) metrics.push({
                label: d.noun === 'positions' ? 'NAV in scope' : 'book value',
                value: eur(d.total_value_eur),
                sub: d.positions != null ? `${d.positions} positions` : (d.coverage ? `${d.coverage.total} ${d.noun}` : undefined),
              })
              if (d.value_at_risk_eur != null) metrics.push({ label: 'value at risk', value: eur(d.value_at_risk_eur) })
              return <StatGrid items={metrics} cols={3} />
            })()}

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
              <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5 accent-[var(--color-sky)]" disabled={blockedByExisting} />
              I confirm this is the data to file — freeze it as an immutable filing.
            </label>
            <div className="flex items-center gap-3">
              <Button variant="primary" onClick={freeze} disabled={busy || !confirmed || blockedByExisting}><Snowflake size={14} /> Confirm & freeze filing</Button>
              {confirmed && <span className="inline-flex items-center gap-1 text-[11px]" style={{ color: '#34d399' }}><CheckCircle2 size={12} /> ready</span>}
            </div>
          </>)}
        </div>
      </Card>
    </div>
  )
}
