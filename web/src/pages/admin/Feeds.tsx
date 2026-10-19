import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, CloudRain, Database, Landmark, Leaf, RefreshCw } from 'lucide-react'
import { api } from '../../lib/api'
import { Card, SectionHead } from '../../components/ui'
import { Drawer } from '../../components/Drawer'
import { CloseButton } from '../../components/Dialog'
import { HEADING, InfoButton } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { ago, refused } from './parts'

// The data sources the figures are computed from: per kind, a bar of where its sources stand; a kind opens a drawer
// with each source, its schedule and when it last refreshed.

interface Feed { key: string; name: string; category: string; cadence_days: number; status: string; maturity?: string; auto_refresh?: boolean
  last_refresh: string | null; next_due_days?: number | null }
type Tone = 'good' | 'warn' | 'bad' | 'neutral'
// where a scheduled source stands, and what an unscheduled one is
const STATUS: Record<string, { label: string; tone: Tone }> = {
  fresh: { label: 'Current', tone: 'good' }, due_soon: { label: 'Due soon', tone: 'warn' }, overdue: { label: 'Overdue', tone: 'bad' },
  failed: { label: 'Last refresh failed', tone: 'bad' }, untracked: { label: 'Not refreshed yet', tone: 'neutral' },
}
const KIND: Record<string, { label: string; tone: Tone }> = {
  live: { label: 'Live', tone: 'good' }, release: { label: 'Fixed release', tone: 'good' }, on_demand: { label: 'Read when needed', tone: 'neutral' },
  partial: { label: 'Partly in use', tone: 'warn' }, proxy: { label: 'Stand-in source', tone: 'warn' }, estimated: { label: 'Estimated', tone: 'neutral' },
  planned: { label: 'Not yet available', tone: 'neutral' },
}
const TONE: Record<Tone, string> = { good: 'var(--color-good)', warn: 'var(--color-warn)', bad: 'var(--color-bad)', neutral: 'var(--color-slate)' }
const every = (d: number) => d === 1 ? 'Every day' : `Every ${d} days`
const nextIn = (d: number) => { const n = Math.ceil(d); return n <= 0 ? 'due now' : n === 1 ? 'next tomorrow' : `next in ${n} days` }
const stand = (f: Feed) => (f.auto_refresh ? STATUS[f.status] : KIND[f.maturity ?? '']) ?? { label: 'Not refreshed yet', tone: 'neutral' as Tone }
const CATEGORIES = [
  { key: 'hazard', label: 'Climate and hazard', icon: CloudRain },
  { key: 'nature', label: 'Nature', icon: Leaf },
  { key: 'reference', label: 'Reference data', icon: Landmark },
]
const ABOUT = {
  title: 'Data sources', sections: [
    { heading: HEADING.shows, body: 'The satellite, agency and reference sources your figures are computed from, grouped by kind.' },
    { heading: HEADING.read, body: 'Each bar shows where a kind’s sources stand. Scheduled sources refresh on their own; one that is overdue or whose last refresh failed is raised before it can reach a filing. Others are read when needed, fixed to a published release, or not yet available.' },
  ],
}

export function Feeds() {
  const q = useQuery({ queryKey: ['data-feeds'], queryFn: () => api.get<{ feeds: Feed[] }>('/v1/admin/data-feeds') })
  const [open, setOpen] = useState<string | null>(null)
  const feeds = q.data?.feeds ?? []
  const cat = CATEGORIES.find(c => c.key === open)
  return (
    <Card className="p-5">
      <SectionHead icon={Database} className="gap-1.5 mb-4">Data sources <InfoButton compact details={ABOUT} /></SectionHead>
      {q.isLoading ? <div className="text-[13px] text-[var(--color-faint)] py-2">Loading…</div> : (
        <div className="grid gap-3 md:grid-cols-3">
          {CATEGORIES.filter(c => feeds.some(f => f.category === c.key)).map(c => {
            const fs = feeds.filter(f => f.category === c.key)
            const counts = (['bad', 'warn', 'good', 'neutral'] as Tone[]).map(t => ({ t, n: fs.filter(f => stand(f).tone === t).length })).filter(x => x.n)
            return (
              <button key={c.key} onClick={() => setOpen(c.key)} className="text-left rounded-xl border border-[var(--color-line)] p-3.5 hover:border-[var(--color-sky)] transition">
                <div className="flex items-center gap-2 mb-2.5">
                  <c.icon size={16} className="text-[var(--color-blue)]" />
                  <span className="text-[13.5px] font-medium text-[var(--color-ink)]">{c.label}</span>
                  <span className="text-[12px] text-[var(--color-faint)] tabular-nums">{fs.length}</span>
                  <ChevronRight size={14} className="ml-auto text-[var(--color-faint)]" />
                </div>
                <div className="flex h-2 rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label={counts.map(x => `${x.n} ${x.t}`).join(', ')}>
                  {counts.map(x => <span key={x.t} style={{ width: `${(100 * x.n) / fs.length}%`, background: TONE[x.t], opacity: 0.85 }} />)}
                </div>
                <div className="mt-2 text-[12px] text-[var(--color-mute)]">
                  {counts.some(x => x.t === 'bad') ? `${counts.find(x => x.t === 'bad')!.n} need attention` : counts.some(x => x.t === 'warn') ? `${counts.find(x => x.t === 'warn')!.n} to watch` : 'All in order'}
                </div>
              </button>
            )
          })}
        </div>
      )}
      {cat && <FeedDrawer title={cat.label} feeds={feeds.filter(f => f.category === cat.key)} onClose={() => setOpen(null)} onRefreshed={() => q.refetch()} />}
    </Card>
  )
}

function FeedDrawer({ title, feeds, onClose, onRefreshed }: { title: string; feeds: Feed[]; onClose: () => void; onRefreshed: () => void }) {
  const [busy, setBusy] = useState<string | null>(null)
  const refresh = async (k: string) => {
    setBusy(k)
    try { await api.post(`/v1/admin/data-feeds/${k}/refresh`, {}); onRefreshed() } catch (e) { refused(e, 'The source could not be refreshed.') } finally { setBusy(null) }
  }
  return (
    <Drawer label={title} onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-6 space-y-4">
      <div className="flex items-center justify-between"><SectionHead>{title}</SectionHead><CloseButton onClick={onClose} /></div>
      <ul className="space-y-2 m-0 p-0 list-none">
        {feeds.map(f => {
          const s = stand(f)
          return (
            <li key={f.key} className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg)] px-3.5 py-2.5">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] text-[var(--color-ink)]">{f.name}</div>
                  <div className="text-[12px] text-[var(--color-faint)] mt-0.5">
                    {f.auto_refresh ? `${every(f.cadence_days)} · refreshed ${ago(f.last_refresh)}${f.next_due_days != null ? ` · ${nextIn(f.next_due_days)}` : ''}` : s.label}
                  </div>
                </div>
                <StatusChip tone={s.tone} label={s.label} />
              </div>
              {f.auto_refresh && (
                <button onClick={() => refresh(f.key)} disabled={busy === f.key}
                  className="mt-2 inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)] disabled:opacity-50">
                  <RefreshCw size={12} className={busy === f.key ? 'animate-spin' : ''} /> {busy === f.key ? 'Refreshing…' : 'Refresh now'}
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </Drawer>
  )
}
