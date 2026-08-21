import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { Card, PageHeader, SectionHead, PlainLead } from '../components/ui'
import { hazardLabel } from '../lib/hazards'
import { Radio, ChevronRight } from 'lucide-react'

interface Alert { commodity: string; hazard: string; avg_hazard: number; level: string; spend_eur: number }
interface Signals { n_alerts: number; alerts: Alert[]; pending: { commodity: string; spend_eur: number }[]; commodity_ids: Record<string, string> }

const eur = (n?: number | null) => n == null ? '—' : `€${(n / 1e6).toFixed(1)}m`
const LEVEL: Record<string, string> = {
  VH: 'var(--color-bad)', H: 'var(--color-bad)', M: 'var(--color-warn)', L: 'var(--color-good)',
}

export default function EarlyWarning() {
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['signals'], queryFn: () => api.get<Signals>('/v1/supply/signals') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — is the API on :8001?</Center>
  const d = q.data
  const alerts = [...d.alerts].sort((a, b) => b.avg_hazard - a.avg_hazard)
  const open = (commodity: string) => { const id = d.commodity_ids?.[commodity]; if (id) nav(`/detail/commodity/${id}`) }

  return (
    <div className="fadeup space-y-7">
      <PageHeader eyebrow="Agriculture · sense" title="Early warning"
        lead="Commodities whose sourcing plots are under elevated hazard right now — the signal that lets you act before the shortfall, not after the harvest." />

      <Card className="p-5">
        <SectionHead icon={Radio} className="mb-4">{d.n_alerts} live alert{d.n_alerts === 1 ? '' : 's'}</SectionHead>
        {alerts.length === 0 ? <div className="text-[13px] text-[var(--color-mute)]">No elevated hazard on the book right now.</div> :
          <div className="space-y-2">
            {alerts.map((a, i) => {
              const clickable = !!d.commodity_ids?.[a.commodity]
              return (
              <div key={i} onClick={() => open(a.commodity)}
                className={`flex items-center gap-3 rounded-lg border border-[var(--color-line)] px-4 py-3 ${clickable ? 'cursor-pointer hover:border-[var(--color-sky)] transition' : ''}`}>
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: LEVEL[a.level] ?? 'var(--color-slate)' }} />
                <span className="text-[14px] font-medium">{a.commodity}</span>
                <span className="mono text-[11px] text-[var(--color-mute)]">{hazardLabel(a.hazard)} · {a.avg_hazard}</span>
                <span className="ml-auto mono text-[12px] text-[var(--color-mute)]">{eur(a.spend_eur)} spend</span>
                {clickable && <ChevronRight size={15} className="text-[var(--color-faint)] shrink-0" />}
              </div>
              )
            })}
          </div>}
      </Card>

      {d.pending.length > 0 &&
        <Card className="p-5">
          <SectionHead className="mb-1">Exposure mapped, awaiting a scored signal</SectionHead>
          <PlainLead className="mb-3">These commodities are in the book but not yet scored on a live hazard — no false alarm, no false calm.</PlainLead>
          <div className="flex flex-wrap gap-2">
            {d.pending.map((p, i) => {
              const clickable = !!d.commodity_ids?.[p.commodity]
              return (
              <span key={i} onClick={() => open(p.commodity)}
                className={`mono text-[12px] px-3 py-1.5 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)] ${clickable ? 'cursor-pointer hover:border-[var(--color-sky)] hover:text-[var(--color-ink)] transition' : ''}`}>
                {p.commodity} <span className="text-[var(--color-faint)]">· {eur(p.spend_eur)}</span>
              </span>
              )
            })}
          </div>
        </Card>}
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
