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
    overview: 'Banks lend against physical collateral — homes, offices, farmland, factories — and hold regulatory capital against the risk that collateral loses value. A loan book is really a map of locations, whether the bank has looked at it that way or not.',
    climateImpact: "Flood, wildfire, heat and drought don't just damage a building — they cut its resale value, its insurability, and the borrower's ability to keep repaying. Regulators now expect banks to quantify this exposure directly, not estimate it at a national or regional average.",
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
    caseStudy: {
      eyebrow: 'Real world · Valencia, Spain · 2024',
      title: '€20bn of exposure nobody saw coming — until the water did.',
      body: 'When the DANA storm flooded Valencia in October 2024, the Bank of Spain found Spanish banks held roughly €20bn of credit exposure concentrated in the flood zone — 1.8% of all Spanish banking credit. The regulator was explicit: this was exposure, not yet realized losses, and the event proved "non-systemic" and "absorbable." But the concentration itself had gone unseen until the flood arrived.',
      stat1: ['Exposure discovered', '€20bn+'],
      stat2: ['Share of national credit', '1.8%'],
      source: 'Source: Banco de España statements, Nov 2024 & Jan 2025',
      whatItMeans: 'On Tellumen, this isn\'t a discovery — it\'s a standing number. Every loan is scored and screened by location the moment it\'s booked, so flood-zone concentration shows up on the Command Center as a live figure, not something a regulator has to go looking for after the water recedes.',
    },
  },
  {
    id: 'insurance', label: 'Insurance', icon: Umbrella, live: true,
    tagline: 'Underwriting & parametric on live hazard data',
    overview: "Insurers price the probability and cost of a bad event before it happens, then hold capital against the worst plausible outcome. Underwriting is a bet on how well the risk was actually understood at the point of sale.",
    climateImpact: "Floods, wildfires and storms are shifting in frequency and severity faster than most pricing models update — meaning yesterday's 'safe' postcode can be tomorrow's concentrated loss. Underpriced risk shows up years later, all at once, in a single catastrophic season.",
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
    caseStudy: {
      eyebrow: 'Real world · Valencia, Spain · 2024',
      title: "One flood, 239,000 claims — and the losses weren't where you'd expect.",
      body: "Spain's public catastrophe insurer, Consorcio de Compensación de Seguros, processed over 239,000 claims and paid out more than €4bn after the 2024 Valencia floods. The losses were hugely concentrated in specific small municipalities along historic flood channels — Paiporta and Catarroja alone outweighed the much larger city of València itself.",
      stat1: ['Claims processed', '239,000+'],
      stat2: ['Paid out', '€4bn+'],
      source: 'Source: Consorcio de Compensación de Seguros, official briefing notes',
      whatItMeans: 'On Tellumen, Paiporta and València are never priced the same, because the loss curve runs per H3 cell, not per region or postcode. The concentration that caught the wider market off guard is already inside a Tellumen technical premium, on day one.',
    },
  },
  {
    id: 'agriculture', label: 'Agriculture', icon: Sprout, live: true,
    tagline: 'Climate cost-of-goods across the supply chain',
    overview: "Food and commodity buyers build their cost base on assumptions about what a harvest will yield — assumptions set months or years before the crop is in the ground. A sourcing plan is a bet on climate staying roughly where it's always been.",
    climateImpact: "Heat and drought hit yield directly — fewer tonnes, smaller beans, lower quality — and the effect compounds across a concentrated growing region faster than substitute supply can be found. The result shows up as a commodity price spike that looks sudden but was building for a season.",
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
    caseStudy: {
      eyebrow: 'Real world · West Africa · 2023–24',
      title: 'Cocoa prices rose 177% — our backtest called the real driver.',
      body: "Cocoa prices surged 177% in 2024 after 2023's excess rain triggered a black-pod disease outbreak, followed by an El Niño drought and a February 2024 heatwave that World Weather Attribution found was 4°C hotter and 10x more likely due to climate change. Our own model, calibrated against the real production shock, correctly attributed the crash to heat rather than drought and reproduced a +173% price move against the real +177%.",
      stat1: ['Model predicted', '+173%'],
      stat2: ['Actual move', '+177%'],
      source: 'Source: ICCO, World Weather Attribution, Climate Central; internal backtest',
      whatItMeans: 'On Tellumen, this shows up as COGS-at-risk rising on the sourcing plots themselves, as heat and rainfall anomalies build through the season — not as a 177% price spike a buyer only feels at the point of purchase.',
    },
  },
  {
    id: 'real-estate', label: 'Real Estate', icon: Building2, live: true,
    tagline: 'Portfolio value & NOI impact for owned property',
    overview: "A property's value is a bet that the building, and the land under it, will still be usable — and insurable — for the life of the investment. Valuation models are built on historical stability, not forward climate risk.",
    climateImpact: "Flood and wildfire don't just cause direct damage — they trigger insurer non-renewals, financing difficulty, and buyer hesitation that erode value long before any water reaches the door. Official flood maps are frequently out of date or too coarse to catch this before the market prices it in the hard way.",
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
    caseStudy: {
      eyebrow: 'Real world · United States & Germany',
      title: '$200bn of US housing was overvalued — because 83% of at-risk homes sat outside the flood map.',
      body: "A peer-reviewed Nature Climate Change study — co-authored with the Federal Reserve, EDF and First Street Foundation — found the US flood-exposed housing stock overvalued by $121–237bn, because 83% of at-risk properties sit outside official FEMA flood zones. The same blind spot played out physically in 2021, when floods in Germany's Ahr valley — a region not classified as extreme flood-risk — destroyed or condemned hundreds of buildings.",
      stat1: ['Overvaluation found', '$121–237bn'],
      stat2: ['At-risk homes outside FEMA zones', '83%'],
      source: 'Source: Nature Climate Change, Feb 2023; First Street Foundation',
      whatItMeans: "On Tellumen, a property's risk score doesn't depend on which side of a FEMA line it happens to sit on. Every property is scored against the same live hazard model regardless of official zone boundaries — so the 83% of at-risk homes invisible to the map are never invisible to a Tellumen portfolio.",
    },
  },
  {
    id: 'asset-management', label: 'Asset Management', icon: TrendingUp, live: true,
    tagline: 'Portfolio climate VaR & screening',
    overview: "A diversified portfolio is built to survive any single holding underperforming — but physical climate risk doesn't respect diversification if multiple holdings share the same underlying exposure: same region, same infrastructure type, same hazard.",
    climateImpact: 'A utility, REIT, or infrastructure holding can carry years of accumulating physical-risk liability that never shows up in a quarterly earnings report — until a single event turns it into a permanent impairment or a bankruptcy filing.',
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
    caseStudy: {
      eyebrow: 'Real world · California · 2019',
      title: "PG&E's wildfire risk wasn't hidden — it was ignored for a decade.",
      body: 'When PG&E filed for Chapter 11 bankruptcy in January 2019 over $30bn+ in wildfire liability, its credit rating collapsed from investment grade to junk and roughly $29bn in market value was erased — losses spread across the index funds and pension funds that held it as a "safe" utility. The risk wasn\'t a surprise: a 2010 felony safety conviction, a 2015 fire already traced to its equipment, and 27 separate regulatory violations predate the crisis by years.',
      stat1: ['Wildfire liability', '$30bn+'],
      stat2: ['Market cap erased', '~$29bn'],
      source: "Source: SEC filings; S&P/Moody's rating actions; DOJ, CPUC records",
      whatItMeans: 'On Tellumen, every holding in a portfolio is screened for physical-risk concentration continuously, not discovered in a bankruptcy filing. A utility with this profile shows up flagged High/Very-High on the screening dashboard years before it becomes a 10-K disclosure.',
    },
  },
  {
    id: 'reinsurance', label: 'Reinsurance', icon: Layers, live: false,
    tagline: 'Portfolio tail aggregation & parametric structuring',
    overview: "Reinsurers absorb the tail risk that individual insurers can't hold alone — pricing catastrophic, low-frequency, high-severity events across many cedents' books at once.",
    climateImpact: 'Climate change is fattening the tail: the same event now correlates across more cedents and more geographies simultaneously than historical models assumed, concentrating risk exactly where diversification was supposed to protect against it.',
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
    overview: "A supply chain is only as resilient as its most exposed single node — a factory, a port, a supplier's supplier — wherever that happens to sit.",
    climateImpact: 'Flood, storm and heat can knock out a single facility for weeks, and the disruption cascades through every downstream customer who depended on it, regardless of how resilient the rest of the network is.',
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
    overview: 'Governments allocate a fixed adaptation budget across an entire population and its infrastructure, with imperfect visibility into which specific areas carry the most risk.',
    climateImpact: 'Flood, heat and wildfire exposure is never distributed evenly — it concentrates in specific neighborhoods and infrastructure corridors, meaning a budget spread evenly across a region can miss where the real risk, and the real need, actually sits.',
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

function Btn({ children, onClick, primary }) {
  const cls = 'inline-flex items-center gap-2 rounded-lg px-[22px] py-3.5 text-[14px] font-medium transition ' +
    (primary
      ? 'bg-[#7DD3FC] text-[#0A0F1C] hover:bg-[#38BDF8]'
      : 'border border-white/10 text-[#E8EEF7] hover:border-[#7DD3FC] hover:text-[#7DD3FC] hover:bg-[#38BDF8]/5')
  return <button onClick={onClick} className={cls}>{children}</button>
}

function Eyebrow({ children }) {
  return <span className="tl-mono mb-4 inline-block text-[13.5px] font-semibold uppercase tracking-[0.16em] text-[#38BDF8]">{children}</span>
}

function Nav({ onHome, onEnter, onBack }) {
  return (
    <nav className="sticky top-0 z-30 flex items-center justify-between bg-[#0A0F1C]/80 px-8 py-3.5 backdrop-blur-md">
      <button onClick={onBack || onHome} className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-[#F4EFE6]">
        <ArrowLeft size={16} className="text-[#64748B]" />
        <span>{onBack ? 'All sectors' : <>Tel<span className="text-[#7DD3FC]">lumen</span></>}</span>
      </button>
      <button onClick={onEnter} className="rounded-lg bg-[#7DD3FC] px-4 py-2 text-[13px] font-medium text-[#0A0F1C] hover:bg-[#38BDF8]">
        Enter the platform
      </button>
    </nav>
  )
}

function Footer() {
  return (
    <footer className="border-t border-white/[0.09] px-8 py-8 text-center">
      <span className="tl-mono text-[11px] tracking-[0.10em] text-[#64748B]">
        Tellumen — Light on the Earth · one engine, every sector · view powered by Sen
      </span>
    </footer>
  )
}

// index — the only entry point into a sector: 8 cards, nothing else
function SolutionsIndex({ onOpen, onHome, onEnter }) {
  return (
    <div className="tl-sans h-screen overflow-y-auto bg-[#0A0F1C] text-[#E8EEF7]" style={{ scrollBehavior: 'smooth' }}>
      <Nav onHome={onHome} onEnter={onEnter} />

      <header className="mx-auto max-w-4xl px-8 pt-14 pb-10 text-center">
        <Eyebrow>Solutions</Eyebrow>
        <h1 className="tl-serif text-[clamp(30px,4.6vw,48px)] font-light italic leading-[1.1] text-[#F4EFE6]">
          One engine, tuned to your industry.
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-[#94A3B8]">
          Every sector reads the same live view of climate risk — then applies its own maths.
          Pick your world below.
        </p>
      </header>

      <section className="mx-auto max-w-5xl px-8 pb-16">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {SECTORS.map(s => {
            const SIcon = s.icon
            return (
              <button key={s.id} onClick={() => onOpen(s.id)}
                className="flex flex-col items-start rounded-2xl border border-white/[0.09] bg-white/[0.02] p-6 text-left transition hover:-translate-y-0.5 hover:border-[#38BDF8]/35 hover:bg-[#38BDF8]/[0.03]">
                <div className="flex w-full items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#38BDF8]/10 text-[#7DD3FC]">
                    <SIcon size={19} strokeWidth={1.7} />
                  </span>
                  <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide ${
                    s.live ? 'bg-[#34D399]/10 text-[#34D399]' : 'bg-white/[0.06] text-[#94A3B8]'}`}>
                    {s.live ? 'Live' : 'Roadmap'}
                  </span>
                </div>
                <div className="mt-4 text-[15px] font-medium text-[#F4EFE6]">{s.label}</div>
                <div className="mt-1 text-[12.5px] leading-relaxed text-[#94A3B8]">{s.tagline}</div>
                <div className="mt-4 flex items-center gap-1 text-[12px] text-[#7DD3FC]">
                  Open sector <ArrowRight size={12} />
                </div>
              </button>
            )
          })}
        </div>
      </section>

      <section className="relative overflow-hidden bg-gradient-to-b from-[#0A0F1C] to-[#050810] px-8 py-24 text-center">
        <div className="tl-starfield absolute inset-0 pointer-events-none" />
        <div className="relative mx-auto max-w-2xl">
          <p className="tl-serif text-[clamp(26px,4vw,40px)] font-light italic leading-[1.15] text-[#F4EFE6]">
            Eight sectors. <span className="text-[#7DD3FC]">One engine.</span>
          </p>
          <p className="mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-[#94A3B8]">
            Five are live today. Reinsurance, supply-chain and the public sector are next — the
            physical-risk primitives are already built, only the sector-specific output is new.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Btn primary onClick={onEnter}>Enter the platform <ArrowRight size={16} /></Btn>
            <Btn onClick={onHome}>Back to home</Btn>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}

// detail — one sector, top to bottom: header -> climate -> proof -> deliverables -> steps -> benefits
function SolutionsDetail({ sector, onBack, onHome, onEnter }) {
  const Icon = sector.icon

  return (
    <div className="tl-sans h-screen overflow-y-auto bg-[#0A0F1C] text-[#E8EEF7]" style={{ scrollBehavior: 'smooth' }}>
      <Nav onHome={onHome} onEnter={onEnter} onBack={onBack} />

      {/* 1 — header: icon, headline, key points */}
      <header className="mx-auto max-w-3xl px-8 pt-14 pb-4 text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[#38BDF8]/10 text-[#7DD3FC]">
          <Icon size={23} strokeWidth={1.7} />
        </span>
        <p className="tl-mono mt-4 text-[13px] font-medium uppercase tracking-[0.14em] text-[#38BDF8]">{sector.label} · {sector.tagline}</p>
        <h1 className="tl-serif mt-3 text-[clamp(30px,4.4vw,48px)] font-light italic leading-[1.1] text-[#F4EFE6]">
          {sector.headline}
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-[15.5px] leading-relaxed text-[#94A3B8]">{sector.overview}</p>
      </header>

      {/* 2 — how climate hits it */}
      <section className="mx-auto max-w-3xl px-8 py-10 text-center">
        <Eyebrow>How climate hits it</Eyebrow>
        <p className="mx-auto max-w-2xl text-[15.5px] leading-relaxed text-[#E8EEF7]">{sector.climateImpact}</p>
      </section>

      {/* 3 — real-world impact + how Tellumen helps */}
      {sector.caseStudy && (
        <section className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-16">
          <div className="mx-auto max-w-4xl px-8 text-center">
            <Eyebrow>{sector.caseStudy.eyebrow}</Eyebrow>
            <h3 className="tl-serif mx-auto max-w-2xl text-[clamp(26px,3.8vw,40px)] font-light italic leading-[1.15] text-[#F4EFE6]">
              {sector.caseStudy.title}
            </h3>
            <p className="mx-auto mt-5 max-w-2xl text-[15px] leading-relaxed text-[#94A3B8]">
              {sector.caseStudy.body}
            </p>
            <div className="mx-auto mt-8 flex max-w-md items-center justify-center gap-8 rounded-2xl border border-white/[0.09] bg-white/[0.02] px-8 py-6">
              <div className="text-center">
                <div className="tl-mono text-[24px] font-medium text-[#7DD3FC]">{sector.caseStudy.stat1[1]}</div>
                <div className="mt-1 text-[12px] font-medium uppercase tracking-wide text-[#94A3B8]">{sector.caseStudy.stat1[0]}</div>
              </div>
              <div className="h-10 w-px bg-white/[0.09]" />
              <div className="text-center">
                <div className="tl-mono text-[24px] font-medium text-[#7DD3FC]">{sector.caseStudy.stat2[1]}</div>
                <div className="mt-1 text-[12px] font-medium uppercase tracking-wide text-[#94A3B8]">{sector.caseStudy.stat2[0]}</div>
              </div>
            </div>
            <div className="mx-auto mt-8 max-w-2xl rounded-xl border-l-[3px] border-[#7DD3FC] bg-[#38BDF8]/[0.06] px-6 py-5 text-left">
              <p className="tl-mono text-[12.5px] font-semibold uppercase tracking-[0.12em] text-[#7DD3FC]">On Tellumen, this doesn’t happen blind</p>
              <p className="mt-2.5 text-[14.5px] leading-relaxed text-[#E8EEF7]">
                {sector.caseStudy.whatItMeans}
              </p>
            </div>
            <p className="mt-4 text-[11px] text-[#64748B]">{sector.caseStudy.source}</p>
          </div>
        </section>
      )}

      {/* 4 — key deliverables */}
      <section className="py-16">
        <div className="mx-auto max-w-3xl px-8 text-center">
          <Eyebrow>Key deliverables</Eyebrow>
          <h3 className="tl-serif mx-auto max-w-2xl text-[clamp(24px,3.4vw,34px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            What Tellumen delivers, out of the box.
          </h3>
          <div className="mt-9 grid gap-4 sm:grid-cols-3">
            {sector.outputs.map((o, i) => (
              <div key={o.t} className="rounded-xl border border-white/[0.09] bg-white/[0.02] p-5 text-left">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#7DD3FC] text-[12px] font-semibold text-[#0A0F1C]">{i + 1}</span>
                <h4 className="mt-3 text-[14.5px] font-medium text-[#F4EFE6]">{o.t}</h4>
                <p className="mt-1 text-[13px] leading-relaxed text-[#94A3B8]">{o.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 5 — practical steps: the flow diagram, colour-matched to sit inside the dark theme */}
      <section className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-16">
        <div className="mx-auto max-w-5xl px-8 text-center">
          <Eyebrow>Practical steps</Eyebrow>
          <h3 className="tl-serif mx-auto max-w-2xl text-[clamp(24px,3.4vw,36px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            What you send us. What we do with it. What you get back.
          </h3>

          <div className="mt-9 overflow-x-auto rounded-2xl border border-white/[0.09] bg-white/[0.015] p-1">
            <SectorFlowDiagram flow={sector.flow} />
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-6 text-[12px] text-[#94A3B8]">
            <span className="flex items-center gap-2"><span className="h-0 w-6 border-t-2 border-dashed border-[#94A3B8]" />Automatic hand-off</span>
            <span className="flex items-center gap-2"><span className="h-0 w-6 border-t-2 border-[#94A3B8]" />Computed &amp; scored</span>
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: '#2F4C86' }} />Client input</span>
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: '#147159' }} />Tellumen engine</span>
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: '#A66A26' }} />Disclosure output</span>
          </div>

          <p className="mx-auto mt-6 max-w-2xl text-[13px] leading-relaxed text-[#94A3B8]">
            <strong className="font-medium text-[#F4EFE6]">{sector.label}.</strong> {sector.flow.footer}
          </p>
        </div>
      </section>

      {/* 6 — customer benefits, closing with the CTA */}
      <section className="relative overflow-hidden bg-gradient-to-b from-[#0A0F1C] to-[#050810] px-8 py-20 text-center">
        <div className="tl-starfield absolute inset-0 pointer-events-none" />
        <div className="relative mx-auto max-w-2xl">
          <Eyebrow>How you benefit</Eyebrow>
          <ul className="mx-auto max-w-md space-y-3 text-left">
            {sector.outcomes.map(o => (
              <li key={o} className="flex items-start gap-2.5 text-[15px] text-[#E8EEF7]">
                <Check size={17} className="mt-0.5 shrink-0 text-[#7DD3FC]" strokeWidth={2.4} />
                {o}
              </li>
            ))}
          </ul>
          <div className="mt-9">
            {sector.live ? (
              <Btn primary onClick={() => onEnter(sector.id)}>See it live <ArrowRight size={16} /></Btn>
            ) : (
              <span className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-[22px] py-3.5 text-[14px] font-medium text-[#64748B]">
                <span className="h-2 w-2 rounded-full bg-[#F59E0B]" /> Coming soon
              </span>
            )}
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}

export default function SolutionsPage({ onHome, onEnter, initialSector }) {
  const [activeId, setActiveId] = useState(initialSector || null)
  const sector = activeId ? (SECTORS.find(s => s.id === activeId) || null) : null

  if (sector) {
    return <SolutionsDetail sector={sector} onBack={() => setActiveId(null)} onHome={onHome} onEnter={onEnter} />
  }
  return <SolutionsIndex onOpen={setActiveId} onHome={onHome} onEnter={onEnter} />
}
