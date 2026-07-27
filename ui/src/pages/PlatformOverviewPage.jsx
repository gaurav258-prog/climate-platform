import { useState, useEffect } from 'react'
import {
  ArrowRight, Satellite, Cpu, ShieldCheck, RefreshCw, GitBranch, Lock, Upload,
  Radar, FileWarning, Bell, ClipboardCheck, SlidersHorizontal,
} from 'lucide-react'
import { INDUSTRIES, PROCESSING_CHAIN } from '../data/industries'
import { industryForOrg } from '../data/catalog'
import { fetchScoresSummary } from '../api/client'

const STAGE_ICONS = [Satellite, Cpu, Cpu, GitBranch, ArrowRight]

// industryForOrg() returns the CATALOG key; INDUSTRIES uses a couple of different ids.
const CATALOG_TO_INDUSTRY = {
  banking: 'banking', insurance: 'insurance', agriculture: 'agriculture',
  realestate: 'real-estate', assetmgmt: 'asset-management',
}

// Each hazard's actual feeds — so a sector shows ONLY the sources its own hazards use
// (agriculture reads drought+heat → ERA5 + soil moisture; it never touches GloFAS or FIRMS).
const HAZARD_SOURCES = {
  flood: ['GloFAS', 'ERA5 runoff', 'Sentinel-1 SAR'],
  heat: ['ERA5'],
  drought: ['ERA5', 'ERA5-Land soil moisture'],
  storm: ['ERA5 wind', 'Sentinel-3'],
  wildfire: ['NASA FIRMS', 'ERA5 dryness'],
  seismic: ['EMSC', 'ESHM20'],
}

// The one book each sector uploads — the portfolio the climate data gets projected onto.
const PORTFOLIO = {
  banking: { chip: 'Loan tape', body: 'the loan book you upload — each financed asset with its location, so the climate score becomes a collateral discount and a disclosure line.' },
  insurance: { chip: 'Statement of Values', body: 'the SOV you upload — each insured location, deductible and limit, so the score becomes an expected annual loss and a technical premium.' },
  agriculture: { chip: 'Sourcing plots', body: 'the parcels you source from — crop, hectares and origin — so drought and heat on each plot become the share of your volume that fails.' },
  'real-estate': { chip: 'Property schedule', body: 'the property schedule you upload — each asset with its location and EPC, so the score becomes a climate-adjusted value and a Taxonomy line.' },
  'asset-management': { chip: 'Holdings book', body: 'the holdings you upload (ISINs + weights) — resolved to each issuer’s sites, so the score becomes a portfolio climate VaR and an SFDR line.' },
}

// The frameworks each sector actually files against, and one real "when a rule changes" example.
const REGULATORY = {
  banking: {
    frameworks: ['TCFD', 'EU Taxonomy', 'CSRD'],
    example: 'the EU Taxonomy’s "aligned" status needs proof of substantial contribution and minimum safeguards — data this platform didn’t originally collect. Rather than approximate it, every financed asset honestly showed "eligible," never "aligned," with the gap disclosed. When we added the ability to supply it, it arrived as optional upload columns on the exact loan-tape template already in use.',
  },
  insurance: {
    frameworks: ['Solvency II', 'CSRD'],
    example: 'Solvency II’s climate scenario add-ons ask for forward-looking hazard on the insured book. Where a scenario needs an input the SOV didn’t carry, we name the exact field and it arrives as one optional column on the template already in use — never a new integration.',
  },
  agriculture: {
    frameworks: ['CSRD', 'EUDR'],
    example: 'the EUDR requires a deforestation-free proof geolocated to each sourcing plot — a geometry and a cut-off-date forest check this platform didn’t originally collect. Rather than approximate it, a plot with no geometry honestly showed "location mapped, EUDR status pending," never "compliant." When we added it, the plot polygon arrived as one optional column on the exact sourcing template already in use.',
  },
  'real-estate': {
    frameworks: ['EU Taxonomy', 'CSRD'],
    example: 'the EU Taxonomy’s "aligned" test needs an EPC rating and a physical-risk adaptation assessment. Rather than approximate it, an asset without an EPC honestly showed "eligible," never "aligned." When we added it, epc_rating arrived as one optional column on the property schedule already in use.',
  },
  'asset-management': {
    frameworks: ['SFDR', 'EU Taxonomy'],
    example: 'SFDR’s PAI statement adds indicators over time (financed emissions via EVIC, then energy/water/waste). Each new one is named as a specific field and arrives as an optional column on the holdings template already in use — the honest gap only closes once you choose to supply it.',
  },
}

