import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Eyebrow, Card, Stat } from '../components/ui'
import { hazardLabel } from '../lib/hazards'
import { Radar, Upload, Boxes, ShieldCheck, RefreshCw, Lock } from 'lucide-react'
import LiveEarthHero from '../components/LiveEarthHero'
import SeasonalArrears from '../components/SeasonalArrears'

interface Scores { total_current_scores: number; hazards: { hazard_type: string; cells: number }[] }
const AGRI_HAZARDS = ['drought', 'heat_acute', 'soil_water']

const STEPS = [
  { k: 'Locate', d: 'Each plot’s lat-lon snaps to one ~0.7 km² H3 cell — the key everything joins on.' },
  { k: 'Score', d: 'That cell gets a 0–100 drought / heat score, now and under warming scenarios.' },
  { k: 'Project', d: 'Score × crop sensitivity × your spend = the euros at risk, plus the EUDR check.' },
]

export default function DataFoundation() {
  const q = useQuery({ queryKey: ['scores'], queryFn: () => api.get<Scores>('/v1/scores/summary') })
  const rows = q.data?.hazards.filter(h => AGRI_HAZARDS.includes(h.hazard_type)) ?? []
  const agriScores = rows.reduce((s, h) => s + h.cells, 0)
  const liveHazards = [...new Set(rows.map(h => hazardLabel(h.hazard_type)))]

  return (
    <div className="fadeup space-y-7">
      {/* live Earth-from-space banner — the data foundation's front door */}
      <LiveEarthHero height="34vh">
        <div className="display text-[clamp(24px,4vw,44px)] font-semibold italic leading-none text-[#F4EFE6]">
          Tel<span className="text-[var(--color-sky)]">lumen</span>
        </div>
        <p className="display italic mt-4 text-[clamp(15px,2.2vw,26px)] font-light leading-tight text-[#F4EFE6]">
          See what's coming. <span className="text-[var(--color-sky)]">Any place on Earth.</span>
        </p>
      </LiveEarthHero>
      <div>
        <Eyebrow>Agriculture · data foundation</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">One golden source in. A defensible number out.</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Two things go in — live satellite data for the hazards agriculture cares about, and your sourcing book —
          and one auditable score per plot comes out. This page is that chain, scoped to agriculture.
        </p>
      </div>

      {/* seasonal-arrears overlay — harvest carry-over vs genuine deterioration (renders once arrears are uploaded) */}
      <SeasonalArrears />

      <div className="grid md:grid-cols-2 gap-4">
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-2"><Radar size={16} className="text-[var(--color-blue)]" />
            <div className="text-[13px] font-semibold">The climate side — ours to maintain</div></div>
          <p className="text-[12.5px] text-[var(--color-mute)]">Agriculture yield is driven by <span className="text-[var(--color-ink)]">drought + heat</span>. Direct feeds from Europe’s &amp; America’s satellites &amp; agencies — Copernicus/ERA5 (temperature, rainfall, soil moisture) and Hansen forest-loss for EUDR.</p>
          <div className="flex flex-wrap gap-2 mt-3">
            {['ERA5', 'ERA5-Land soil moisture', 'Hansen GFC'].map(s => <Chip key={s}>{s}</Chip>)}
          </div>
        </Card>
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-2"><Upload size={16} className="text-[var(--color-good)]" />
            <div className="text-[13px] font-semibold">Your side — the sourcing plots</div></div>
          <p className="text-[12.5px] text-[var(--color-mute)]">The parcels you source from — crop, hectares, and geolocation (a polygon above 4 ha for EUDR) — the book the climate data gets projected onto. One spreadsheet; nothing else to maintain.</p>
          <div className="flex flex-wrap gap-2 mt-3"><Chip tone="good">Sourcing plots</Chip></div>
        </Card>
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4"><Boxes size={16} className="text-[var(--color-sky)]" />
          <div className="text-[13px] font-semibold">From raw pixels to one score</div></div>
        <div className="grid md:grid-cols-3 gap-4">
          {STEPS.map((s, i) => (
            <div key={i} className="rounded-xl border border-[var(--color-line)] p-4">
              <div className="mono text-[10px] text-[var(--color-blue)] mb-1">{`0${i + 1}`}</div>
              <div className="text-[14px] font-semibold">{s.k}</div>
              <div className="text-[12px] text-[var(--color-mute)] mt-1">{s.d}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-5 flex flex-wrap items-center justify-between gap-4"
        style={{ background: 'linear-gradient(180deg,#0e2338,var(--color-panel))', borderColor: 'var(--color-blued)' }}>
        <div>
          <div className="mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-sky)]">Live golden source for agriculture</div>
          <div className="display text-3xl font-semibold mt-1">{q.isLoading ? '…' : agriScores.toLocaleString()} <span className="text-base text-[var(--color-mute)] font-normal">current scores</span></div>
        </div>
        <div className="text-right">
          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">hazards scored on real data</div>
          <div className="text-[15px]">{liveHazards.join(' · ') || (q.isLoading ? 'loading…' : '—')}</div>
        </div>
      </Card>

      <div className="grid sm:grid-cols-4 gap-4">
        <Stat big="51.4M" label="satellite observations" />
        <Stat big="1998–2026" label="28 years of history" />
        <Stat big="H3 res-8" label="~0.7 km² cells" />
        <Stat big="append-only" label="immutable golden source" />
      </div>
      <p className="mono text-[11px] text-[var(--color-faint)]">The shared foundation underneath — one golden source, the same for every sector.</p>

      <div className="grid sm:grid-cols-3 gap-4">
        <Why icon={RefreshCw} t="Near-real-time" b="New observations flow straight to scores; you see risk rising before it lands." />
        <Why icon={Lock} t="Append-only" b="Scores are immutable — a new score retires the old with a timestamp; both stand." />
        <Why icon={ShieldCheck} t="Audit-grade" b="Every score records its model version, data vintage and input fingerprint." />
      </div>
    </div>
  )
}

function Chip({ children, tone }: { children: React.ReactNode; tone?: 'good' }) {
  return <span className={`mono text-[11px] px-3 py-1 rounded-lg border ${tone === 'good' ? 'text-[var(--color-good)] border-[color-mix(in_oklab,var(--color-good)_40%,var(--color-line))]' : 'text-[var(--color-mute)] border-[var(--color-line-2)]'}`}>{children}</span>
}
function Why({ icon: Icon, t, b }: { icon: typeof RefreshCw; t: string; b: string }) {
  return <Card className="p-4"><Icon size={18} className="text-[var(--color-sky)] mb-2" />
    <div className="text-[13px] font-semibold">{t}</div><div className="text-[12px] text-[var(--color-mute)] mt-1">{b}</div></Card>
}
