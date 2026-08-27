import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Coins, PackageX, Percent, Boxes } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, HeroBanner, SectionHead, StatGrid, type StatItem } from '../components/ui'
import { HBar } from '../components/Charts'
import { hazardLabel } from '../lib/hazards'

interface Commodity {
  commodity: string; eudr_covered: boolean; annual_spend_eur: number; n_plots: number; status: string
  calibration: string | null; held_reason: string | null; avg_hazard: number | null; top_hazard: string | null
  yield_shock_pct: number | null; volume_at_risk_eur: number | null; volume_at_risk_low_eur: number | null
  volume_at_risk_high_eur: number | null; fit_r2: number | null; confidence_grade: string | null; measured_basis: string | null
}
interface ConcHazard { hazard: string; spend_eur: number; at_risk_eur: number | null; n_commodities: number; pct_of_spend: number }
interface Concentration {
  available: boolean; total_spend_eur: number; effective_commodities: number | null; effective_hazards: number | null
  top_commodity: { commodity: string; pct_of_spend: number } | null
  common_shock: ConcHazard | null; common_shock_pct_of_spend: number
  by_commodity: { commodity: string; spend_eur: number; pct_of_spend: number }[]
  by_hazard: ConcHazard[]; flags: string[]; method: string
}
interface Summary {
  rollup: { ingredient_spend_eur: number; total_cogs_eur: number; volume_at_risk_eur: number; pct_cogs_at_risk: number }
  commodities: Commodity[]
  commodity_ids: Record<string, string>
  concentration?: Concentration
}

const eur = (n?: number | null) => n == null ? '—' : `€${(n / 1e6).toFixed(1)}m`
const TIER: Record<string, { label: string; cls: string }> = {
  backtested: { label: 'Backtested', cls: 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_13%,transparent)]' },
  ranged: { label: 'Ranged · band', cls: 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_13%,transparent)]' },
}

