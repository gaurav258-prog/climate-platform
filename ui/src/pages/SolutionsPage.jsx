import { useState } from 'react'
import {
  Landmark, Umbrella, Sprout, Building2, TrendingUp, Layers, Truck, Building,
  ArrowRight, ArrowLeft, Check,
} from 'lucide-react'
import SectorFlowDiagram from '../components/software/SectorFlowDiagram'

// Outward-facing solutions catalogue. One engine, many industries.
// Five are live in the product today; three (reinsurance, supply chain, public
// sector) are the confirmed next targets and carry a "Coming soon" state —
// this mirrors the in-app Industry-modules grid so the public site shows the
// same target scope. Descriptions are intentionally plain data (not copy baked
// into JSX) — expect these to be rewritten as each vertical's offering
// evolves; keep them short and accurate.
const SECTORS = [
  {
    id: 'banking', label: 'Banking', icon: Landmark, live: true,
    tagline: 'Physical climate risk for lending & disclosure',
    headline: 'Know which loans climate is coming for.',
    narrative:
      'Project every asset in your book against flood, wildfire and seismic hazard — today and under forward-looking climate scenarios. Quantify value-at-risk, satisfy TCFD, EU Taxonomy and CSRD, and drill from a single portfolio number down to one building — every figure traceable to its source.',
    outcomes: [
      'Portfolio value-at-risk by scenario & time horizon',
      'Asset-level exposure across every hazard',
      'TCFD / EU-Taxonomy / CSRD-ready disclosure',
      'A full audit trail behind every number',
    ],
    outputs: [
      { t: 'Command center', d: 'Live exposure across your whole loan book, at a glance.' },
      { t: 'Portfolio screening', d: 'Every asset scored per hazard — sort by risk and value.' },
      { t: 'Regulatory reporting', d: 'Disclosure packs generated straight from the data.' },
    ],
    flow: {
      onboarding: { t: 'Client Onboarding', s: 'Org, roles & licensed offering', tag: 'ONE-TIME SETUP' },
      inputs: [
        { t: 'Loan Book', s: 'Property location, type & value', tag: 'CSV / EXCEL' },
        { t: 'Outstanding Balance', s: 'Optional — enables LTV calc', tag: 'OPTIONAL FIELD' },
      ],
      engine: [
        { t: 'Hazard Scoring', s: 'Flood, wildfire, heat & quake, per location' },
        { t: 'Valuation & Taxonomy Calc', s: 'Risk-bucket haircut → VaR, stranded-asset exposure' },
      ],
      outputs: [
        { t: 'Portfolio VaR', s: 'By scenario & time horizon, live', tag: 'LIVE DASHBOARD' },
        { t: 'Audit & Disclosure Export', s: 'TCFD / EU Taxonomy, audit-ready', tag: 'TCFD-READY' },
      ],
      footer: 'Value-at-risk and stranded-asset exposure trace to a model version and data vintage — the defensible basis for TCFD and EU Taxonomy disclosure.',
    },
  },
  {
    id: 'insurance', label: 'Insurance', icon: Umbrella, live: true,
    tagline: 'Underwriting & parametric on live hazard data',
    headline: 'Price the risk you’re actually taking on.',
    narrative:
      'Underwrite with forward-looking loss curves and design parametric cover triggered by the same live hazard data your models already trust — one consistent view of hazard, from the quote to the claim.',
    outcomes: [
      'Forward-looking loss curves by peril',
      'Location-precise exposure accumulation',
      'Objective parametric triggers on live data',
      'One hazard view across the whole book',
    ],
    outputs: [
      { t: 'Risk pricing', d: 'Hazard-calibrated loss curves for any location.' },
      { t: 'Accumulation', d: 'See concentration before it becomes a catastrophe.' },
      { t: 'Parametric design', d: 'Data-driven payout triggers you can defend.' },
    ],
    flow: {
      onboarding: { t: 'Client Onboarding', s: 'Org, roles & licensed offering', tag: 'ONE-TIME SETUP' },
      inputs: [
        { t: 'Insured Locations', s: 'Address, sum insured & peril', tag: 'CSV / EXCEL' },
      ],
      engine: [
        { t: 'Hazard Scoring', s: 'Per peril, per location, live' },
        { t: 'Loss-Curve Pricing', s: 'Loss curve → expected annual loss → premium' },
      ],
      outputs: [
        { t: 'Technical Premium', s: 'Defensible, parametric-trigger ready', tag: 'LIVE DASHBOARD' },
        { t: 'Audit & Disclosure Export', s: 'Pricing basis & model version', tag: 'DEFENSIBLE EXPORT' },
      ],
      footer: 'The same hazard score prices the policy and arms the parametric trigger — underwriting and claims read one number, always in sync.',
    },
  },
  {
    id: 'agriculture', label: 'Agriculture', icon: Sprout, live: true,
    tagline: 'Climate cost-of-goods across the supply chain',
    headline: 'Know what climate is doing to your cost-of-goods.',
    narrative:
      'Roll live climate hazard on every sourcing plot up your bill of materials into one auditable "COGS-at-risk" per commodity — event-backtested (cocoa 2023/24, coffee 2021), scenario-projected, and EUDR+CSRD ready. The number no one else builds: hazard on the plots you buy from, not just the assets you own.',
    outcomes: [
      'COGS-at-risk by commodity, scenario & horizon',
      'Every sourcing plot scored & mapped, event-backtested',
      'Early warning on commodities heating up',
      'EUDR (deforestation-free + climate-viable) & CSRD packs',
    ],
    outputs: [
      { t: 'COGS-at-risk', d: 'Climate cost on your bill of materials, per commodity.' },
      { t: 'Sourcing book + map', d: 'Every plot scored per hazard, traceable to the source.' },
      { t: 'EUDR + CSRD disclosure', d: 'Deforestation-free and climate-viable, one record.' },
    ],
    flow: {
      onboarding: { t: 'Client Onboarding', s: 'Org, roles & licensed offering', tag: 'ONE-TIME SETUP' },
      inputs: [
        { t: 'Sourcing Plots', s: 'Commodity, hectares & location', tag: 'CSV / EXCEL' },
      ],
      engine: [
        { t: 'Hazard Scoring', s: 'Drought & heat, per plot, per season' },
        { t: 'Yield-Loss Model', s: 'Crop-sensitivity → yield-loss fraction' },
      ],
      outputs: [
        { t: 'COGS-at-Risk (€)', s: 'Per commodity, scenario & horizon', tag: 'LIVE DASHBOARD' },
        { t: 'Audit & Disclosure Export', s: 'Deforestation-free & climate-viable', tag: 'EUDR / CSRD' },
      ],
      footer: 'The plots you buy from, not just the assets you own — event-backtested against real cocoa and coffee price shocks.',
    },
  },
  {
    id: 'real-estate', label: 'Real Estate', icon: Building2, live: true,
    tagline: 'Portfolio value & NOI impact for owned property',
    headline: 'Know what climate costs your NOI — before it does.',
    narrative:
      'An owned property is a loan-book asset with no loan attached. We apply the same risk-based valuation haircut banks use, and insurance’s real pricing chain to estimate what each property would cost to insure at its hazard exposure — expressed as a share of net operating income, the number your team already prices against.',
    outcomes: [
      'Climate-adjusted valuation, per property',
      'NOI-impact %, not a vague risk score',
      'EU Taxonomy eligibility per property',
      'Portfolio rollup by hazard and geography',
    ],
    outputs: [
      { t: 'Portfolio & NOI impact', d: 'Climate-adjusted value and NOI impact, per property.' },
      { t: 'Climate-adjusted valuation', d: 'Same haircut schedule used across the platform.' },
      { t: 'EU Taxonomy status', d: 'Eligibility per property, honestly scoped.' },
    ],
    flow: {
      onboarding: { t: 'Client Onboarding', s: 'Org, roles & licensed offering', tag: 'ONE-TIME SETUP' },
      inputs: [
        { t: 'Property Schedule', s: 'Address, value & annual NOI', tag: 'CSV / EXCEL' },
      ],
      engine: [
        { t: 'Hazard Scoring', s: 'Per property, per scenario' },
        { t: 'Valuation & NOI-Impact Calc', s: 'Same haircut + insurance’s pricing chain' },
      ],
      outputs: [
        { t: 'Climate-Adjusted Value', s: 'Plus NOI-impact %, per property', tag: 'LIVE DASHBOARD' },
        { t: 'Audit & Disclosure Export', s: 'Taxonomy status, honestly scoped', tag: 'TAXONOMY EXPORT' },
      ],
      footer: 'An owned property is a loan-book asset with no loan attached — it reuses banking’s valuation engine directly, not a new model.',
    },
  },
  {
    id: 'asset-management', label: 'Asset Management', icon: TrendingUp, live: true,
    tagline: 'Portfolio climate VaR & screening',
    headline: 'See portfolio climate risk the way your banks already do.',
    narrative:
      'Reuses the exact same risk-bucket discount schedule as banking and real estate — applied value-weighted across your holdings book — to produce one portfolio-level climate exposure figure, a High/Very-High screen, and EU Taxonomy eligibility per holding. Zero new scoring code, just the same engine pointed at a new book.',
    outcomes: [
      'Portfolio-level climate VaR, value-weighted',
      'Screening flags on High/Very-High holdings',
      'EU Taxonomy eligibility per holding',
      'Same golden source as every other vertical',
    ],
    outputs: [
      { t: 'Portfolio climate VaR', d: 'Value-weighted climate exposure across the book.' },
      { t: 'Screening', d: 'Holdings above the risk threshold, flagged automatically.' },
      { t: 'EU Taxonomy eligibility', d: 'Per-holding status wherever a NACE code is supplied.' },
    ],
    flow: {
      onboarding: { t: 'Client Onboarding', s: 'Org, roles & licensed offering', tag: 'ONE-TIME SETUP' },
      inputs: [
        { t: 'Holdings Book', s: 'Name, position value & location', tag: 'CSV / EXCEL' },
        { t: 'NACE Code', s: 'Optional — enables Taxonomy check', tag: 'OPTIONAL FIELD' },
      ],
      engine: [
        { t: 'Hazard Scoring', s: 'Value-weighted, across the book' },
        { t: 'Risk & Taxonomy Calc', s: 'Same discount schedule as banking' },
      ],
      outputs: [
        { t: 'Portfolio Climate VaR', s: '€ / % value-weighted, screening flags', tag: 'LIVE DASHBOARD' },
        { t: 'Audit & Disclosure Export', s: 'Eligibility, model version, scored date', tag: 'TCFD-READY' },
      ],
      footer: 'Zero new scoring code — the exact same risk-bucket schedule as Banking and Real Estate, pointed at a new book.',
    },
  },
  {
    id: 'reinsurance', label: 'Reinsurance', icon: Layers, live: false,
    tagline: 'Portfolio tail aggregation & parametric structuring',
    headline: 'Aggregate the tail. Structure the trigger.',
    narrative:
      'Reinsurers price the tail of someone else’s book. The platform already has the parametric primitives — reinsurance aggregates cedent exposures across the same H3 grid into portfolio tail risk, and structures cat bonds on the same objective scores the cedents price on.',
    outcomes: [
      'Aggregate many cedent books into one tail view',
      'Cat-bond structuring on objective, auditable triggers',
      'Same golden source the cedents already price on',
    ],
    outputs: [
      { t: 'Tail aggregation', d: 'Portfolio PML / occurrence across cells.' },
      { t: 'Correlation', d: 'Across hazards and geographies.' },
      { t: 'Cat-bond design', d: 'Parametric triggers, structured on live data.' },
    ],
    flow: {
      onboarding: { t: 'Client Onboarding', s: 'Org, roles & licensed offering', tag: 'ONE-TIME SETUP' },
      inputs: [
        { t: 'Cedent Exposures', s: 'Aggregated across many books', tag: 'BATCH INGEST' },
      ],
      engine: [
        { t: 'Hazard Scoring', s: 'Across every cell, every book' },
        { t: 'Tail Aggregation', s: 'PML / occurrence, portfolio-level' },
      ],
      outputs: [
        { t: 'Portfolio Tail View', s: 'Cat-bond structuring, objective triggers', tag: 'PLANNED DASHBOARD' },
        { t: 'Audit & Disclosure Export', s: 'Same golden source cedents price on', tag: 'PLANNED EXPORT' },
      ],
      footer: 'The parametric primitives already exist — reinsurance aggregates cedent exposures onto the same H3 grid, nothing new to build there.',
    },
  },
  {
    id: 'supply-chain', label: 'Supply Chain', icon: Truck, live: false,
    tagline: 'Facility & supplier business-interruption exposure',
    headline: 'Know which nodes climate can break.',
    narrative:
      'A facility or supplier is a located asset like any other. The projection surfaces which nodes sit in elevated hazard cells, translating straight into business-interruption exposure and continuity priorities.',
    outcomes: [
      'Every facility and supplier mapped to its hazard score',
      'Business-interruption exposure by node',
      'Continuity prioritization, not guesswork',
    ],
    outputs: [
      { t: 'Node exposure', d: 'Hazard score for every facility and supplier.' },
      { t: 'BI estimate', d: 'Business-interruption exposure, quantified.' },
      { t: 'SPOF flags', d: 'Single-point-of-failure nodes, surfaced.' },
    ],
    flow: {
      onboarding: { t: 'Client Onboarding', s: 'Org, roles & licensed offering', tag: 'ONE-TIME SETUP' },
      inputs: [
        { t: 'Facility & Supplier List', s: 'Locations across the network', tag: 'BATCH INGEST' },
      ],
      engine: [
        { t: 'Hazard Scoring', s: 'Per node' },
        { t: 'Node Risk Flagging', s: 'Elevated-hazard cells, flagged' },
      ],
      outputs: [
        { t: 'BI Exposure', s: 'Business-interruption, quantified', tag: 'PLANNED DASHBOARD' },
        { t: 'Audit & Disclosure Export', s: 'Single-point-of-failure flags', tag: 'PLANNED EXPORT' },
      ],
      footer: 'A facility or supplier is a located asset like any other — the same projection surfaces which nodes sit in elevated hazard.',
    },
  },
  {
    id: 'public-sector', label: 'Public Sector', icon: Building, live: false,
    tagline: 'Vulnerability mapping & adaptation budgeting',
    headline: 'Put resilience spend where it counts most.',
    narrative:
      'Governments allocate scarce adaptation budgets. Population and infrastructure are located assets — the same projection produces a vulnerability map that ranks where every euro of resilience spend goes furthest.',
    outcomes: [
      'Vulnerability map by area and hazard',
      'Adaptation budget prioritization',
      'Same auditable scores used by regulated finance',
    ],
    outputs: [
      { t: 'Vulnerability index', d: 'Area-level, per hazard.' },
      { t: 'Exposure', d: 'Population and infrastructure, mapped.' },
      { t: 'Spend ranking', d: 'Where adaptation budget goes furthest.' },
    ],
    flow: {
      onboarding: { t: 'Client Onboarding', s: 'Org, roles & licensed offering', tag: 'ONE-TIME SETUP' },
      inputs: [
        { t: 'Population & Infrastructure', s: 'Located assets, area by area', tag: 'BATCH INGEST' },
      ],
      engine: [
        { t: 'Hazard Scoring', s: 'Per area' },
        { t: 'Vulnerability Ranking', s: 'Vulnerability × value at stake' },
      ],
      outputs: [
        { t: 'Vulnerability Map', s: 'Where every euro goes furthest', tag: 'PLANNED DASHBOARD' },
        { t: 'Audit & Disclosure Export', s: 'Same auditable scores as regulated finance', tag: 'PLANNED EXPORT' },
      ],
      footer: 'Population and infrastructure are located assets — the same engine that prices a loan book ranks adaptation spend.',
    },
  },
]

