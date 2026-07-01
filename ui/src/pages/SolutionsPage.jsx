import { useState } from 'react'
import {
  Landmark, Umbrella, Sprout, Building2, Zap,
  ArrowRight, ArrowLeft, Check,
} from 'lucide-react'

// Outward-facing solutions catalogue. One engine, many industries.
// Banking is live (launches the product); the rest carry a full value
// proposition and a tasteful "Coming soon".
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
  },
  {
    id: 'insurance', label: 'Insurance', icon: Umbrella, live: false,
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
  },
  {
    id: 'agriculture', label: 'Agriculture', icon: Sprout, live: false,
    tagline: 'Yield-at-risk across growing regions',
    headline: 'Protect yield, supply and margins.',
    narrative:
      'Track climate stress across growing regions and supply sheds — heat, drought, flood — so you can anticipate yield shortfalls, secure sourcing, and price crop risk before the season turns.',
    outcomes: [
      'Yield-at-risk by region & crop',
      'Drought and heat-stress monitoring',
      'Supply-chain resilience mapping',
      'Season-ahead early warning',
    ],
    outputs: [
      { t: 'Region monitor', d: 'Live climate stress across your footprint.' },
      { t: 'Yield risk', d: 'Exposure broken down by crop and geography.' },
      { t: 'Sourcing resilience', d: 'Spot fragile supply sheds early.' },
    ],
  },
  {
    id: 'real-estate', label: 'Real Estate', icon: Building2, live: false,
    tagline: 'Asset resilience & site selection',
    headline: 'Buy, build and hold with eyes open.',
    narrative:
      'Screen individual properties and whole portfolios for physical climate risk before you acquire, develop or refinance — and evidence the resilience of what you hold to lenders and investors.',
    outcomes: [
      'Property & portfolio risk screening',
      'Site-selection due diligence',
      'Resilience reporting for lenders',
      'Forward-looking scenario exposure',
    ],
    outputs: [
      { t: 'Asset screening', d: 'Risk on any address in seconds.' },
      { t: 'Due diligence', d: 'Climate risk inside the acquisition workflow.' },
      { t: 'Investor reporting', d: 'Resilience, evidenced.' },
    ],
  },
  {
    id: 'energy', label: 'Energy', icon: Zap, live: false,
    tagline: 'Infrastructure exposure & continuity',
    headline: 'Keep critical infrastructure running.',
    narrative:
      'Map physical climate hazard across generation, grid and network assets to prioritise hardening, plan for extremes, and keep the lights on as conditions shift.',
    outcomes: [
      'Network-wide hazard exposure',
      'Asset-hardening prioritisation',
      'Extreme-event preparedness',
      'Continuity & resilience planning',
    ],
    outputs: [
      { t: 'Network map', d: 'Hazard across every asset you operate.' },
      { t: 'Prioritisation', d: 'Where to harden first — by risk × value.' },
      { t: 'Preparedness', d: 'Plan for the events that actually matter.' },
    ],
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
          Climate <span className="text-[#0071e3]">Intelligence</span>
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
        <div className="mx-auto flex max-w-5xl items-center gap-1 overflow-x-auto px-6 py-2">
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
                <button onClick={onEnter}
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

      {/* and more */}
      <section className="border-t border-gray-200 bg-[#f5f5f7] py-14">
        <div className="mx-auto max-w-3xl px-8 text-center">
          <h3 className="text-2xl font-semibold tracking-tight">And beyond these five.</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-gray-500">
            Logistics, telecoms, the public sector, supply-chain and asset management — any business
            that lives with a physical footprint reads the same engine. If your world isn’t here yet,
            it’s on the roadmap.
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
        Climate Intelligence · one engine, every sector · Earth view powered by Sen
      </footer>
    </div>
  )
}