export default function Cogs() {
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['summary'], queryFn: () => api.get<Summary>('/v1/supply/summary') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — is the API on :8001?</Center>
  const d = q.data
  const rows = [...d.commodities].sort((a, b) => (b.volume_at_risk_eur ?? 0) - (a.volume_at_risk_eur ?? 0))

  return (
    <div className="fadeup space-y-7">
      <PageHeader eyebrow="Agriculture · the volume that won't arrive" title="COGS-at-risk"
        lead="Climate hazard on every sourcing plot, rolled into the share of your volume that fails — priced at what you already pay. A euro publishes only when the hazard→yield chain reproduces a real crop failure; otherwise exposure is mapped and the € withheld." />

      <HeroBanner
        eyebrow="COGS-at-risk"
        title={(d.rollup.volume_at_risk_eur ?? 0) > 0 ? "Some of your volume won't arrive." : 'Your volume is clearing.'}
        lead="Climate hazard on every sourcing plot, rolled into the share of volume that fails — priced at what you already pay."
        stat={[
          { label: 'ingredient spend', value: eur(d.rollup.ingredient_spend_eur), icon: Coins },
          { label: 'volume at risk (physical)', value: eur(d.rollup.volume_at_risk_eur), icon: PackageX, tone: '#E8853C' },
          { label: 'of COGS', value: `${(d.rollup.pct_cogs_at_risk ?? 0).toFixed(2)}%`, icon: Percent },
          { label: 'commodities', value: d.commodities.length, icon: Boxes, tone: 'var(--color-sky)' },
        ]} />

      <SupplyConcentrationCard c={d.concentration} />

      <div className="space-y-3">
        {rows.map(c => {
          const tier = c.calibration ? TIER[c.calibration] : undefined
          const published = c.calibration === 'backtested' || c.calibration === 'ranged'
          const cid = d.commodity_ids?.[c.commodity]
          return (
            <Card key={c.commodity} className={`p-4 ${cid ? 'cursor-pointer hover:border-[var(--color-sky)] transition' : ''}`}
              style={cid ? undefined : undefined}>
              <div onClick={() => cid && nav(`/detail/commodity/${cid}`)}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-[15px] font-semibold">{c.commodity}</span>
                {cid && <ChevronRight size={15} className="text-[var(--color-faint)] order-last ml-1" />}
                {c.eudr_covered && <span className="mono text-[9px] px-2 py-0.5 rounded-full text-[var(--color-blue)] bg-[color-mix(in_oklab,var(--color-blue)_13%,transparent)]">EUDR</span>}
                {tier && <span className={`mono text-[9px] px-2 py-0.5 rounded-full ${tier.cls}`}>{tier.label}{c.fit_r2 != null ? ` · r² ${c.fit_r2.toFixed(2)}` : ''}</span>}
                {c.confidence_grade && <span className="mono text-[9px] px-2 py-0.5 rounded-full text-[var(--color-mute)] border border-[var(--color-line-2)]">Grade {c.confidence_grade}</span>}
                <div className="ml-auto text-right">
                  {published
                    ? <div className="display text-lg font-semibold text-[var(--color-warn)]">
                        {c.calibration === 'ranged' ? `${eur(c.volume_at_risk_low_eur)}–${eur(c.volume_at_risk_high_eur)}` : eur(c.volume_at_risk_eur)}
                      </div>
                    : <div className="mono text-[12px] text-[var(--color-faint)]">€ withheld</div>}
                  <div className="text-[10px] text-[var(--color-faint)]">{published ? 'volume at risk' : 'exposure mapped'}</div>
                </div>
              </div>
              <div className="text-[12px] text-[var(--color-mute)] mt-2">
                spend {eur(c.annual_spend_eur)} · {c.n_plots} plots · {c.top_hazard ?? 'hazard'} {c.avg_hazard ?? '—'}
                {c.yield_shock_pct != null && published ? ` · ${c.yield_shock_pct}% of yield at risk` : ''}
                {!published && c.held_reason ? <span className="text-[var(--color-faint)]"> · {c.held_reason}</span> : ''}
              </div>
              {c.measured_basis && <div className="text-[11px] text-[var(--color-faint)] mt-1">measures {c.measured_basis}</div>}
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
function SupplyConcentrationCard({ c }: { c?: Concentration }) {
  if (!c || !c.available) return null
  const cs = c.common_shock
  return (
    <Card className="px-4 py-3.5">
      <SectionHead className="mb-3" hint="is your sourcing risk concentrated in one crop or one hazard?">Supply-shock concentration</SectionHead>
      <StatGrid cols={4} items={[
        { label: 'Effective independent crops', value: c.effective_commodities ?? '—' },
        { label: 'Effective independent hazards', value: c.effective_hazards ?? '—' },
        { label: `Top crop${c.top_commodity ? ` · ${c.top_commodity.commodity}` : ''}`, value: c.top_commodity ? `${c.top_commodity.pct_of_spend}%` : '—', accent: c.top_commodity && c.top_commodity.pct_of_spend > 25 ? '#E8B24C' : undefined },
        { label: 'Spend in top common shock', value: `${c.common_shock_pct_of_spend}%`, accent: '#E9744A' },
      ] satisfies StatItem[]} />
      {cs && (
        <div className="mt-3 rounded-lg border border-[var(--color-line-2)] px-3.5 py-2.5">
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Largest common shock · one bad season hits these together</div>
          <div className="text-[13px] text-[var(--color-ink)]">
            <span className="font-medium">{hazardLabel(cs.hazard)}</span> across <span className="font-medium">{cs.n_commodities} crops</span> — {eur(cs.spend_eur)} spend exposed{cs.at_risk_eur ? <> · <span style={{ color: '#E9744A' }}>{eur(cs.at_risk_eur)} published at-risk</span></> : null}
          </div>
        </div>
      )}
      {c.by_hazard.length > 0 && (
        <div className="mt-4">
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-2">Sourcing spend exposed by hazard</div>
          <HBar data={c.by_hazard.slice(0, 6).map((h, i) => ({ label: hazardLabel(h.hazard), value: h.spend_eur, sub: `${h.n_commodities} crops`, color: i === 0 ? '#E9744A' : 'var(--color-sky)' }))} format={eur} height={18} />
        </div>
      )}
      {c.flags.length > 0 && <div className="mono text-[9.5px] mt-3" style={{ color: '#E8B24C' }}>{c.flags.join(' · ')}</div>}
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2">{c.method}</div>
    </Card>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