export default function SolutionsPage({ onHome, onEnter }) {
  const [activeId, setActiveId] = useState('banking')
  const sector = SECTORS.find(s => s.id === activeId) || SECTORS[0]
  const Icon = sector.icon

  return (
    <div className="h-screen overflow-y-auto bg-white text-[#1d1d1f]">
      {/* nav */}
      <nav className="sticky top-0 z-30 flex items-center justify-between border-b border-gray-200 bg-white/80 px-8 py-3.5 backdrop-blur">
        <button onClick={onHome} className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
          <ArrowLeft size={16} className="text-gray-400" />
          <span>Tel<span className="text-[#0071e3]">lumen</span></span>
        </button>
        <button onClick={onEnter} className="rounded-full bg-[#0071e3] px-4 py-2 text-[13px] font-medium text-white">
          Enter the platform
        </button>
      </nav>

      {/* header */}
      <header className="mx-auto max-w-5xl px-8 pt-14 pb-8 text-center">
        <p className="text-xs font-medium uppercase tracking-[0.15em] text-gray-400">Solutions</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight md:text-5xl">One engine, tuned to your industry.</h1>
        <p className="mx-auto mt-4 max-w-2xl text-[17px] leading-relaxed text-gray-500">
          Every sector reads the same live view of climate risk — then applies its own maths.
          Pick your world below.
        </p>
      </header>

      {/* tabs */}
      <div className="sticky top-[57px] z-20 border-b border-gray-200 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-1.5 px-6 py-2.5">
          {SECTORS.map(s => {
            const on = s.id === activeId
            const TabIcon = s.icon
            return (
              <button key={s.id} onClick={() => setActiveId(s.id)}
                className={`flex shrink-0 items-center gap-2 rounded-full px-4 py-2 text-[14px] font-medium transition ${
                  on ? 'bg-[#1d1d1f] text-white' : 'text-gray-500 hover:bg-gray-100 hover:text-[#1d1d1f]'}`}>
                <TabIcon size={15} strokeWidth={1.8} />
                {s.label}
                {s.live && (
                  <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${
                    on ? 'bg-emerald-400/20 text-emerald-300' : 'bg-emerald-50 text-emerald-600'}`}>LIVE</span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* active sector */}
      <section className="mx-auto max-w-5xl px-8 py-14">
        <div className="grid gap-12 md:grid-cols-[1.1fr_1fr]">
          {/* left — narrative */}
          <div>
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#0071e3]/10 text-[#0071e3]">
                <Icon size={22} strokeWidth={1.7} />
              </span>
              <div>
                <p className="text-[12px] font-medium uppercase tracking-wide text-gray-400">{sector.label}</p>
                <p className="text-[13px] text-gray-500">{sector.tagline}</p>
              </div>
            </div>

            <h2 className="mt-6 text-3xl font-semibold tracking-tight md:text-4xl">{sector.headline}</h2>
            <p className="mt-4 text-[16px] leading-relaxed text-gray-600">{sector.narrative}</p>

            <ul className="mt-6 space-y-2.5">
              {sector.outcomes.map(o => (
                <li key={o} className="flex items-start gap-2.5 text-[15px] text-[#1d1d1f]">
                  <Check size={17} className="mt-0.5 shrink-0 text-[#0071e3]" strokeWidth={2.4} />
                  {o}
                </li>
              ))}
            </ul>

            <div className="mt-8">
              {sector.live ? (
                <button onClick={() => onEnter(sector.id)}
                  className="inline-flex items-center gap-2 rounded-full bg-[#0071e3] px-6 py-3 text-[15px] font-medium text-white transition hover:brightness-110">
                  See it live <ArrowRight size={17} />
                </button>
              ) : (
                <span className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-gray-50 px-6 py-3 text-[15px] font-medium text-gray-400">
                  <span className="h-2 w-2 rounded-full bg-amber-400" /> Coming soon
                </span>
              )}
            </div>
          </div>

          {/* right — what you get */}
          <div className="rounded-3xl bg-[#f5f5f7] p-7">
            <p className="text-[12px] font-medium uppercase tracking-wide text-gray-400">What you get</p>
            <div className="mt-4 space-y-3">
              {sector.outputs.map((o, i) => (
                <div key={o.t} className="rounded-2xl bg-white p-4 shadow-sm">
                  <div className="flex items-start gap-3">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[#1d1d1f] text-[12px] font-semibold text-white">{i + 1}</span>
                    <div>
                      <h3 className="text-[15px] font-semibold">{o.t}</h3>
                      <p className="mt-0.5 text-[13px] leading-relaxed text-gray-500">{o.d}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-5 text-[12px] leading-relaxed text-gray-400">
              Same live data. Same engine. The output is shaped to how {sector.label.toLowerCase()} works.
            </p>
          </div>
        </div>
      </section>

      {/* how it works — 3-lane data-flow diagram, sector-specific content */}
      <section className="border-t border-gray-200 bg-[#f5f5f7] py-14">
        <div className="mx-auto max-w-5xl px-8">
          <p className="text-center text-[12px] font-medium uppercase tracking-wide text-gray-400">How it works</p>
          <h3 className="mt-2 text-center text-2xl font-semibold tracking-tight md:text-3xl">
            What you send us. What we do with it. What you get back.
          </h3>

          <div className="mt-8 overflow-x-auto rounded-2xl border border-gray-200 bg-white p-1">
            <SectorFlowDiagram flow={sector.flow} />
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-center gap-6 text-[12px] text-gray-500">
            <span className="flex items-center gap-2"><span className="h-0 w-6 border-t-2 border-dashed border-[#1d1d1f]" />Automatic hand-off</span>
            <span className="flex items-center gap-2"><span className="h-0 w-6 border-t-2 border-[#1d1d1f]" />Computed &amp; scored</span>
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: '#2F4C86' }} />Client input</span>
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: '#147159' }} />Tellumen engine</span>
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: '#A66A26' }} />Disclosure output</span>
          </div>

          <p className="mx-auto mt-6 max-w-2xl text-center text-[13px] leading-relaxed text-gray-500">
            <strong className="font-semibold text-[#1d1d1f]">{sector.label}.</strong> {sector.flow.footer}
          </p>
        </div>
      </section>

      {/* and more */}
      <section className="border-t border-gray-200 bg-[#f5f5f7] py-14">
        <div className="mx-auto max-w-3xl px-8 text-center">
          <h3 className="text-2xl font-semibold tracking-tight">Eight sectors. One engine.</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-gray-500">
            Five are live today. Reinsurance, supply-chain and the public sector are next — the
            physical-risk primitives are already built, only the sector-specific output is new.
          </p>
          <div className="mt-7 flex items-center justify-center gap-3">
            <button onClick={onEnter}
              className="inline-flex items-center gap-2 rounded-full bg-[#0071e3] px-6 py-3 text-[15px] font-medium text-white transition hover:brightness-110">
              Enter the platform <ArrowRight size={17} />
            </button>
            <button onClick={onHome}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-6 py-3 text-[15px] font-medium text-[#1d1d1f]">
              Back to home
            </button>
          </div>
        </div>
      </section>

      <footer className="border-t border-gray-200 px-8 py-8 text-center text-[12px] text-gray-400">
        Tellumen — Light on the Earth · one engine, every sector · view powered by Sen
      </footer>
    </div>
  )
}
