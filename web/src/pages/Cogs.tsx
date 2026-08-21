import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Coins, PackageX, Percent, Boxes } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, HeroBanner } from '../components/ui'

interface Commodity {
  commodity: string; eudr_covered: boolean; annual_spend_eur: number; n_plots: number; status: string
  calibration: string | null; held_reason: string | null; avg_hazard: number | null; top_hazard: string | null
  yield_shock_pct: number | null; volume_at_risk_eur: number | null; volume_at_risk_low_eur: number | null
  volume_at_risk_high_eur: number | null; fit_r2: number | null; confidence_grade: string | null; measured_basis: string | null
}
interface Summary {
  rollup: { ingredient_spend_eur: number; total_cogs_eur: number; volume_at_risk_eur: number; pct_cogs_at_risk: number }
  commodities: Commodity[]
  commodity_ids: Record<string, string>
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
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
