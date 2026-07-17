import { useState, useEffect } from 'react'
import {
  Landmark, Umbrella, Sprout, Layers, TrendingUp, Building, Truck, Building2,
  ArrowRight, Satellite, Cpu, ShieldCheck, RefreshCw, GitBranch, Lock, Upload,
  Radar, FileWarning, Bell, ClipboardCheck, SlidersHorizontal,
} from 'lucide-react'
import { INDUSTRIES, PROCESSING_CHAIN } from '../data/industries'
import { fetchScoresSummary } from '../api/client'

const ICONS = {
  landmark: Landmark, umbrella: Umbrella, sprout: Sprout, layers: Layers,
  'trending-up': TrendingUp, building: Building, truck: Truck, 'building-community': Building2,
}

const STAGE_ICONS = [Satellite, Cpu, Cpu, GitBranch, ArrowRight]

// The built sectors' own {consumes, output} pairs already live in industries.js —
// this just adds the human-readable "what you get" line so the Outputs section
// doesn't duplicate a second, drifting copy of the same facts.
const OUTPUT_DETAIL = {
  banking: 'Recommended collateral discount %, climate-adjusted LTV, TCFD / EU Taxonomy disclosure pack, financed emissions.',
  insurance: 'Damage ratio, expected annual loss, technical premium, parametric trigger payout — one pricing chain.',
  agriculture: 'Volume-at-risk per commodity (physical, no price forecast), EUDR deforestation-free status, CSRD physical-risk pack.',
  'real-estate': 'Climate-adjusted valuation, NOI-impact %, expected insurance cost, EU Taxonomy eligibility.',
  'asset-management': 'Portfolio climate VaR (€ and % of AUM), High/Very-High screening flags, Taxonomy eligibility.',
}

