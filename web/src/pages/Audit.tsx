import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Card, PageHeader } from '../components/ui'
import { actionLabel } from '../lib/actionLabels'

interface Row {
  id: string; action: string; target_type: string | null; target_id: string | null
  detail: Record<string, unknown> | null; actor_email: string | null; actor_name: string | null; created_at: string | null
}

const ACTION_TONE = (a: string) => a.includes('delete') ? 'text-[var(--color-bad)]' : a.includes('decide') || a.includes('approval') ? 'text-[var(--color-warn)]' : 'text-[var(--color-blue)]'
const fmtDetail = (d: Record<string, unknown> | null) => {
  if (!d) return ''
  const c = d.changes as Record<string, unknown> | undefined
  if (c && Object.keys(c).length) return Object.entries(c).map(([k, v]) => `${k}→${v}`).join(', ')
  if (d.decision) return `${d.decision}${d.reason ? ` (${d.reason})` : ''}`
  return Object.entries(d).filter(([k]) => k !== 'target_id').map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).slice(0, 3).join(' · ')
}

export default function Audit({ embedded = false }: { embedded?: boolean }) {
  const [actor, setActor] = useState('')
  const q = useQuery({ queryKey: ['audit', actor], queryFn: () => api.get<Row[]>(`/v1/admin/audit?limit=100${actor ? `&actor=${encodeURIComponent(actor)}` : ''}`) })
  const rows = q.data ?? []

  return (
    <div className={embedded ? 'space-y-6' : 'fadeup space-y-6'}>
      {!embedded && (
        <PageHeader eyebrow="Governance · accountability" title="Audit trail"
          lead="Every change — who did what, when, and (where it needed sign-off) who approved it. Immutable, append-only." />
      )}

      <input value={actor} onChange={e => setActor(e.target.value)} placeholder="filter by user email…"
        className="w-full max-w-sm bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />

      {q.isLoading ? <Center>loading…</Center> : rows.length === 0 ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">No audit entries.</Card> : (
        <Card className="p-0 overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
                <th className="font-normal py-2.5 px-4">When</th><th className="font-normal px-4">Who</th>
                <th className="font-normal px-4">Action</th><th className="font-normal px-4">Target</th><th className="font-normal px-4">Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-b border-[var(--color-line)] last:border-0">
                  <td className="py-2.5 px-4 mono text-[11px] text-[var(--color-mute)] whitespace-nowrap">{r.created_at ? new Date(r.created_at).toLocaleString() : '—'}</td>
                  <td className="px-4 text-[var(--color-ink)] whitespace-nowrap">{r.actor_email ?? '—'}</td>
                  <td className={`px-4 text-[12.5px] whitespace-nowrap ${ACTION_TONE(r.action)}`} title={r.action}>{actionLabel(r.action)}</td>
                  <td className="px-4 mono text-[11px] text-[var(--color-faint)] whitespace-nowrap">{r.target_type ?? ''}{r.target_id ? ` ${String(r.target_id).slice(0, 8)}` : ''}</td>
                  <td className="px-4 text-[var(--color-mute)]">{fmtDetail(r.detail)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[40vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
