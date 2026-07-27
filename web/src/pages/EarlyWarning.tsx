import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Eyebrow, Card } from '../components/ui'
import { Radio } from 'lucide-react'

interface Alert { commodity: string; hazard: string; avg_hazard: number; level: string; spend_eur: number }
interface Signals { n_alerts: number; alerts: Alert[]; pending: { commodity: string; spend_eur: number }[] }

const eur = (n?: number | null) => n == null ? '—' : `€${(n / 1e6).toFixed(1)}m`
const LEVEL: Record<string, string> = {
  VH: 'var(--color-bad)', H: 'var(--color-bad)', M: 'var(--color-warn)', L: 'var(--color-good)',
}

export default function EarlyWarning() {
  const q = useQuery({ queryKey: ['signals'], queryFn: () => api.get<Signals>('/v1/supply/signals') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — is the API on :8001?</Center>
  const d = q.data
  const alerts = [...d.alerts].sort((a, b) => b.avg_hazard - a.avg_hazard)

  return (
    <div className="fadeup space-y-7">
      <div>
        <Eyebrow>Agriculture · sense</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Early warning</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Commodities whose sourcing plots are under elevated hazard right now — the signal that lets you act before
          the shortfall, not after the harvest.
        </p>
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4"><Radio size={16} className="text-[var(--color-warn)]" />
          <div className="text-[13px] font-semibold">{d.n_alerts} live alert{d.n_alerts === 1 ? '' : 's'}</div></div>
        {alerts.length === 0 ? <div className="text-[13px] text-[var(--color-mute)]">No elevated hazard on the book right now.</div> :
          <div className="space-y-2">
            {alerts.map((a, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-[var(--color-line)] px-4 py-3">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: LEVEL[a.level] ?? 'var(--color-slate)' }} />
                <span className="text-[14px] font-medium">{a.commodity}</span>
                <span className="mono text-[11px] text-[var(--color-mute)]">{a.hazard} · {a.avg_hazard}</span>
                <span className="ml-auto mono text-[12px] text-[var(--color-mute)]">{eur(a.spend_eur)} spend</span>
              </div>
            ))}
          </div>}
      </Card>

      {d.pending.length > 0 &&
        <Card className="p-5">
          <div className="text-[13px] font-semibold mb-1">Exposure mapped, awaiting a scored signal</div>
          <p className="text-[12px] text-[var(--color-faint)] mb-3">These commodities are in the book but not yet scored on a live hazard — no false alarm, no false calm.</p>
          <div className="flex flex-wrap gap-2">
            {d.pending.map((p, i) => (
              <span key={i} className="mono text-[12px] px-3 py-1.5 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)]">
                {p.commodity} <span className="text-[var(--color-faint)]">· {eur(p.spend_eur)}</span>
              </span>
            ))}
          </div>
        </Card>}
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
