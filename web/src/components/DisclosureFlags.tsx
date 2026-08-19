import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Flag, Check, X } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, SectionHead } from './ui'

// Act → Report bridge: exposures an approved 'disclose' decision flagged for the next climate filing. The
// reporting team sees, in the cockpit, what Risk wants surfaced this period, and marks each included or
// dismissed. Only shown when there are open flags.

interface FlagRow { flag_id: string; entity_name: string | null; scenario: string | null; horizon: string | null; by: string | null; at: string }
const SCEN: Record<string, string> = { baseline: 'Today', orderly_1_5c: 'Orderly 1.5°C', disorderly_2c: 'Disorderly 2°C', hot_house_3_5c: 'Hot-house 3.5°C' }

export default function DisclosureFlags() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canAct = (profile?.permissions ?? []).includes('approvals.create')
  const q = useQuery({ queryKey: ['disclosure-flags'], queryFn: () => api.get<{ flags: FlagRow[] }>('/v1/decisions/disclosure-flags') })
  const flags = q.data?.flags ?? []
  if (flags.length === 0) return null
  const resolve = async (id: string, status: 'included' | 'dismissed') => {
    try { await api.post(`/v1/decisions/disclosure-flags/${id}/resolve?status=${status}`, {}); qc.invalidateQueries({ queryKey: ['disclosure-flags'] }) }
    catch { /* no-op */ }
  }
  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
        <Flag size={15} className="text-[var(--scn-disorderly)]" />
        <SectionHead hint="from forward-risk decisions">Flagged for disclosure</SectionHead>
        <span className="ml-auto mono text-[10px] text-[var(--color-faint)]">{flags.length} exposure{flags.length === 1 ? '' : 's'}</span>
      </div>
      <div className="divide-y divide-[var(--color-line)]">
        {flags.map(f => (
          <div key={f.flag_id} className="px-5 py-2.5 flex items-center gap-3 text-[12.5px]">
            <div className="min-w-0 flex-1">
              <span className="text-[var(--color-ink)]">{f.entity_name ?? '—'}</span>
              <span className="mono text-[10px] text-[var(--color-faint)] ml-2">{SCEN[f.scenario ?? ''] ?? f.scenario} · {f.horizon} · {f.by?.split('@')[0]}</span>
            </div>
            {canAct && (
              <div className="flex items-center gap-1.5 shrink-0">
                <button onClick={() => resolve(f.flag_id, 'included')} title="Mark included in the filing" className="inline-flex items-center gap-1 mono text-[10px] uppercase tracking-wide px-2 py-1 rounded" style={{ color: 'var(--color-good)', background: 'color-mix(in oklab, var(--color-good) 14%, transparent)' }}><Check size={11} /> included</button>
                <button onClick={() => resolve(f.flag_id, 'dismissed')} title="Dismiss" className="text-[var(--color-faint)] hover:text-[var(--color-bad)]"><X size={13} /></button>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}
