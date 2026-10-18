import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Coins, Percent, PieChart } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { scenarioLabel } from '../lib/labels'
import { Card, HeroBanner, PageHeader } from '../components/ui'
import { HEADING } from '../components/Details'
import MethodGap from '../components/MethodGap'
import RealizedExposure from '../components/RealizedExposure'
import AssetDrawer from '../components/AssetDrawer'
import HorizonSelect, { DEFAULT_HORIZON } from '../components/HorizonSelect'
import ExpectedLossCard from '../components/ExpectedLossCard'
import ReportedHistoryRef from '../components/ReportedHistoryRef'
import { FORWARD_DEFAULT, SCENARIOS, SECTORS, kpiValue } from './portfolio/sectors'
import ForwardRiskCard, { type ForwardRisk } from './portfolio/ForwardRisk'
import { BookPanel, HazardExposure, type Asset } from './portfolio/Book'
import { CollateralStrandingCard, EnergyStrandingCard, ResilienceCard, TransitionCard, ValueLossBand,
  type CollateralStranding, type EnergyStranding, type LossBand, type Resilience, type Transition } from './portfolio/BookCards'
import { CatAccumulation, InsurerInvestmentsCard, InsurerReinsuranceCard, type Cat } from './portfolio/InsurerCards'
import { CombinedVarCard, ConcentrationCard, type CombinedVar, type Concentration } from './portfolio/HoldingsCards'

// The financial sector's book (bank, insurer, asset manager, REIT), to the UI standard (2026-10-16): figures and charts
// on the main screen; every explanation one click away — the page's in "About this page", each card's in its own
// "How it's calculated", in the words of the server that computed the figure. Every number is the book's own.

type Rollup = Record<string, unknown>
type PortfolioResp = { scenario: string; horizon: string; rollup: Rollup; transition?: Transition; collateral_stranding?: CollateralStranding; concentration?: Concentration } & Record<string, unknown>

const ABOUT = [
  { heading: HEADING.shows, body: 'Your book scored against our climate data: the biggest physical threat to each asset, the money at risk, and how both change as the world warms. The cards under the headline figures depend on your sector.' },
  { heading: HEADING.read, body: 'Today is the climate as it is. Disorderly 2 °C is a world about 2 °C warmer after late, abrupt policy action; choose the year with the year selector. Your book lists each asset and its scores; Forward view shows how the risk changes up to 2100.' },
  { heading: HEADING.sources, body: 'Hazard scores from our climate models, read at each asset’s location. Money figures use the method your organisation states for the year, under Methodology.' },
  { heading: HEADING.limits, body: 'A dash (—) means the asset is not scored yet, or a figure’s method is not stated. Nothing is estimated in its place.' },
]

