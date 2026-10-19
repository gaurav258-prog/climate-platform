import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ChevronRight, Coins, PackageX, Percent, Boxes, X } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, HeroBanner, SectionHead, StatGrid, type StatItem } from '../components/ui'
import { HBar } from '../components/Charts'
import { HEADING, InfoButton, MessageLine, messageDetails, type Details, type Message } from '../components/Details'
import { hazardLabel } from '../lib/hazards'
import { flow } from '../lib/money'
import { pressable } from '../lib/pressable'

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
  by_hazard: ConcHazard[]; flags: Message[]; method: Message
}
interface Summary {
  rollup: { ingredient_spend_eur: number; total_cogs_eur: number; volume_at_risk_eur: number; pct_cogs_at_risk: number }
  commodities: Commodity[]
  commodity_ids: Record<string, string>
  concentration?: Concentration
}

const TIER: Record<string, { label: string; cls: string }> = {
  backtested: { label: 'Backtested', cls: 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_13%,transparent)]' },
  ranged: { label: 'Ranged · band', cls: 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_13%,transparent)]' },
}

export default function Cogs() {
  const nav = useNavigate()
  const [sp] = useSearchParams()
  // deep-link from Coverage ("see it on your book →") arrives pre-filtered to that hazard
  const [hazardFilter, setHazardFilter] = useState<string | null>(sp.get('hazard'))
  const rowsRef = useRef<HTMLDivElement>(null)
  const q = useQuery({ queryKey: ['summary'], queryFn: () => api.get<Summary>('/v1/supply/summary') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>We couldn't load this data. Please retry, or contact support if it persists.</Center>
  const d = q.data
  const sorted = [...d.commodities].sort((a, b) => (b.volume_at_risk_eur ?? 0) - (a.volume_at_risk_eur ?? 0))
  const rows = hazardFilter ? sorted.filter(c => c.top_hazard === hazardFilter) : sorted

  return (
    <div className="fadeup space-y-7">
      <PageHeader eyebrow="Agriculture · the volume that won't arrive" title="COGS-at-risk"
        lead="The share of your sourcing volume that climate hazard puts at risk."
        about={[
          { heading: HEADING.shows, body: 'Climate hazard on every sourcing plot, rolled into the share of your volume that fails to arrive, priced at what you already pay for it.' },
          { heading: HEADING.read, body: 'A euro figure is published for a crop only where its calibration reproduces real crop failures from the hazard. Elsewhere the exposure is mapped and the euro figure is withheld; each withheld crop says why.' },
        ]} />

      <HeroBanner
        eyebrow="COGS-at-risk"
        title={(d.rollup.volume_at_risk_eur ?? 0) > 0 ? "Some of your volume won't arrive." : 'Your volume is clearing.'}
        lead="Hazard on every sourcing plot, priced at what you pay."
        stat={[
          { label: 'ingredient spend', value: flow(d.rollup.ingredient_spend_eur), icon: Coins },
          { label: 'volume at risk (physical)', value: flow(d.rollup.volume_at_risk_eur), icon: PackageX, tone: '#E8853C' },
          { label: 'of COGS', value: `${(d.rollup.pct_cogs_at_risk ?? 0).toFixed(2)}%`, icon: Percent },
          { label: 'commodities', value: d.commodities.length, icon: Boxes, tone: 'var(--color-sky)' },
        ]} />

      <SupplyConcentrationCard c={d.concentration} commodityIds={d.commodity_ids}
        onHazard={(hazard) => { setHazardFilter(prev => prev === hazard ? null : hazard); setTimeout(() => rowsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60) }} />

      <div ref={rowsRef} className="scroll-mt-4" />
      {hazardFilter && (
        <div className="flex items-center gap-2 text-[12px] text-[var(--color-mute)]">
          showing {rows.length} commodit{rows.length === 1 ? 'y' : 'ies'} exposed to <span className="font-medium text-[var(--color-ink)]">{hazardLabel(hazardFilter)}</span>
          <button onClick={() => setHazardFilter(null)} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">clear <X size={12} /></button>
        </div>
      )}
      <div className="space-y-3">
        {rows.map(c => {
          const tier = c.calibration ? TIER[c.calibration] : undefined
          const published = c.calibration === 'backtested' || c.calibration === 'ranged'
          const cid = d.commodity_ids?.[c.commodity]
          const why = rowDetails(c, published)
          return (
            <Card key={c.commodity} className={`p-4 ${cid ? 'cursor-pointer hover:border-[var(--color-sky)] transition' : ''}`}
              style={cid ? undefined : undefined}>
              <div {...pressable(cid && (() => nav(`/detail/commodity/${cid}`)))}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-[15px] font-semibold">{c.commodity}</span>
                {cid && <ChevronRight size={15} className="text-[var(--color-faint)] order-last ml-1" />}
                {c.eudr_covered && <span className="text-[10.5px] font-medium px-2 py-0.5 rounded-full text-[var(--color-blue)] bg-[color-mix(in_oklab,var(--color-blue)_13%,transparent)]">EUDR</span>}
                {tier && <span className={`text-[10.5px] font-medium px-2 py-0.5 rounded-full ${tier.cls}`}>{tier.label}</span>}
                {c.confidence_grade && <span className="text-[10.5px] px-2 py-0.5 rounded-full text-[var(--color-mute)] border border-[var(--color-line-2)]">Grade {c.confidence_grade}</span>}
                <div className="ml-auto text-right">
                  {published
                    ? <div className="display text-lg font-semibold text-[var(--color-warn)]">
                        {c.calibration === 'ranged' ? `${flow(c.volume_at_risk_low_eur)}–${flow(c.volume_at_risk_high_eur)}` : flow(c.volume_at_risk_eur)}
                      </div>
                    : <div className="text-[12.5px] text-[var(--color-faint)]">€ withheld</div>}
                  <div className="text-[10px] text-[var(--color-faint)]">{published ? 'volume at risk' : 'exposure mapped'}</div>
                </div>
              </div>
              <div className="text-[12px] text-[var(--color-mute)] mt-2 tabular-nums">
                Spend {flow(c.annual_spend_eur)} · {c.n_plots} plots · {c.top_hazard ? hazardLabel(c.top_hazard) : 'No hazard scored'}{c.avg_hazard != null ? ` ${c.avg_hazard}` : ''}
                {c.yield_shock_pct != null && published ? ` · ${c.yield_shock_pct}% of yield at risk` : ''}
              </div>
              </div>
              {/* outside the row's link: the explanation opens its own pop-up */}
              {why && <InfoButton details={why} label={published ? 'About this figure' : 'Why withheld'} className="mt-1.5" />}
            </Card>
          )
        })}
      </div>
    </div>
  )
}
// Why a crop's figure reads as it does — the server's own explanation, one click away (UI standard): why the euro
// figure is withheld, what the crop's figure measures, and how well its calibration fits.
function rowDetails(c: Commodity, published: boolean): Details | null {
  const sections = [
    ...(!published && c.held_reason ? [{ heading: 'Why the euro figure is withheld', body: c.held_reason }] : []),
    ...(c.measured_basis ? [{ heading: 'What the figure measures', body: c.measured_basis }] : []),
    ...(published && c.fit_r2 != null ? [{ heading: 'Calibration fit', body: `Out-of-sample r² ${c.fit_r2.toFixed(2)}: the share of this crop's yield swings the calibration explains in years it was not fitted on.` }] : []),
  ]
  return sections.length ? { title: c.commodity, sections } : null
}

function SupplyConcentrationCard({ c, commodityIds, onHazard }: { c?: Concentration; commodityIds?: Record<string, string>; onHazard?: (hazard: string) => void }) {
  const nav = useNavigate()
  if (!c || !c.available) return null
  const cs = c.common_shock
  return (
    <Card className="px-4 py-3.5">
      <div className="flex items-center gap-2 mb-3">
        <SectionHead hint="one crop or one hazard?">Supply-shock concentration</SectionHead>
        <InfoButton compact details={messageDetails(c.method)} />
      </div>
      <StatGrid cols={4} items={[
        { label: 'Effective independent crops', value: c.effective_commodities ?? '—' },
        { label: 'Effective independent hazards', value: c.effective_hazards ?? '—' },
        { label: `Top crop${c.top_commodity ? ` · ${c.top_commodity.commodity}` : ''}`, value: c.top_commodity ? `${c.top_commodity.pct_of_spend}%` : '—', accent: c.top_commodity && c.top_commodity.pct_of_spend > 25 ? '#E8B24C' : undefined },
        { label: 'Spend in top common shock', value: `${c.common_shock_pct_of_spend}%`, accent: '#E9744A' },
      ] satisfies StatItem[]} />
      {cs && (
        <div className="mt-3 rounded-lg border border-[var(--color-line-2)] px-3.5 py-2.5">
          <div className="text-[11.5px] font-medium text-[var(--color-faint)] mb-1">Largest common shock</div>
          <div className="text-[13px] text-[var(--color-ink)]">
            <span className="font-medium">{hazardLabel(cs.hazard)}</span> across <span className="font-medium">{cs.n_commodities} crops</span> — {flow(cs.spend_eur)} spend exposed{cs.at_risk_eur ? <> · <span style={{ color: '#E9744A' }}>{flow(cs.at_risk_eur)} published at-risk</span></> : null}
          </div>
        </div>
      )}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
        {c.by_commodity.length > 0 && (
          <div>
            <div className="text-[11.5px] font-medium text-[var(--color-faint)] mb-2">Spend by commodity</div>
            <HBar data={c.by_commodity.slice(0, 6).map(m => ({ label: m.commodity, value: m.spend_eur, sub: `${m.pct_of_spend}%`, color: m.pct_of_spend > 25 ? '#E8B24C' : 'var(--color-sky)' }))} format={flow} height={18}
              onBar={(i) => { const cid = commodityIds?.[c.by_commodity[i].commodity]; if (cid) nav(`/detail/commodity/${cid}`) }} />
          </div>
        )}
        {c.by_hazard.length > 0 && (
          <div>
            <div className="text-[11.5px] font-medium text-[var(--color-faint)] mb-2">Spend by main hazard</div>
            <HBar data={c.by_hazard.slice(0, 6).map((h, i) => ({ label: hazardLabel(h.hazard), value: h.spend_eur, sub: `${h.n_commodities} crop${h.n_commodities === 1 ? '' : 's'}`, color: i === 0 ? '#E9744A' : 'var(--color-sky)' }))} format={flow} height={18}
              onBar={onHazard ? (i) => onHazard!(c.by_hazard[i].hazard) : undefined} />
          </div>
        )}
      </div>
      {c.flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px]" style={{ color: '#E8B24C' }}>
          {c.flags.map(f => <MessageLine key={f.code} m={f} />)}
        </div>
      )}
    </Card>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
