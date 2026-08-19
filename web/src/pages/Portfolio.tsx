import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Download, Upload, FileSpreadsheet, ArrowRight } from 'lucide-react'
import { api, download, upload, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card, SectionHead } from '../components/ui'
import AssetDrawer from '../components/AssetDrawer'
import HorizonSelect, { DEFAULT_HORIZON } from '../components/HorizonSelect'
import ExpectedLossCard from '../components/ExpectedLossCard'
import ReportedHistoryRef from '../components/ReportedHistoryRef'
import { hazardLabel, sevColor, sevLabel } from '../lib/hazards'

// The financial-sector operating surface behind the Horizon globe. One page, sector-adaptive: the org's
// type (bank / insurer / asset_manager / reit) chooses which real book endpoint to read and how to label
// its rollup — every number is the projected book from the golden source, nothing invented. Agriculture
// keeps its own workspace (Sourcing/Cogs/…); this is the equivalent operating book for the four financials.

interface Hazard { hazard: string; score: number; bucket: string; model_version?: string; scored_at?: string; ci_lo?: number | null; ci_hi?: number | null }
interface FwdPoint { horizon: string; at_risk_eur: number; at_risk_pct: number; at_risk_band_eur: [number, number]; newly_crossing_eur: number; newly_crossing_count: number }
interface FwdMover { entity_name: string; current_score: number; future_score: number; delta: number; value_eur: number }
interface ForwardRisk { scenario: string; book_eur: number; entities: number; trajectory: FwdPoint[]; movers: FwdMover[]; runway: string | null; basis: string }
interface Valuation {
  discounted_value_eur: number; is_overridden: boolean
  recommended_discount_pct?: number; effective_discount_pct?: number
  original_ltv_pct?: number; climate_adjusted_ltv_pct?: number
  vulnerability_factor?: number
  vulnerability?: { applied: boolean; complete: boolean; drivers: { attr: string; value: unknown; factor: number }[]; missing: string[] }
}
interface Asset {
  region?: string; lat?: number; lon?: number
  headline_score: number | null; headline_bucket: string | null; headline_hazard: string | null
  hazards: Hazard[]; valuation?: Valuation
  [k: string]: unknown   // id/name/type/value + rollup live under sector-specific keys
}
type Rollup = Record<string, number | unknown>
type PortfolioResp = { scenario: string; horizon: string; rollup: Rollup } & Record<string, unknown>
interface LossBand { expected_value_loss_eur: number; loss_low_eur: number; loss_high_eur: number; band_pct: number | null; ci_coverage_pct: number }
interface Cat { available: boolean; mean_annual_loss_eur: number; sum_independent_eal_eur: number; mean_reconciles: boolean; pml_eur: number; pml_return_period: number; tail_to_mean_multiple: number | null; n_zones: number; aep_eur: Record<string, number>; oep_eur: Record<string, number> }
interface Transition { available: boolean; financed_emissions_tco2e: number; emissions_reported_pct: number; n_emissions_estimated: number; transition_expected_loss_eur: number; transition_el_pct_of_outstanding: number; exposure_weighted_transition_score: number | null; by_sector: { nace_section: string; transition_el_eur: number; outstanding_eur: number; n: number }[] }
interface CombinedVar { available: boolean; median_loss_eur: number; var95_eur: number; var99_eur: number; physical_expected_eur: number; transition_expected_eur: number; combined_expected_eur: number; combined_pct_of_book: number; n_positions: number; n_with_transition: number }
interface Resilience { available: boolean; n_properties: number; total_resilience_capex_eur: number; total_avoided_loss_eur: number; portfolio_benefit_cost_ratio: number | null; n_worth_retrofit: number; taxonomy_adaptation_aligned_capex_eur: number; by_hazard: { hazard: string; resilience_capex_eur: number; avoided_loss_eur: number; n: number }[] }