export default function PlatformOverviewPage({ onSelectIndustry }) {
  const [summary, setSummary] = useState(null)
  useEffect(() => {
    let alive = true
    fetchScoresSummary().then(d => alive && setSummary(d)).catch(() => {})
    return () => { alive = false }
  }, [])

  const liveScores = summary?.total_current_scores
  const hazardsLive = summary?.hazards_live || []
  const builtIndustries = INDUSTRIES.filter(i => i.status === 'built')

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      {/* Header — plain, no video: this section is only about the data foundation */}
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-6xl mx-auto px-8 py-12">
          <p className="text-[11px] uppercase tracking-[0.25em] text-indigo-400 mb-3">Data foundation</p>
          <h1 className="text-4xl md:text-5xl font-light leading-tight text-gray-900">
            One golden source in.<br /><span className="text-indigo-600">A defensible number out.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-gray-600 leading-relaxed">
            Two things go in — live satellite/climate data, and your own portfolio — and one auditable score per
            location comes out, translated into whatever your sector actually prices against. This page is that
            whole chain, made visible.
          </p>
        </div>
      </header>

      {/* 1 · INPUTS — the two sides of what we ingest */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="01" title="What goes in" sub="Two inputs, not one" />
        <div className="grid md:grid-cols-2 gap-5 mt-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center"><Radar size={18} /></div>
              <p className="font-medium text-gray-900">The climate side — public, live, ours to maintain</p>
            </div>
            <p className="text-sm text-gray-600 leading-relaxed">
              Every feed lands in one place through a provider-abstraction layer, keyed to the H3 hexagonal grid —
              the platform never cares which satellite or agency produced a reading, only where and when. Sources
              include ERA5 reanalysis (temperature, precipitation, soil moisture, wind, runoff), GloFAS hydrology,
              NASA FIRMS fire detection, and EMSC/ESHM seismic catalogs.
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              {['ERA5', 'GloFAS', 'NASA FIRMS', 'Sentinel-1 SAR', 'Sentinel-3', 'EMSC', 'ESHM20'].map(s => (
                <span key={s} className="text-xs bg-gray-100 text-gray-700 rounded-full px-3 py-1">{s}</span>
              ))}
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-9 h-9 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center"><Upload size={18} /></div>
              <p className="font-medium text-gray-900">Your side — the portfolio the climate data gets projected onto</p>
            </div>
            <p className="text-sm text-gray-600 leading-relaxed">
              A location on its own is just a point on a map. What turns it into a number your business can act on
              is your own book — the loan tape, statement of values, sourcing plots, property schedule or holdings
              list you upload. We publish the exact template for each sector, and every optional field exists
              because it unlocks a specific, named calculation (an EPC rating enables a real EU Taxonomy check; a
              deductible enables real premium pricing) — never collected for its own sake.
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              {['Loan tape', 'Statement of Values', 'Sourcing plots', 'Property schedule', 'Holdings book'].map(s => (
                <span key={s} className="text-xs bg-gray-100 text-gray-700 rounded-full px-3 py-1">{s}</span>
              ))}
            </div>
          </div>
        </div>
        <div className="grid sm:grid-cols-4 gap-4 mt-5">
          <Stat big="51.4M" label="satellite observations" />
          <Stat big="1998–2026" label="28 years of history" />
          <Stat big="H3 res-8" label="~0.7 km² cells, EU" />
          <Stat big="append-only" label="immutable golden source" />
        </div>
      </section>

      {/* 2 · PROCESSING STORY */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="02" title="What happens in between" sub="From raw pixels to one 0–100 score" />
        <div className="grid md:grid-cols-5 gap-3 mt-6">
          {PROCESSING_CHAIN.map((s, i) => {
            const I = STAGE_ICONS[i] || Cpu
            return (
              <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 relative">
                <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center mb-2"><I size={18} /></div>
                <p className="text-sm font-medium text-gray-900">{s.stage}</p>
                <p className="text-xs text-gray-500 mt-0.5">{s.detail}</p>
                <p className="text-[10px] font-mono text-indigo-500 mt-2">{s.table}</p>
                {i < PROCESSING_CHAIN.length - 1 && (
                  <ArrowRight size={14} className="text-gray-300 absolute -right-2.5 top-1/2 hidden md:block" />
                )}
              </div>
            )
          })}
        </div>
        <div className="bg-indigo-600 rounded-xl p-6 mt-6 text-white flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-indigo-100 text-sm">Live golden source right now</p>
            <p className="text-3xl font-light">
              {liveScores != null ? liveScores.toLocaleString() : '…'} <span className="text-lg text-indigo-200">current scores</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-indigo-100 text-sm">Hazards scored on real data</p>
            <p className="text-xl">{hazardsLive.length ? hazardsLive.join(' · ') : 'starting…'}</p>
          </div>
        </div>
      </section>

      {/* 3 · OUTPUTS — one engine, a different number for every sector */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="03" title="What comes out" sub="One projected score, translated per sector" />
        <p className="mt-4 max-w-3xl text-sm text-gray-600 leading-relaxed">
          Every sector runs the identical fetch → project → headline pipeline (<code className="text-xs bg-gray-100 rounded px-1 py-0.5">services/portfolio_engine.py</code>) —
          only the last step, turning a 0–100 score into a business number, is sector-specific. That's why adding a
          sector means adding a calculation layer, not a new pipeline.
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mt-6">
          {builtIndustries.map(ind => {
            const Icon = ICONS[ind.icon] || Landmark
            return (
              <div key={ind.id} className="bg-white rounded-xl border border-gray-200 p-5">
                <div className="flex items-center gap-2.5 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center"><Icon size={16} strokeWidth={1.6} /></div>
                  <p className="font-medium text-gray-900">{ind.name}</p>
                </div>
                <p className="text-xs text-gray-500 mb-2">Consumes: <span className="text-gray-700">{ind.consumes}</span></p>
                <p className="text-sm text-gray-700 leading-snug">{OUTPUT_DETAIL[ind.id] || ind.output}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* 4 · WHY US */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="04" title="Why this foundation is defensible" sub="Always the latest, always auditable" />
        <div className="grid sm:grid-cols-2 gap-4 mt-6">
          <Why icon={RefreshCw} title="Near-real-time, never stale"
            body="New observations flow straight to scores. Each cell carries 6h/24h/48h velocity, so customers see risk rising before it lands — not in next quarter's report." />
          <Why icon={Lock} title="Append-only golden source"
            body="Scores are immutable. A new score retires the old one with a timestamp; nothing is overwritten. Today's number and last week's both stand, fully reproducible." />
          <Why icon={ShieldCheck} title="Audit-grade traceability"
            body="Every score records its model version, data vintage and a fingerprint of its inputs — the evidence regulators and reinsurers ask for." />
          <Why icon={GitBranch} title="One source, every sector"
            body="Banking, insurance, agriculture, real estate and asset management read the exact same canonical score. Add a sector and you add a layer, not a pipeline." />
          <Why icon={SlidersHorizontal} title="Recommended, never forced"
            body="Every modelled figure — a discount %, a premium, a VaR — is a recommendation a permitted human can override with a mandatory reason, fully audited. Never a black box." />
          <Why icon={FileWarning} title="Honest about the gaps"
            body="Where we don't yet have the data to answer a question (e.g. EU Taxonomy's 'aligned' test), we say so explicitly rather than approximate — a disclosed gap, never a guess dressed up as a number." />
        </div>
      </section>

      {/* 5 · REGULATORY CHANGE COMMITMENT */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="05" title="When a regulation changes" sub="Whose job it is to notice, and what happens next" />
        <div className="bg-white rounded-xl border border-gray-200 p-6 mt-6">
          <p className="text-gray-800 leading-relaxed">
            Disclosure rules don't stand still — TCFD, the EU Taxonomy, CSRD, EUDR and SFDR have all added new
            required data points since first written. When a framework starts asking for something we don't yet
            collect, that gap is <span className="font-medium">our responsibility to catch, not yours to
            discover during an audit.</span> We hold to a fixed sequence, every time:
          </p>
        </div>
        <div className="grid sm:grid-cols-4 gap-4 mt-5">
          <RegStep n="1" icon={Bell} title="We monitor the frameworks"
            body="TCFD, EU Taxonomy, CSRD, EUDR, SFDR and Solvency II are tracked on an ongoing basis — not reacted to after a client asks why a number is missing." />
          <RegStep n="2" icon={FileWarning} title="We name the exact new field"
            body="Not 'more data needed' — a specific, named field (e.g. an EPC rating, a counterparty compliance flag), and exactly which calculation it unlocks." />
          <RegStep n="3" icon={ClipboardCheck} title="We tell you in time"
            body="Customers hear about a new required field with real lead time before the next reporting deadline — enough to pull it from your own systems, not scramble the week it's due." />
          <RegStep n="4" icon={Upload} title="You supply it your way"
            body="The same upload template you already use gets one new optional column. Nothing else about your workflow changes." />
        </div>
        <div className="bg-gray-900 rounded-xl p-6 mt-5 text-white">
          <p className="text-sm text-gray-300 leading-relaxed">
            <span className="font-medium text-white">A real example, not a hypothetical:</span> the EU Taxonomy's
            "aligned" status needs proof of substantial contribution and minimum safeguards — data this platform
            didn't originally collect. Rather than approximate it, every asset honestly showed "eligible," never
            "aligned," with the gap disclosed. When we added the ability to supply it, it arrived as two optional
            upload columns (<code className="text-xs bg-white/10 rounded px-1 py-0.5">epc_rating</code>,{' '}
            <code className="text-xs bg-white/10 rounded px-1 py-0.5">minimum_safeguards_status</code>) on the exact
            templates already in use — no new workflow, no new integration, and the honest gap only closes once you
            choose to supply the data.
          </p>
        </div>
      </section>

      {/* 6 · SAME ENGINE, OTHER SECTORS */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="06" title="Same engine, every sector" sub="What else runs on this foundation" />
        <div className="flex flex-wrap gap-3 mt-6">
          {INDUSTRIES.map(ind => {
            const Icon = ICONS[ind.icon] || Landmark
            const built = ind.status === 'built'
            const Chip = built ? 'button' : 'div'
            return (
              <Chip key={ind.id} {...(built ? { onClick: () => onSelectIndustry(ind.id) } : {})}
                className={`flex items-center gap-2 rounded-full border px-4 py-2 text-left transition ${
                  built ? 'border-gray-200 bg-white hover:border-indigo-300 hover:shadow-sm' : 'border-gray-100 bg-gray-50 opacity-70'}`}>
                <Icon size={15} strokeWidth={1.6} className="text-indigo-600" />
                <span className="text-[13px] font-medium text-gray-900">{ind.name}</span>
                <span className={`text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded-full ${built ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-500'}`}>
                  {built ? 'Live' : 'Roadmap'}
                </span>
              </Chip>
            )
          })}
        </div>
      </section>
      <div className="h-12" />
    </div>
  )
}

const SectionLabel = ({ n, title, sub }) => (
  <div className="flex items-baseline gap-3">
    <span className="text-xs font-mono text-indigo-400">{n}</span>
    <h2 className="text-2xl font-light text-gray-900">{title}</h2>
    <span className="text-sm text-gray-400">— {sub}</span>
  </div>
)

const Stat = ({ big, label }) => (
  <div className="bg-white rounded-xl border border-gray-200 p-5">
    <p className="text-2xl font-semibold text-gray-900">{big}</p>
    <p className="text-xs text-gray-500 mt-1">{label}</p>
  </div>
)

const Why = ({ icon: Icon, title, body }) => (
  <div className="bg-white rounded-xl border border-gray-200 p-6">
    <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center mb-3"><Icon size={20} strokeWidth={1.5} /></div>
    <p className="font-medium text-gray-900">{title}</p>
    <p className="text-sm text-gray-600 mt-1 leading-relaxed">{body}</p>
  </div>
)

const RegStep = ({ n, icon: Icon, title, body }) => (
  <div className="bg-white rounded-xl border border-gray-200 p-5 relative">
    <span className="absolute top-4 right-4 text-xs font-mono text-gray-300">{n}</span>
    <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center mb-3"><Icon size={18} /></div>
    <p className="text-sm font-medium text-gray-900">{title}</p>
    <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{body}</p>
  </div>
)
