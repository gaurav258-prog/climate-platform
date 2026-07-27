import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Map, ShieldCheck, FileCheck2, Boxes } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, Stat, Button } from '../components/ui'
import LiveEarthHero from '../components/LiveEarthHero'

interface Summary {
  rollup: { volume_at_risk_eur: number; pct_cogs_at_risk: number }
  eudr: { summary: Record<string, number> }
}

const eur = (n?: number | null) => n == null ? '—' : `€${(n / 1e6).toFixed(1)}m`

const LINKS = [
  { to: '/disclosure', icon: ShieldCheck, label: 'Disclosure & EUDR', sub: 'the deforestation-free check + DDS' },
  { to: '/cogs', icon: Boxes, label: 'COGS-at-risk', sub: 'the volume that won’t arrive' },
  { to: '/riskmap', icon: Map, label: 'Risk map', sub: 'every plot by live hazard' },
  { to: '/models', icon: FileCheck2, label: 'Models & validation', sub: 'why the numbers hold up' },
]

export default function Home() {
  const nav = useNavigate()
  const { profile } = useAuth()
  const q = useQuery({ queryKey: ['summary'], queryFn: () => api.get<Summary>('/v1/supply/summary') })
  const s = q.data?.eudr.summary ?? {}

  return (
    <div className="fadeup space-y-7">
      <LiveEarthHero height="60vh">
        <div className="display text-[clamp(40px,7vw,76px)] font-semibold italic leading-none text-[#F4EFE6]">
          Tel<span className="text-[var(--color-sky)]">lumen</span>
        </div>
        <div className="mono mt-3 text-[11px] uppercase tracking-[0.28em] text-[var(--color-blue)]">Light on the Earth</div>
        <p className="display italic mt-8 max-w-2xl text-[clamp(22px,3.4vw,38px)] font-light leading-tight text-[#F4EFE6]">
          See what’s coming. <span className="text-[var(--color-sky)]">Any place on Earth.</span>
        </p>
        <p className="mt-4 max-w-xl text-[15px] text-[#c7d3e6]">
          Live satellite &amp; sensor data on every sourcing plot — turned into one defensible number, and the EUDR
          filing to go with it.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Button onClick={() => nav('/disclosure')}>Open the workspace <ArrowRight size={15} /></Button>
          <Button variant="ghost" onClick={() => nav('/riskmap')}>See the risk map</Button>
        </div>
      </LiveEarthHero>

      <div className="grid sm:grid-cols-4 gap-4">
        <Stat big={eur(q.data?.rollup.volume_at_risk_eur)} label="volume at risk (physical)" tone="warn" />
        <Stat big={`${(q.data?.rollup.pct_cogs_at_risk ?? 0).toFixed(2)}%`} label="of COGS" />
        <Stat big={s.covered_plots ?? '—'} label="EUDR-covered plots" />
        <Stat big={s.deforestation_free ?? '—'} label="deforestation-free" tone="good" />
      </div>

      <div>
        <div className="mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-faint)] mb-3">
          {profile?.org?.name} · agriculture workspace
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {LINKS.map(l => (
            <button key={l.to} onClick={() => nav(l.to)} className="text-left">
              <Card className="p-5 h-full hover:border-[var(--color-sky)] transition">
                <l.icon size={18} className="text-[var(--color-sky)] mb-3" />
                <div className="text-[14px] font-semibold">{l.label}</div>
                <div className="text-[12px] text-[var(--color-mute)] mt-1">{l.sub}</div>
              </Card>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