type Kpi = { label: string; field?: string; num?: string; den?: string; fmt: 'eur' | 'pct' | 'frac'; tone?: string; hint?: string }
// plain-English → the precise technical term (shown on hover) so a pro's model-risk team still sees it
const SCENARIO_HINT: Record<string, string> = {
  baseline: "Today's climate, held steady", orderly_1_5c: 'A 1.5°C-warmer world (fast, orderly action)',
  disorderly_2c: 'A 2°C-warmer world (late, disorderly action)', hot_house_3_5c: 'A 3.5°C-warmer world (little action)',
}
interface Cfg {
  prefix: string; listKey: string; noun: string
  idKey: string; nameKey: string; typeKey: string; valueKey: string
  uploadNoun: string   // what a CSV row is, for the import affordance ("loan tape", "SoV", …)
  itemKey: string      // singular resource for the detail/override path: /v1/{prefix}/{itemKey}/{id}
  valuationKey?: string  // where the valuation block sits in the detail payload (varies by sector)
  auditKey: string     // where the audit trail sits in the detail payload
  overrideMode: 'valuation' | 'trigger'   // insurer configures a parametric trigger, the rest override a discount
  kpis: Kpi[]
}
// upload/template paths follow one shape: /v1/{prefix}/{listKey}/{upload|template.xlsx}
const uploadPath = (c: Cfg) => `/v1/${c.prefix}/${c.listKey}/upload`
const templatePath = (c: Cfg) => `/v1/${c.prefix}/${c.listKey}/template.xlsx`
// The ONLY thing that differs between the four financial books — list key, per-item value key, rollup labels.
const SECTORS: Record<string, Cfg> = {
  bank: {
    prefix: 'bank', listKey: 'assets', noun: 'financed assets', uploadNoun: 'loan tape',
    idKey: 'asset_id', nameKey: 'asset_name', typeKey: 'asset_type', valueKey: 'value_eur',
    itemKey: 'asset', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation',
    kpis: [
      { label: 'Total book value', field: 'total_value_eur', fmt: 'eur' },
      { label: 'Money at high risk', field: 'value_at_risk_eur', fmt: 'eur', tone: '#E9744A', hint: 'Value at Risk (High+): value of assets in the top two severity bands' },
      { label: 'Share of book at high risk', field: 'pct_value_at_risk', fmt: 'pct', hint: '% of book value at high risk' },
      { label: 'Assets analysed', num: 'n_scored', den: 'n_assets', fmt: 'frac' },
    ],
  },
  insurer: {
    prefix: 'insurance', listKey: 'policies', noun: 'insured locations', uploadNoun: 'Statement of Values',
    idKey: 'policy_id', nameKey: 'policy_name', typeKey: 'policy_type', valueKey: 'sum_insured_eur',
    itemKey: 'policy', auditKey: 'audit', overrideMode: 'trigger',
    kpis: [
      { label: 'Total sum insured', field: 'total_sum_insured_eur', fmt: 'eur' },
      { label: 'Likely yearly loss', field: 'total_expected_annual_loss_eur', fmt: 'eur', tone: '#E9744A', hint: 'Expected annual loss' },
      { label: 'Claims vs premiums', field: 'portfolio_loss_ratio_pct', fmt: 'pct', hint: 'Loss ratio' },
      { label: 'Locations priced', num: 'n_priced', den: 'n_policies', fmt: 'frac' },
    ],
  },
  asset_manager: {
    prefix: 'assetmgmt', listKey: 'holdings', noun: 'holdings', uploadNoun: 'holdings book',
    idKey: 'holding_id', nameKey: 'holding_name', typeKey: 'sector', valueKey: 'position_value_eur',
    itemKey: 'holding', valuationKey: 'climate_var', auditKey: 'valuation_audit', overrideMode: 'valuation',
    kpis: [
      { label: 'Portfolio value', field: 'total_portfolio_value_eur', fmt: 'eur' },
      { label: 'Money at climate risk', field: 'total_climate_var_eur', fmt: 'eur', tone: '#E9744A', hint: 'Climate Value at Risk (Climate VaR)' },
      { label: 'Share at climate risk', field: 'portfolio_climate_var_pct', fmt: 'pct', hint: 'Climate VaR %' },
      { label: 'Holdings analysed', num: 'n_scored', den: 'n_holdings', fmt: 'frac' },
    ],
  },
  reit: {
    prefix: 'realestate', listKey: 'properties', noun: 'properties', uploadNoun: 'property schedule',
    idKey: 'property_id', nameKey: 'property_name', typeKey: 'property_type', valueKey: 'property_value_eur',
    itemKey: 'property', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation',
    kpis: [
      { label: 'Portfolio value', field: 'total_value_eur', fmt: 'eur' },
      { label: 'Yearly rental income', field: 'total_annual_noi_eur', fmt: 'eur' },
      { label: 'Hit to rental income', field: 'portfolio_noi_impact_pct', fmt: 'pct', tone: '#E8B24C', hint: 'Net operating income (NOI) impact' },
      { label: 'Properties analysed', num: 'n_scored', den: 'n_properties', fmt: 'frac' },
    ],
  },
}

const SCENARIOS: [string, string][] = [['baseline', 'Today'], ['disorderly_2c', 'Disorderly 2°C']]

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
function col(l: number): [number, number, number] { return l < 28 ? [95, 185, 140] : l < 50 ? [232, 178, 76] : l < 75 ? [233, 116, 74] : [210, 59, 59] }
const BUCKET: Record<string, string> = { VH: 'severe', H: 'high', M: 'elevated', L: 'low' }

function kpiValue(k: Kpi, r: Rollup | undefined): string {
  if (!r) return '—'
  if (k.fmt === 'frac') return `${(r[k.num!] as number) ?? 0}/${(r[k.den!] as number) ?? 0}`
  const v = r[k.field!] as number | undefined
  if (v == null) return '—'
  return k.fmt === 'pct' ? `${v}%` : eur(v)
}