export default function Portfolio() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const type = profile?.org?.type ?? ''
  const cfg = SECTORS[type]
  const [sp] = useSearchParams()
  const [scenario, setScenario] = useState<string>('baseline')
  // a hazard deep-link (Coverage: "see it on your book") is about today's score, so it opens on that year
  const [horizon, setHorizon] = useState<string>(sp.get('horizon') ?? DEFAULT_HORIZON)
  const [view, setView] = useState<'book' | 'forward'>(sp.get('view') === 'forward' ? 'forward' : 'book')
  const [filters, setFilters] = useState({ search: '', hazard: sp.get('hazard') ?? '', band: '' })
  const [open, setOpen] = useState<string | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const bookRef = useRef<HTMLDivElement>(null)
  const refresh = () => ['fin-portfolio', 'fin-forward', 'fin-detail'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))

  const q = useQuery({
    queryKey: ['fin-portfolio', cfg?.prefix, scenario, horizon], enabled: !!cfg,
    queryFn: () => api.get<PortfolioResp>(`/v1/${cfg!.prefix}/portfolio?scenario=${scenario}&horizon=${horizon}`),
  })
  // the forward view always reads a pathway: today has no projection to decide on
  const fwd = scenario === 'baseline' ? FORWARD_DEFAULT : scenario
  const fq = useQuery({
    queryKey: ['fin-forward', cfg?.prefix, fwd], enabled: !!cfg && view === 'forward',
    queryFn: () => api.get<ForwardRisk>(`/v1/${cfg!.prefix}/forward-risk?scenario=${fwd}`),
  })

  if (!cfg) return (
    <div className="fadeup space-y-4">
      <PageHeader eyebrow="Portfolio" title="Portfolio" />
      <Card className="p-8 text-[13px] text-[var(--color-mute)]">This view is for banks, insurers, asset managers and property companies.</Card>
    </div>
  )

  const r = q.data?.rollup
  const items = (q.data?.[cfg.listKey] as Asset[] | undefined) ?? []
  const pathway = scenarioLabel(scenario === 'baseline' ? fwd : scenario)
  // a drill from a card: open the book, filtered to what was clicked
  const drill = (f: Partial<typeof filters>) => {
    setView('book'); setFilters({ search: '', hazard: '', band: '', ...f })
    setTimeout(() => bookRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
  }
  const tab = (on: boolean) => `px-3 py-1.5 rounded-md text-[12.5px] transition ${on ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)] font-medium' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow={`${profile?.org?.name} · ${cfg.noun}`} title="Portfolio" about={ABOUT}
        lead="Your book’s climate risk today and as the world warms."
        actions={
          <div className="flex flex-wrap items-center gap-2 justify-end">
            <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)]" role="group" aria-label="Climate">
              {SCENARIOS.map(k => <button key={k} onClick={() => setScenario(k)} aria-pressed={scenario === k} className={tab(scenario === k)}>{k === 'baseline' ? 'Today' : scenarioLabel(k)}</button>)}
            </div>
            {view === 'book' && <div className="flex items-center gap-1 p-1 rounded-lg border border-[var(--color-line-2)]"><HorizonSelect value={horizon} onChange={setHorizon} /></div>}
          </div>
        } />

      <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)] w-fit" role="group" aria-label="View">
        {([['book', 'Your book'], ['forward', 'Forward view']] as const).map(([k, l]) => <button key={k} onClick={() => setView(k)} aria-pressed={view === k} className={tab(view === k)}>{l}</button>)}
      </div>

      <HeroBanner title="Your book against a warming world."
        stat={cfg.kpis.map(k => ({ label: k.label, value: kpiValue(k, r), tone: k.tone, icon: k.fmt === 'eur' ? Coins : k.fmt === 'pct' ? Percent : PieChart }))} />

      {/* a money figure whose method the organisation has not stated for the year is named, never estimated */}
      <MethodGap gap={r?.gap as string | undefined} what="Some figures" />
      <RealizedExposure />
      <ValueLossBand band={r?.expected_value_loss_band as LossBand | undefined} />
      <CatAccumulation cat={r?.catastrophe as Cat | undefined} />
      {type === 'insurer' && <InsurerInvestmentsCard scenario={fwd} horizon={horizon} />}
      {type === 'insurer' && <InsurerReinsuranceCard scenario={scenario} horizon={horizon} />}
      <TransitionCard t={q.data?.transition} pathway={scenario === 'baseline' ? 'Today' : pathway} />
      <CollateralStrandingCard cs={q.data?.collateral_stranding} />
      <CombinedVarCard c={r?.combined_climate_var as CombinedVar | undefined} pathway={scenario === 'baseline' ? 'Today' : pathway} />
      <ConcentrationCard c={q.data?.concentration}
        onRegion={region => drill({ search: region })}
        onHazard={hazard => drill({ hazard })}
        onCluster={(hazard, region) => drill({ hazard, search: region })} />
      <ResilienceCard rc={r?.resilience_capex as Resilience | undefined} />
      <EnergyStrandingCard es={r?.energy_stranding as EnergyStranding | undefined} />

      {view === 'forward' ? (
        <div className="space-y-6">
          <ReportedHistoryRef />
          {fq.data && <ForwardRiskCard d={fq.data} />}
          {fq.isError && <div className="text-[12.5px] text-[var(--color-bad)]">The forward view could not be loaded. Try again shortly.</div>}
          {cfg.prefix === 'bank' && <ExpectedLossCard prefix={cfg.prefix} scenario={fwd} scenarioLabel={pathway} />}
          {(type === 'bank' || type === 'asset_manager' || type === 'reit') && (
            <Link to="/analytics" className="inline-flex items-center gap-1.5 text-[13px] text-[var(--color-sky)] hover:underline">
              See the full forward analysis <ArrowRight size={14} />
            </Link>
          )}
        </div>
      ) : (
        <div className="space-y-6">
          <HazardExposure items={items} valueKey={cfg.valueKey} active={filters.hazard}
            onPick={h => drill({ hazard: filters.hazard === h ? '' : h })} />
          <div ref={bookRef} className="scroll-mt-4" />
          <BookPanel cfg={cfg} items={items} loading={q.isLoading} failed={q.isError} scenario={scenario} horizon={horizon}
            filters={filters} setFilters={setFilters} open={open} setOpen={setOpen} onDetail={setDetailId} onImported={refresh} />
        </div>
      )}

      {detailId && <AssetDrawer cfg={cfg} id={detailId} onClose={() => setDetailId(null)} onChanged={refresh} />}
    </div>
  )
}