export default function PlatformOverviewPage({ auth }) {
  const [summary, setSummary] = useState(null)
  useEffect(() => {
    let alive = true
    fetchScoresSummary().then(d => alive && setSummary(d)).catch(() => {})
    return () => { alive = false }
  }, [])

  const industryId = CATALOG_TO_INDUSTRY[industryForOrg(auth?.org)] || null
  const sector = INDUSTRIES.find(i => i.id === industryId) || null
  const sectorName = sector?.name || 'Your sector'

  // The sector's own hazards, parsed from its `consumes` line ("drought, heat").
  const hazards = sector
    ? sector.consumes.split(',').map(h => h.trim().toLowerCase()).filter(h => HAZARD_SOURCES[h])
    : []
  const climateSources = [...new Set(hazards.flatMap(h => HAZARD_SOURCES[h] || []))]
  const portfolio = PORTFOLIO[industryId] || { chip: 'Your portfolio', body: 'the book you upload — the assets the climate score gets projected onto.' }
  const regulatory = REGULATORY[industryId] || null

  // Live golden source, SCOPED to this sector's hazards (not the platform-wide total).
  const sectorHazardRows = (summary?.hazards || []).filter(h => hazards.includes(h.hazard_type))
  const liveScores = sectorHazardRows.reduce((n, h) => n + (h.cells || 0), 0)
  const hazardsLive = [...new Set(sectorHazardRows.map(h => h.hazard_type))]  // distinct: a hazard may have >1 model version

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-6xl mx-auto px-8 py-12">
          <p className="text-[11px] uppercase tracking-[0.25em] text-indigo-400 mb-3">{sectorName} · Data foundation</p>
          <h1 className="text-4xl md:text-5xl font-light leading-tight text-gray-900">
            One golden source in.<br /><span className="text-indigo-600">A defensible number out.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-gray-600 leading-relaxed">
            Two things go in — live satellite/climate data for the hazards {sectorName.toLowerCase()} cares about, and
            your own book — and one auditable score per location comes out, translated into {sector ? sector.output.split('·')[0].trim() : 'your business number'}. This
            page is that whole chain, scoped to {sectorName.toLowerCase()}.
          </p>
        </div>
      </header>

      {/* 1 · INPUTS — the two sides of what we ingest, for THIS sector */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="01" title="What goes in" sub="Two inputs, not one" />
        <div className="grid md:grid-cols-2 gap-5 mt-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center"><Radar size={18} /></div>
              <p className="font-medium text-gray-900">The climate side — public, live, ours to maintain</p>
            </div>
            <p className="text-sm text-gray-600 leading-relaxed">
              {sectorName} yield/value is driven by <span className="font-medium text-gray-800">{hazards.length ? hazards.join(' + ') : 'its climate hazards'}</span>.
              Every feed for those hazards lands in one place through a provider-abstraction layer, keyed to the H3
              hexagonal grid — the platform never cares which satellite or agency produced a reading, only where and
              when.
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              {(climateSources.length ? climateSources : ['ERA5']).map(s => (
                <span key={s} className="text-xs bg-gray-100 text-gray-700 rounded-full px-3 py-1">{s}</span>
              ))}
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-9 h-9 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center"><Upload size={18} /></div>
              <p className="font-medium text-gray-900">Your side — the {portfolio.chip.toLowerCase()} the climate data gets projected onto</p>
            </div>
            <p className="text-sm text-gray-600 leading-relaxed">
              A location on its own is just a point on a map. What turns it into a number your business can act on is
              your own book — {portfolio.body} We publish the exact template, and every optional field exists because
              it unlocks a specific, named calculation — never collected for its own sake.
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              <span className="text-xs bg-emerald-50 text-emerald-700 rounded-full px-3 py-1">{portfolio.chip}</span>
            </div>
          </div>
        </div>
        <p className="text-xs text-gray-400 mt-6">The shared foundation underneath — one golden source, the same for every sector:</p>
        <div className="grid sm:grid-cols-4 gap-4 mt-2">
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
            <p className="text-indigo-100 text-sm">Live golden source for {sectorName.toLowerCase()} right now</p>
            <p className="text-3xl font-light">
              {summary == null ? '…' : liveScores.toLocaleString()} <span className="text-lg text-indigo-200">current scores</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-indigo-100 text-sm">Hazards scored on real data</p>
            <p className="text-xl">{hazardsLive.length ? hazardsLive.join(' · ') : (summary == null ? 'loading…' : 'awaiting scores')}</p>
          </div>
        </div>
      </section>

      {/* 3 · OUTPUT — this sector's one number */}
      {sector && (
        <section className="max-w-6xl mx-auto px-8 py-12">
          <SectionLabel n="03" title="What comes out" sub={`The ${sectorName.toLowerCase()} number`} />
          <p className="mt-4 max-w-3xl text-sm text-gray-600 leading-relaxed">
            The identical fetch → project → headline pipeline (<code className="text-xs bg-gray-100 rounded px-1 py-0.5">services/portfolio_engine.py</code>)
            runs under the hood; only the last step — turning a 0–100 score into the {sectorName.toLowerCase()} number — is
            specific to you.
          </p>
          <div className="bg-white rounded-xl border border-gray-200 p-6 mt-6">
            <p className="text-xs text-gray-500 mb-2">Consumes: <span className="text-gray-700">{sector.consumes}</span></p>
            <p className="text-lg text-gray-900 leading-snug font-light">{sector.output}</p>
            <div className="mt-4 space-y-1.5">
              {sector.valuePoints?.map(v => (
                <div key={v} className="flex items-start gap-2 text-sm text-gray-600">
                  <ArrowRight size={14} className="text-indigo-400 mt-1 shrink-0" /><span>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* 4 · WHY US — defensibility, scoped to this sector's own chain */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="04" title="Why this foundation is defensible" sub="Always the latest, always auditable" />
        <div className="grid sm:grid-cols-2 gap-4 mt-6">
          <Why icon={RefreshCw} title="Near-real-time, never stale"
            body="New observations flow straight to scores. Each cell carries 6h/24h/48h velocity, so you see risk rising before it lands — not in next quarter's report." />
          <Why icon={Lock} title="Append-only golden source"
            body="Scores are immutable. A new score retires the old one with a timestamp; nothing is overwritten. Today's number and last week's both stand, fully reproducible." />
          <Why icon={ShieldCheck} title="Audit-grade traceability"
            body="Every score records its model version, data vintage and a fingerprint of its inputs — the evidence regulators and auditors ask for." />
          <Why icon={SlidersHorizontal} title="Recommended, never forced"
            body="Every modelled figure is a recommendation a permitted human can override with a mandatory reason, fully audited. Never a black box." />
          <Why icon={FileWarning} title="Honest about the gaps"
            body="Where we don't yet have the data to answer a question, we say so explicitly rather than approximate — a disclosed gap, never a guess dressed up as a number." />
          <Why icon={GitBranch} title="One score, every output"
            body={`The same canonical ${hazards.join('/') || 'hazard'} score feeds every ${sectorName.toLowerCase()} output — the disclosure, the risk map and the early warning all read one number, not three drifting copies.`} />
        </div>
      </section>

      {/* 5 · REGULATORY CHANGE COMMITMENT — this sector's frameworks */}
      {regulatory && (
        <section className="max-w-6xl mx-auto px-8 py-12">
          <SectionLabel n="05" title="When a regulation changes" sub="Whose job it is to notice, and what happens next" />
          <div className="bg-white rounded-xl border border-gray-200 p-6 mt-6">
            <p className="text-gray-800 leading-relaxed">
              The frameworks that bind {sectorName.toLowerCase()} — <span className="font-medium">{regulatory.frameworks.join(', ')}</span> —
              don't stand still. When one starts asking for something we don't yet collect, that gap is
              <span className="font-medium"> our responsibility to catch, not yours to discover during an audit.</span> We
              hold to a fixed sequence, every time:
            </p>
          </div>
          <div className="grid sm:grid-cols-4 gap-4 mt-5">
            <RegStep n="1" icon={Bell} title="We monitor the frameworks"
              body={`${regulatory.frameworks.join(', ')} are tracked on an ongoing basis — not reacted to after a client asks why a number is missing.`} />
            <RegStep n="2" icon={FileWarning} title="We name the exact new field"
              body="Not 'more data needed' — a specific, named field, and exactly which calculation it unlocks." />
            <RegStep n="3" icon={ClipboardCheck} title="We tell you in time"
              body="You hear about a new required field with real lead time before the next deadline — enough to pull it from your own systems." />
            <RegStep n="4" icon={Upload} title="You supply it your way"
              body={`The same ${portfolio.chip.toLowerCase()} template you already use gets one new optional column. Nothing else changes.`} />
          </div>
          <div className="bg-gray-900 rounded-xl p-6 mt-5 text-white">
            <p className="text-sm text-gray-300 leading-relaxed">
              <span className="font-medium text-white">A real example, not a hypothetical:</span> {regulatory.example}
            </p>
          </div>
        </section>
      )}
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