export default function Portfolio() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const type = profile?.org?.type ?? ''
  const cfg = SECTORS[type]
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState<string>(DEFAULT_HORIZON)
  const [open, setOpen] = useState<string | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  // two jobs, cleanly separated: work the book (find/open assets) vs. read the forward analysis.
  // Analytics deep-links straight to the forward view via ?view=forward, so the two feel like one flow.
  const [sp] = useSearchParams()
  const [view, setView] = useState<'book' | 'forward'>(sp.get('view') === 'forward' ? 'forward' : 'book')
  // the book is search-driven — not a full dump. filter by text (name/region/sector), hazard, and severity.
  const [search, setSearch] = useState('')
  const [hazardF, setHazardF] = useState('')
  const [bandF, setBandF] = useState('')
  const bookRef = useRef<HTMLDivElement>(null)
  const refreshBook = () => {
    qc.invalidateQueries({ queryKey: ['fin-portfolio'] }); qc.invalidateQueries({ queryKey: ['fin-forward'] })
    qc.invalidateQueries({ queryKey: ['fin-detail'] })
  }

  const q = useQuery({
    queryKey: ['fin-portfolio', cfg?.prefix, scenario, horizon],
    queryFn: () => api.get<PortfolioResp>(`/v1/${cfg!.prefix}/portfolio?scenario=${scenario}&horizon=${horizon}`),
    enabled: !!cfg,
  })
  // forward-change decision signal — always a forward pathway (baseline has no projection to decide on)
  const fwdScenario = scenario === 'baseline' ? 'disorderly_2c' : scenario
  const fq = useQuery({
    queryKey: ['fin-forward', cfg?.prefix, fwdScenario],
    queryFn: () => api.get<ForwardRisk>(`/v1/${cfg!.prefix}/forward-risk?scenario=${fwdScenario}`),
    enabled: !!cfg,
  })

  if (!cfg) return (
    <div className="fadeup"><Eyebrow>Portfolio</Eyebrow>
      <Card className="p-10 mt-4 text-[13px] text-[var(--color-mute)]">This workspace has no financial book — the Portfolio view is for bank, insurer, asset-manager and REIT tenants.</Card>
    </div>
  )

  const r = q.data?.rollup
  const items = (q.data?.[cfg.listKey] as Asset[] | undefined) ?? []
  const sorted = [...items].sort((a, b) => (b.headline_score ?? -1) - (a.headline_score ?? -1))

  // search-driven book: filter by free text (name / region / sector-or-type), headline hazard, and severity
  const bandOf = (sc: number | null | undefined) => sc == null ? '' : sc < 28 ? 'low' : sc < 50 ? 'elevated' : sc < 75 ? 'high' : 'severe'
  const hazardOpts = [...new Set(sorted.map(a => a.headline_hazard).filter(Boolean))] as string[]
  const term = search.trim().toLowerCase()
  const searching = !!(term || hazardF || bandF)
  const filtered = sorted.filter(a => {
    if (term) {
      const hay = `${a[cfg.nameKey] ?? ''} ${a.region ?? ''} ${a[cfg.typeKey] ?? ''} ${a.headline_hazard ?? ''}`.toLowerCase()
      if (!hay.includes(term)) return false
    }
    if (hazardF && a.headline_hazard !== hazardF) return false
    if (bandF && bandOf(a.headline_score) !== bandF) return false
    return true
  })
  // default (nothing searched): show only the most-exposed few — never the whole list
  const shown = searching ? filtered : sorted.slice(0, 6)
  const clearSearch = () => { setSearch(''); setHazardF(''); setBandF('') }

  return (
    <div className="fadeup space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>{profile?.org?.name} · {cfg.noun}</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">Portfolio</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">Your {cfg.noun}, checked against our verified climate data — the biggest physical threat to each one, and how it changes with warming. Every figure is real; “—” means we haven’t scored that one yet.</p>
        </div>
        <div className="flex flex-col gap-2 items-end">
          <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)]">
            {SCENARIOS.map(([k, lbl]) => (
              <button key={k} title={SCENARIO_HINT[k]} onClick={() => setScenario(k)} className={`px-3 py-1.5 rounded-md text-[12px] transition ${scenario === k ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{lbl}</button>
            ))}
          </div>
          {view === 'book' && (
            <div className="flex items-center gap-1 p-1 rounded-lg border border-[var(--color-line-2)]">
              <HorizonSelect value={horizon} onChange={setHorizon} />
            </div>
          )}
        </div>
      </div>

      {/* view switch — separate the two jobs so the page isn't a long scroll of both at once:
          "Your book" = the searchable asset list you operate; "Forward view" = the trajectory + €-loss analysis. */}
      <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)] w-fit">
        {([['book', 'Your book'], ['forward', 'Forward view']] as const).map(([k, lbl]) => (
          <button key={k} onClick={() => setView(k)}
            className={`px-4 py-1.5 rounded-md text-[12.5px] transition ${view === k ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)] font-medium' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{lbl}</button>
        ))}
      </div>

      {/* rollup KPIs — sector-labelled; the headline, shown on both views */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {cfg.kpis.map(k => <Kpi key={k.label} label={k.label} value={kpiValue(k, r)} tone={k.tone} hint={k.hint} />)}
      </div>

      {/* modelled uncertainty — the expected value loss as a RANGE, from the per-cell score confidence
          interval propagated through the same haircut (bank & REIT; nothing invented). */}
      <ValueLossBand band={r?.expected_value_loss_band as LossBand | undefined} />

      {/* catastrophe accumulation — the correlated tail (AEP/OEP/PML) the summed EALs hide (insurer). */}
      <CatAccumulation cat={r?.catastrophe as Cat | undefined} />

      {/* transition risk — financed emissions + a carbon-price expected-loss beside the physical one (bank). */}
      <TransitionCard t={(q.data as PortfolioResp | undefined)?.transition as Transition | undefined} scenarioLabel={(SCENARIOS.find(([k]) => k === scenario)?.[1]) ?? scenario} />

      {/* combined physical + transition climate VaR — one loss distribution over both drivers (asset mgmt). */}
      <CombinedVarCard c={r?.combined_climate_var as CombinedVar | undefined} scenarioLabel={(SCENARIOS.find(([k]) => k === scenario)?.[1]) ?? scenario} />

      {/* resilience & adaptation capex — spend vs avoided loss + Taxonomy-aligned capex (REIT). */}
      <ResilienceCard rc={r?.resilience_capex as Resilience | undefined} />

      {view === 'forward' ? (
        <div className="space-y-6">
          {/* ties the forward view back to what you actually filed (renders only if prior filings exist) */}
          <ReportedHistoryRef />
          {/* forward-change decision signal */}
          {fq.data && <ForwardRiskCard d={fq.data} scenarioLabel={(SCENARIOS.find(([k]) => k === fwdScenario)?.[1]) ?? fwdScenario} />}
          {/* climate expected loss (€) — near-term decision quantity, bank only */}
          {cfg.prefix === 'bank' && <ExpectedLossCard prefix={cfg.prefix} scenario={fwdScenario} scenarioLabel={(SCENARIOS.find(([k]) => k === fwdScenario)?.[1]) ?? fwdScenario} />}
          {/* one flow: the deeper version of this forward story lives in Analytics (bank/AM/REIT only) */}
          {(type === 'bank' || type === 'asset_manager' || type === 'reit') && (
            <Link to="/analytics" className="inline-flex items-center gap-1.5 text-[13px] text-[var(--color-sky)] hover:underline">
              See the full forward analytics — pathways, drivers &amp; lineage <ArrowRight size={14} />
            </Link>
          )}
        </div>
      ) : (
      <div className="space-y-6">
      {/* where the risk comes from — plain-language money-by-hazard, traffic-light by severity.
          Clicking a hazard filters the book below to exactly those sites (the impulsive path). */}
      <HazardExposure items={items} valueKey={cfg.valueKey} active={hazardF}
        onPick={(h) => { setSearch(''); setBandF(''); setHazardF(prev => prev === h ? '' : h); setTimeout(() => bookRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60) }} />

      {/* the book */}
      <div ref={bookRef} className="scroll-mt-4" />
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]">
          <SectionHead>Your {cfg.noun}</SectionHead>
          <div className="flex items-center gap-4">
            <ImportBook cfg={cfg} onDone={refreshBook} />
            <button
               className="inline-flex items-center gap-1.5 mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"
               onClick={() => download(`/v1/${cfg.prefix}/portfolio.xlsx?scenario=${scenario}&horizon=${horizon}`, `${cfg.prefix}-portfolio.xlsx`).catch(() => toast.error('Could not download the export.'))}>
              <Download size={13} /> Export .xlsx
            </button>
          </div>
        </div>
        {q.isLoading ? <div className="p-10 text-center text-[var(--color-faint)] text-sm">loading the book…</div>
          : sorted.length === 0 ? <EmptyBook cfg={cfg} onDone={refreshBook} />
          : (
          <>
            {/* search + filters — the book is found, not dumped */}
            <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center gap-2">
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder={`Search your ${cfg.noun} — name, region, sector…`}
                className="flex-1 min-w-[200px] bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
              <select value={hazardF} onChange={e => setHazardF(e.target.value)} title="Filter by biggest hazard"
                className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[12.5px] text-[var(--color-mute)] outline-none focus:border-[var(--color-sky)]">
                <option value="">All hazards</option>
                {hazardOpts.map(h => <option key={h} value={h}>{hazardLabel(h)}</option>)}
              </select>
              <select value={bandF} onChange={e => setBandF(e.target.value)} title="Filter by severity"
                className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[12.5px] text-[var(--color-mute)] outline-none focus:border-[var(--color-sky)]">
                <option value="">All severity</option>
                <option value="severe">Severe</option>
                <option value="high">High</option>
                <option value="elevated">Elevated</option>
                <option value="low">Low</option>
              </select>
              {searching && <button onClick={clearSearch} className="mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-sky)] px-1">clear</button>}
            </div>
            <div className="px-5 py-2 mono text-[10.5px] text-[var(--color-faint)] border-b border-[var(--color-line)]">
              {searching ? `${filtered.length} match${filtered.length === 1 ? '' : 'es'} · of ${sorted.length} ${cfg.noun}`
                         : `Most exposed · showing ${shown.length} of ${sorted.length} — search or filter above to open any`}
            </div>
            {shown.length === 0
              ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">No {cfg.noun} match — adjust your search or filters.</div>
              : (
          <div className="divide-y divide-[var(--color-line)]">
            {shown.map((a) => {
              const id = String(a[cfg.idKey] ?? '')
              const name = String(a[cfg.nameKey] ?? '—')
              const atype = a[cfg.typeKey] ? String(a[cfg.typeKey]) : null
              const value = a[cfg.valueKey] as number | null
              const sc = a.headline_score
              const [rr, gg, bb] = col(sc ?? 0)
              const bk = a.headline_bucket ? BUCKET[a.headline_bucket] : null
              const isOpen = open === id
              return (
                <div key={id}>
                  <button onClick={() => setOpen(isOpen ? null : id)} className="w-full text-left px-5 py-3 flex items-center gap-4 hover:bg-[var(--color-bg-2)] transition">
                    <ChevronRight size={15} className={`shrink-0 text-[var(--color-faint)] transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[14px] text-[var(--color-ink)] truncate">{name}</div>
                      <div className="mono text-[11px] text-[var(--color-faint)] truncate">{[a.region, atype?.replace(/_/g, ' ')].filter(Boolean).join(' · ') || '—'}</div>
                    </div>
                    <div className="mono text-[13px] text-[var(--color-mute)] tabular-nums shrink-0 w-24 text-right">{eur(value)}</div>
                    <div className="shrink-0 w-36 flex justify-end">
                      {sc == null ? <span className="mono text-[12px] text-[var(--color-faint)]">—</span>
                        : <span className="inline-flex items-center gap-1.5 mono text-[12px] whitespace-nowrap" style={{ color: `rgb(${rr},${gg},${bb})` }}>
                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: `rgb(${rr},${gg},${bb})` }} />
                            {Math.round(sc)}/100{bk ? ` · ${bk}` : ''}
                          </span>}
                    </div>
                  </button>
                  {isOpen && (
                    <div className="px-5 pb-4 pt-1 bg-[var(--color-bg-2)]">
                      <div className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-2">Biggest threat: {a.headline_hazard ? hazardLabel(a.headline_hazard) : '—'} · {scenario} · {horizon}</div>
                      <div className="grid sm:grid-cols-2 gap-x-8 gap-y-1.5">
                        {(a.hazards ?? []).length === 0 && <div className="text-[12.5px] text-[var(--color-faint)]">No hazard scores under this scenario/horizon yet.</div>}
                        {(a.hazards ?? []).map(h => { const [hr, hg, hb] = col(h.score); return (
                          <div key={h.hazard} className="flex items-center justify-between gap-3 text-[12.5px] border-b border-[var(--color-line)] py-1">
                            <span className="min-w-0">
                              <span className="text-[var(--color-mute)]">{hazardLabel(h.hazard)}</span>
                              {h.model_version && <span className="mono text-[10px] text-[var(--color-faint)] ml-2">{h.model_version}{h.scored_at ? ` · ${h.scored_at.slice(0, 10)}` : ''}</span>}
                            </span>
                            <span className="mono tabular-nums shrink-0 text-right" style={{ color: `rgb(${hr},${hg},${hb})` }}>
                              {Math.round(h.score)}/100 · {BUCKET[h.bucket] ?? h.bucket}
                              {h.ci_lo != null && h.ci_hi != null && Math.round(h.ci_lo) !== Math.round(h.ci_hi) && <span className="block text-[9.5px] text-[var(--color-faint)] leading-tight" title="Across-model / sea-level 68% band (projection uncertainty)">band {Math.round(h.ci_lo)}–{Math.round(h.ci_hi)}</span>}
                            </span>
                          </div>) })}
                      </div>
                      {a.valuation && (<>
                        <div className="mono text-[11.5px] text-[var(--color-faint)] mt-3 leading-relaxed">
                          risk-adjusted value <b className="text-[var(--color-mute)]">{eur(a.valuation.discounted_value_eur)}</b>
                          {a.valuation.effective_discount_pct != null ? ` · ${a.valuation.effective_discount_pct}% climate discount` : ''}
                          {a.valuation.is_overridden ? ' · analyst override on file' : ''}
                          {a.valuation.original_ltv_pct != null && a.valuation.climate_adjusted_ltv_pct != null
                            ? ` · LTV ${a.valuation.original_ltv_pct}% → ${a.valuation.climate_adjusted_ltv_pct}%` : ''}
                          {a.lat != null && a.lon != null ? ` · ${Math.abs(a.lat).toFixed(1)}°${a.lat >= 0 ? 'N' : 'S'}, ${Math.abs(a.lon).toFixed(1)}°${a.lon >= 0 ? 'E' : 'W'}` : ''}
                        </div>
                        {a.valuation.vulnerability?.applied && a.valuation.vulnerability_factor != null && (
                          <div className="mono text-[11px] text-[var(--color-faint)] mt-1 leading-relaxed">
                            vulnerability <b className="text-[var(--color-mute)]">×{a.valuation.vulnerability_factor}</b>
                            {' — '}{a.valuation.vulnerability.drivers.map(d => `${d.attr.replace(/_/g, ' ')} ${d.value}`).join(' · ')}
                            <span className="text-[var(--color-faint)]"> · from asset attributes, not fitted to loss history</span>
                          </div>
                        )}
                      </>)}
                      <button onClick={() => setDetailId(id)} className="mt-3 inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline">
                        Full detail{cfg.overrideMode === 'valuation' ? ' & valuation override' : ' & set trigger'} →
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
              )}
          </>
        )}
      </Card>
      {q.isError && <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the book — reload, or sign in again.</div>}
      </div>
      )}

      {detailId && <AssetDrawer cfg={cfg} id={detailId} onClose={() => setDetailId(null)} onChanged={refreshBook} />}
    </div>
  )
}

function Kpi({ label, value, tone, hint }: { label: string; value: string; tone?: string; hint?: string }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="display text-[26px] leading-none" style={tone ? { color: tone } : undefined}>{value}</div>
      <div className="mono text-[10.5px] tracking-[0.14em] uppercase text-[var(--color-faint)] mt-2" title={hint}>
        {label}{hint && <span className="text-[var(--color-faint)] normal-case tracking-normal"> ⓘ</span>}
      </div>
    </Card>
  )
}

function ValueLossBand({ band }: { band?: LossBand }) {
  if (!band || !band.expected_value_loss_eur) return null
  const halfPct = band.band_pct != null ? (band.band_pct / 2).toFixed(1) : null
  return (
    <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">Expected value loss</span>
      <span className="text-[14px] font-semibold text-[var(--color-ink)] tabular-nums">{eur(band.expected_value_loss_eur)}</span>
      <span className="text-[12.5px] text-[var(--color-mute)]">
        modelled range <span className="tabular-nums text-[var(--color-ink)]">{eur(band.loss_low_eur)} – {eur(band.loss_high_eur)}</span>{halfPct && <> (±{halfPct}%)</>}
      </span>
      <span className="mono text-[10px] text-[var(--color-faint)] ml-auto" title="Share of at-risk value whose per-cell physical score carries a modelled confidence interval">
        {band.ci_coverage_pct}% of at-risk value has a confidence interval
      </span>
    </div>
  )
}

function CatAccumulation({ cat }: { cat?: Cat }) {
  if (!cat || !cat.available) return null
  const rp = (m: Record<string, number>, k: string) => eur(m[k])
  return (
    <Card className="px-4 py-3.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-3">
        <span className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">Catastrophe accumulation</span>
        <span className="text-[12px] text-[var(--color-mute)]">the correlated tail your summed expected losses hide</span>
        <span className="mono text-[10px] text-[var(--color-faint)] ml-auto">{cat.n_zones} peril·region zones</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <div className="display text-[22px] leading-none tabular-nums" style={{ color: '#E9744A' }}>{eur(cat.pml_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">PML · 1-in-{cat.pml_return_period} single event</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-ink)]">{rp(cat.aep_eur, 'rp_100')}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">1-in-100 year (aggregate)</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-ink)]">{rp(cat.aep_eur, 'rp_250')}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">1-in-250 year (aggregate)</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-mute)]">{eur(cat.mean_annual_loss_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">mean annual loss{cat.tail_to_mean_multiple ? ` · tail ${cat.tail_to_mean_multiple}×` : ''}</div>
        </div>
      </div>
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-3">
        Common-shock Monte-Carlo over peril·region zones — a single event hits every policy in its footprint. Mean {cat.mean_reconciles ? 'reconciles to' : 'vs'} the summed expected annual loss ({eur(cat.sum_independent_eal_eur)}); the tail is the accumulation. Correlation assumed, not a fitted vendor cat model.
      </div>
    </Card>
  )
}

const NACE_SECTION_LABEL: Record<string, string> = {
  '05': 'Coal mining', '06': 'Oil & gas extraction', '19': 'Refining', '35': 'Power & gas utilities',
  '24': 'Basic metals (steel)', '23': 'Cement & minerals', '29': 'Motor vehicles', '49': 'Land transport',
  '51': 'Air transport', '62': 'IT services',
}

function TransitionCard({ t, scenarioLabel }: { t?: Transition; scenarioLabel: string }) {
  if (!t || !t.available) return null
  const tco2e = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}Mt` : n >= 1e3 ? `${(n / 1e3).toFixed(0)}kt` : `${Math.round(n)}t`
  return (
    <Card className="px-4 py-3.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-3">
        <span className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">Transition risk · loan book</span>
        <span className="text-[12px] text-[var(--color-mute)]">the low-carbon shift on your counterparties ({scenarioLabel})</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <div className="display text-[22px] leading-none tabular-nums" style={{ color: '#8E6FC7' }}>{eur(t.transition_expected_loss_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Transition expected loss · {t.transition_el_pct_of_outstanding}%</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-ink)]">{tco2e(t.financed_emissions_tco2e)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Financed emissions (Scope 1+2)</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-ink)]">{t.exposure_weighted_transition_score ?? '—'}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Weighted transition score</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-mute)]">{t.emissions_reported_pct}%</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Emissions reported{t.n_emissions_estimated ? ` · ${t.n_emissions_estimated} estimated` : ''}</div>
        </div>
      </div>
      {t.by_sector?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {t.by_sector.slice(0, 4).map(s => (
            <span key={s.nace_section} className="mono text-[10.5px] px-2 py-1 rounded-lg border border-[var(--color-line-2)] text-[var(--color-mute)]">
              {NACE_SECTION_LABEL[s.nace_section] || `NACE ${s.nace_section}`} · {eur(s.transition_el_eur)}
            </span>
          ))}
        </div>
      )}
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-3">
        Transition EL = outstanding × modelled stranded-asset fraction (NGFS carbon price + sector tiers). Financed emissions are counterparty Scope 1+2, reported or NACE-estimated; a rigorous PCAF attribution additionally needs counterparty EVIC (you provide). Disclosed relative tiers, not a fitted PD model.
      </div>
    </Card>
  )
}

function CombinedVarCard({ c, scenarioLabel }: { c?: CombinedVar; scenarioLabel: string }) {
  if (!c || !c.available) return null
  return (
    <Card className="px-4 py-3.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-3">
        <span className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">Combined climate VaR</span>
        <span className="text-[12px] text-[var(--color-mute)]">physical + transition in one loss distribution ({scenarioLabel})</span>
        <span className="mono text-[10px] text-[var(--color-faint)] ml-auto">{c.n_with_transition}/{c.n_positions} positions carry a transition tier</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <div className="display text-[22px] leading-none tabular-nums" style={{ color: '#E9744A' }}>{eur(c.combined_expected_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Combined expected · {c.combined_pct_of_book}%</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-blue)]">{eur(c.physical_expected_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">— of which physical</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums" style={{ color: '#8E6FC7' }}>{eur(c.transition_expected_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">— of which transition</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-ink)]">{eur(c.var99_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">99th-percentile VaR</div>
        </div>
      </div>
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-3">
        One Monte-Carlo per holding over both drivers — physical (continuous haircut, sampled around the per-cell confidence interval) and transition (sector stranded-asset fraction under the scenario's NGFS carbon price). Combined as 1−(1−physical)(1−transition), so a holding is never lost twice. Disclosed relative tiers, not a fitted model.
      </div>
    </Card>
  )
}

const HAZARD_LABEL: Record<string, string> = {
  flood: 'Flooding', coastal_flood: 'Coastal flood', storm: 'Storms', wildfire: 'Wildfire', seismic: 'Earthquake',
  heat_chronic: 'Heat', drought: 'Drought', soil_water: 'Soil-water', pollution: 'Pollution',
}

function ResilienceCard({ rc }: { rc?: Resilience }) {
  if (!rc || !rc.available) return null
  return (
    <Card className="px-4 py-3.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-3">
        <span className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">Resilience &amp; adaptation capex</span>
        <span className="text-[12px] text-[var(--color-mute)]">what to spend, what loss it avoids</span>
        <span className="mono text-[10px] text-[var(--color-faint)] ml-auto">{rc.n_worth_retrofit}/{rc.n_properties} properties worth retrofitting</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-ink)]">{eur(rc.total_resilience_capex_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Resilience capex</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums" style={{ color: 'var(--color-good)' }}>{eur(rc.total_avoided_loss_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Loss avoided</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums" style={{ color: rc.portfolio_benefit_cost_ratio && rc.portfolio_benefit_cost_ratio >= 1 ? 'var(--color-good)' : 'var(--color-ink)' }}>{rc.portfolio_benefit_cost_ratio ?? '—'}×</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Benefit-cost ratio</div>
        </div>
        <div>
          <div className="display text-[22px] leading-none tabular-nums text-[var(--color-ink)]">{eur(rc.taxonomy_adaptation_aligned_capex_eur)}</div>
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Taxonomy adaptation capex</div>
        </div>
      </div>
      {rc.by_hazard?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {rc.by_hazard.slice(0, 4).map(h => (
            <span key={h.hazard} className="mono text-[10.5px] px-2 py-1 rounded-lg border border-[var(--color-line-2)] text-[var(--color-mute)]">
              {HAZARD_LABEL[h.hazard] || h.hazard} · spend {eur(h.resilience_capex_eur)} → avoid {eur(h.avoided_loss_eur)}
            </span>
          ))}
        </div>
      )}
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-3">
        Avoided loss = modelled physical loss × a disclosed per-hazard adaptation effectiveness (EU Climate-ADAPT / IPCC AR6 WGII ranges); capex = a disclosed reference fraction of value by severity. Disclosed relative tiers, not a per-property quote. The retrofit is EU-Taxonomy climate-adaptation-aligned capex (Objective 2).
      </div>
    </Card>
  )
}

// Book import — a CSV of the book lands in the org, gets an H3 cell per row and is scored against the
// golden source (same core as an any-address lookup). Shared by the header control and the empty-state CTA.
// Pull the most useful message out of an error body. This API wraps HTTPException detail as
// {"error": <detail>}, so a missing-columns 400 arrives as {error:{error:"missing_columns", missing:[…]}}.
function uploadErrorText(e: unknown): string {
  if (e instanceof ApiError) {
    const b = e.body as Record<string, unknown> | string | undefined
    if (typeof b === 'string') return b
    const inner = (b && typeof b === 'object' && 'error' in b ? (b as { error: unknown }).error : b) as Record<string, unknown> | undefined
    const miss = (inner?.missing ?? (b as { missing?: unknown })?.missing) as string[] | undefined
    if (Array.isArray(miss)) return `Missing required columns: ${miss.join(', ')}`
    const msg = (inner?.message ?? (b as { message?: unknown })?.message) as string | undefined
    if (typeof msg === 'string') return msg
  }
  return 'Import failed — check the CSV columns against the template.'
}

function useBookUpload(cfg: Cfg, onDone: () => void) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'err' } | null>(null)
  const send = async (file: File) => {
    setBusy(true); setMsg(null)
    try {
      const r = await upload<{ n_uploaded: number; n_skipped: number }>(uploadPath(cfg), file)
      setMsg({ text: `Imported ${r.n_uploaded} row${r.n_uploaded === 1 ? '' : 's'}${r.n_skipped ? ` · ${r.n_skipped} skipped` : ''} — scored against the golden source.`, tone: 'ok' })
      onDone()
    } catch (e) {
      setMsg({ text: uploadErrorText(e), tone: 'err' })
    } finally { setBusy(false) }
  }
  return { busy, msg, send }
}

function TemplateButton({ cfg, big }: { cfg: Cfg; big?: boolean }) {
  const onClick = () => download(templatePath(cfg), `tellumen-${cfg.prefix}-template.xlsx`).catch(() => toast.error('Could not download the template.'))
  return big
    ? <button onClick={onClick} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-4 py-2 text-[13px] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><FileSpreadsheet size={14} /> Download template</button>
    : <button onClick={onClick} className="inline-flex items-center gap-1.5 mono text-[11px] text-[var(--color-faint)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={13} /> template</button>
}

function FilePickButton({ busy, onPick, big }: { busy: boolean; onPick: (f: File) => void; big?: boolean }) {
  const cls = big
    ? `inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-medium cursor-pointer transition ${busy ? 'bg-[var(--color-panel)] text-[var(--color-faint)]' : 'bg-[var(--color-sky)] text-[#08111f] hover:bg-[var(--color-blue)]'}`
    : `inline-flex items-center gap-1.5 mono text-[11px] cursor-pointer ${busy ? 'text-[var(--color-faint)]' : 'text-[var(--color-mute)] hover:text-[var(--color-sky)]'}`
  return (
    <label className={cls}>
      <Upload size={big ? 14 : 13} /> {busy ? 'uploading…' : 'Import CSV'}
      <input type="file" accept=".csv" className="hidden" disabled={busy}
        onChange={e => { const f = e.target.files?.[0]; if (f) onPick(f); e.target.value = '' }} />
    </label>
  )
}

// Header import control — now surfaces the result (success/error) inline, not just in the empty state.
function ImportBook({ cfg, onDone }: { cfg: Cfg; onDone: () => void }) {
  const { busy, msg, send } = useBookUpload(cfg, onDone)
  return (
    <div className="flex items-center gap-4">
      {msg && <span className={`mono text-[10.5px] max-w-xs truncate ${msg.tone === 'ok' ? 'text-[var(--color-good)]' : 'text-[var(--color-bad)]'}`} title={msg.text}>{msg.text}</span>}
      <TemplateButton cfg={cfg} />
      <FilePickButton busy={busy} onPick={send} />
    </div>
  )
}

function EmptyBook({ cfg, onDone }: { cfg: Cfg; onDone: () => void }) {
  const { busy, msg, send } = useBookUpload(cfg, onDone)
  return (
    <div className="p-10 text-center">
      <FileSpreadsheet size={26} className="mx-auto mb-3 text-[var(--color-faint)]" />
      <div className="text-[14px] text-[var(--color-ink)] mb-1">No {cfg.noun} yet — import your {cfg.uploadNoun}</div>
      <p className="text-[12.5px] text-[var(--color-mute)] max-w-md mx-auto mb-4">Upload a CSV and every row is placed on the H3 grid and scored against the golden source — the same engine an any-address lookup uses. Start from the template so the columns line up.</p>
      <div className="flex items-center justify-center gap-3">
        <FilePickButton busy={busy} onPick={send} big />
        <TemplateButton cfg={cfg} big />
      </div>
      {msg && <div className={`mono text-[11px] mt-4 ${msg.tone === 'ok' ? 'text-[var(--color-good)]' : 'text-[var(--color-bad)]'}`}>{msg.text}</div>}
    </div>
  )
}

function HazardExposure({ items, valueKey, onPick, active }: { items: Asset[]; valueKey: string; onPick?: (hazard: string) => void; active?: string }) {
  const m: Record<string, { eur: number; n: number; worst: number }> = {}
  for (const a of items) {
    const hz = a.headline_hazard, sc = a.headline_score
    if (!hz || sc == null) continue
    const g = (m[hz] ??= { eur: 0, n: 0, worst: 0 })
    g.eur += ((a as unknown as Record<string, number>)[valueKey]) ?? 0
    g.n += 1; g.worst = Math.max(g.worst, sc)
  }
  const groups = Object.entries(m).sort((a, b) => b[1].worst - a[1].worst || b[1].eur - a[1].eur)
  if (!groups.length) return null
  return (
    <Card className="p-5">
      <SectionHead className="mb-3" hint={<>money exposed by hazard{onPick && <span className="normal-case tracking-normal"> · click a hazard to see the sites</span>}</>}>Where your risk comes from</SectionHead>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {groups.map(([hz, g]) => {
          const isActive = active === hz
          return (
            <button key={hz} onClick={() => onPick?.(hz)} disabled={!onPick}
              className={`rounded-lg border px-3.5 py-3 text-left transition ${onPick ? 'cursor-pointer hover:shadow-sm' : 'cursor-default'}`}
              style={{ borderColor: isActive ? sevColor(g.worst) : sevColor(g.worst) + '55', borderWidth: isActive ? 2 : 1, background: isActive ? sevColor(g.worst) + '12' : undefined }}>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: sevColor(g.worst) }} />
                <span className="text-[13px] text-[var(--color-ink)] leading-tight">{hazardLabel(hz)}</span>
              </div>
              <div className="display text-[21px] leading-none">{eur(g.eur)}</div>
              <div className="text-[11px] text-[var(--color-mute)] mt-1"><b style={{ color: sevColor(g.worst) }}>{sevLabel(g.worst)}</b> · {g.n} asset{g.n > 1 ? 's' : ''} exposed{onPick && <span className="text-[var(--color-sky)]"> → {isActive ? 'showing below' : 'view sites'}</span>}</div>
            </button>
          )
        })}
      </div>
      <div className="text-[10px] text-[var(--color-faint)] mt-3 leading-relaxed">Money = value of the assets whose biggest physical threat is this hazard. Colour shows how severe: <span style={{ color: '#34d399' }}>green</span> moderate · <span style={{ color: '#f0a860' }}>amber</span> high · <span style={{ color: '#fb7185' }}>red</span> severe.</div>
    </Card>
  )
}

function ForwardRiskCard({ d, scenarioLabel }: { d: ForwardRisk; scenarioLabel: string }) {
  const traj = d.trajectory
  const now = traj.find(t => t.horizon === 'current')
  const end = traj[traj.length - 1]
  const worst = traj.filter(t => t.horizon !== 'current').reduce((a, b) => (b.newly_crossing_eur > (a?.newly_crossing_eur ?? -1) ? b : a), traj[1])
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-3">
        <SectionHead hint={<>decision signal · {scenarioLabel}</>}>Forward risk</SectionHead>
        <div className="mono text-[10px] text-[var(--color-faint)]">biggest threat crossing into high risk</div>
      </div>
      {/* headline */}
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[15px] mb-4">
        <span className="display text-[22px]" style={{ color: 'var(--color-warm, #f0a860)' }}>{now?.at_risk_pct ?? 0}%</span>
        <span className="text-[var(--color-mute)]">of your book is at risk today</span>
        {end && <><span className="text-[var(--color-faint)]">→</span>
          <span className="display text-[22px]" style={{ color: 'var(--color-bad, #fb7185)' }}>{end.at_risk_pct}%</span>
          <span className="text-[var(--color-mute)]">by {end.horizon}</span></>}
        {d.runway
          ? <span className="ml-1 text-[12.5px] px-2 py-0.5 rounded-md border border-[var(--color-line-2)] text-[var(--color-ink)]">material new exposure by <b>{d.runway}</b></span>
          : <span className="ml-1 text-[12.5px] text-[var(--color-faint)]">· no material new crossing on the horizon</span>}
      </div>
      {/* trajectory */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {traj.map(t => (
          <div key={t.horizon} className="rounded-lg border border-[var(--color-line)] px-3 py-2.5">
            <div className="mono text-[10px] text-[var(--color-faint)] uppercase">{t.horizon === 'current' ? 'Now' : t.horizon}</div>
            <div className="mono text-[15px] mt-0.5">{eur(t.at_risk_eur)}</div>
            <div className="text-[11px] text-[var(--color-mute)]">{t.at_risk_pct}% at risk</div>
            {t.horizon !== 'current' && t.at_risk_band_eur[0] !== t.at_risk_band_eur[1] &&
              <div className="mono text-[9.5px] text-[var(--color-faint)] mt-0.5" title="CMIP6/AR6 model-disagreement band">band {eur(t.at_risk_band_eur[0])}–{eur(t.at_risk_band_eur[1])}</div>}
            {t.newly_crossing_eur > 0 && <div className="text-[10px] text-[var(--color-warm,#f0a860)] mt-0.5">+{eur(t.newly_crossing_eur)} new ({t.newly_crossing_count})</div>}
          </div>
        ))}
      </div>
      {/* movers — the assets to act on */}
      {d.movers.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <div className="mono text-[10px] tracking-[0.14em] uppercase text-[var(--color-faint)]">Movers · act on these first ({worst?.horizon ?? end?.horizon})</div>
            {/* Sense → Decide: the movers are the projection's act-by list Decisions consumes */}
            <Link to="/decisions" className="inline-flex items-center gap-1 mono text-[10px] uppercase tracking-wide text-[var(--color-sky)] hover:underline shrink-0">
              Act on these in Decisions <ArrowRight size={12} />
            </Link>
          </div>
          <div className="space-y-1">
            {d.movers.map((m, i) => (
              <div key={i} className="flex items-center justify-between text-[12.5px] border-b border-[var(--color-line)] py-1">
                <span className="text-[var(--color-ink)] truncate">{m.entity_name}</span>
                <span className="mono tabular-nums shrink-0 text-[var(--color-mute)]">{Math.round(m.current_score)} → <b className="text-[var(--color-bad,#fb7185)]">{Math.round(m.future_score)}</b> · {eur(m.value_eur)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="text-[10px] text-[var(--color-faint)] mt-3 leading-relaxed">{d.basis} Feeds TCFD / IFRS S2 / ECB forward scenario analysis.</div>
    </Card>
  )
}
