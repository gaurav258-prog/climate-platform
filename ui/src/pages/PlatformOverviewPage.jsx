import { useState, useEffect } from 'react'
import {
  Landmark, Umbrella, Sprout, Layers, TrendingUp, Building, Truck, Building2,
  ArrowRight, Satellite, Cpu, ShieldCheck, RefreshCw, GitBranch, Lock,
} from 'lucide-react'
import { INDUSTRIES, PROCESSING_CHAIN } from '../data/industries'
import { fetchScoresSummary } from '../api/client'
import LiveEarthHero from '../components/LiveEarthHero'

const ICONS = {
  landmark: Landmark, umbrella: Umbrella, sprout: Sprout, layers: Layers,
  'trending-up': TrendingUp, building: Building, truck: Truck, 'building-community': Building2,
}

const STAGE_ICONS = [Satellite, Cpu, Cpu, GitBranch, ArrowRight]

export default function PlatformOverviewPage({ onSelectIndustry }) {
  const [summary, setSummary] = useState(null)
  useEffect(() => {
    let alive = true
    fetchScoresSummary().then(d => alive && setSummary(d)).catch(() => {})
    return () => { alive = false }
  }, [])

  const liveScores = summary?.total_current_scores
  const hazardsLive = summary?.hazards_live || []

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      {/* Hero — live Earth from the ISS */}
      <LiveEarthHero>
        <p className="text-[11px] uppercase tracking-[0.25em] text-white/70 mb-3">Climate Intelligence Platform</p>
        <h1 className="text-5xl md:text-6xl font-light leading-tight text-white drop-shadow-[0_2px_20px_rgba(0,0,0,0.5)]">
          One climate-risk engine.<br /><span className="text-sky-300">Every sector.</span>
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-white/85 drop-shadow-[0_1px_10px_rgba(0,0,0,0.6)]">
          We turn live satellite and climate data — like the Earth you're watching now, streamed from the ISS —
          into one auditable risk score per location. Every industry reads that same golden source.
        </p>
      </LiveEarthHero>

      {/* 1 · DATA STORY */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="01" title="The data" sub="Three decades, one grid" />
        <div className="grid sm:grid-cols-4 gap-4 mt-6">
          <Stat big="51.4M" label="satellite observations" />
          <Stat big="1998–2026" label="28 years of history" />
          <Stat big="H3 res-8" label="~0.7 km² cells, EU" />
          <Stat big="append-only" label="immutable golden source" />
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-6 mt-6">
          <p className="text-gray-800 leading-relaxed">
            Every feed lands in one place through a provider-abstraction layer, keyed to the H3 hexagonal grid — so the
            platform never cares which satellite produced a reading, only where and when. Sources include ERA5 reanalysis
            (temperature, precipitation, soil moisture, wind, runoff), GloFAS hydrology, NASA FIRMS fire detection, and
            EMSC/ESHM seismic catalogs.
          </p>
          <div className="flex flex-wrap gap-2 mt-4">
            {['ERA5', 'GloFAS', 'NASA FIRMS', 'Sentinel-1 SAR', 'Sentinel-3', 'EMSC', 'ESHM20'].map(s => (
              <span key={s} className="text-xs bg-gray-100 text-gray-700 rounded-full px-3 py-1">{s}</span>
            ))}
          </div>
        </div>
      </section>

      {/* 2 · PROCESSING STORY */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="02" title="The processing" sub="From raw pixels to one 0–100 score" />
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

      {/* 3 · WHY US */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="03" title="Why customers stay current with us" sub="Always the latest, always auditable" />
        <div className="grid sm:grid-cols-2 gap-4 mt-6">
          <Why icon={RefreshCw} title="Near-real-time, never stale"
            body="New observations flow straight to scores. Each cell carries 6h/24h/48h velocity, so customers see risk rising before it lands — not in next quarter's report." />
          <Why icon={Lock} title="Append-only golden source"
            body="Scores are immutable. A new score retires the old one with a timestamp; nothing is overwritten. Today's number and last week's both stand, fully reproducible." />
          <Why icon={ShieldCheck} title="Audit-grade traceability"
            body="Every score records its model version, data vintage and a SHA-256 fingerprint of its inputs — the evidence regulators and reinsurers ask for." />
          <Why icon={GitBranch} title="One source, every sector"
            body="Banking, insurance and agriculture read the exact same canonical score. Add a sector and you add a layer, not a pipeline — so everyone is always on the same truth." />
        </div>
      </section>

      {/* 4 · INDUSTRIES GRID */}
      <section className="max-w-6xl mx-auto px-8 py-12">
        <SectionLabel n="04" title="Industry modules" sub="Same engine, sector-specific output" />
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
          {INDUSTRIES.map(ind => {
            const Icon = ICONS[ind.icon] || Landmark
            const built = ind.status === 'built'
            return (
              <button key={ind.id} onClick={() => onSelectIndustry(ind.id)}
                className="text-left bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md hover:border-indigo-300 transition-all">
                <div className="flex items-center justify-between mb-3">
                  <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center"><Icon size={20} strokeWidth={1.5} /></div>
                  <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full ${built ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-500'}`}>{built ? 'Live' : 'Roadmap'}</span>
                </div>
                <p className="font-medium text-gray-900">{ind.name}</p>
                <p className="text-xs text-gray-500 mt-1 leading-snug">{ind.tagline}</p>
                <p className="text-xs text-indigo-600 mt-3 flex items-center gap-1">Open module <ArrowRight size={12} /></p>
              </button>
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
