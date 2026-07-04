import { useState, useEffect } from 'react'
import {
  Satellite, Cpu, ShieldCheck, GitBranch, Activity, TrendingUp, ScrollText, Layers,
  Landmark, Umbrella, Sprout, Building2, ArrowRight,
} from 'lucide-react'
import LiveEarthHero from '../components/LiveEarthHero'
import BrandMark from '../components/BrandMark'
import { fetchScoresSummary } from '../api/client'

const SOURCES = ['Copernicus ERA5', 'GloFAS', 'NASA FIRMS', 'Sentinel', 'EMSC · USGS', 'Sen · ISS']

// Why this matters — outward-facing, the customer's problem, not our plumbing.
const WHY = [
  { icon: TrendingUp, t: 'The exposure is real', d: 'Floods, wildfires and earthquakes are hitting assets, collateral and supply chains with rising frequency — and it lands on your balance sheet.' },
  { icon: ScrollText, t: 'The rules have arrived', d: 'TCFD, EU Taxonomy and CSRD now require forward-looking, location-specific climate risk in what you report and disclose.' },
  { icon: Layers, t: 'The data is scattered', d: 'It sits across dozens of agencies and formats. We bring it into one current, comparable, decision-ready view of your world.' },
]

const STEPS = [
  { icon: Satellite, k: 'Sense', t: 'Live from orbit', d: 'Near-real-time satellite, weather and seismic data — everywhere on Earth, always current.' },
  { icon: Cpu, k: 'Understand', t: 'Scored by the engine', d: 'We fuse it into one clear 0–100 risk per hazard, for any location you care about.' },
  { icon: ShieldCheck, k: 'Trust', t: 'Current & auditable', d: 'Every number is timestamped and traceable to its source — so you can put your name to it.' },
  { icon: GitBranch, k: 'Act', t: 'Built into decisions', d: 'Each industry turns the same risk picture into pricing, disclosure and action.' },
]

const PILLARS = [
  { icon: Layers, t: 'One number, everywhere', d: 'The same risk read by every team and every sector — no two people working off different maps.' },
  { icon: ShieldCheck, t: 'Honest about uncertainty', d: 'We test our scores against what actually happened, and show plainly where we’re confident and where we’re not.' },
  { icon: GitBranch, t: 'Traceable end to end', d: 'Every figure carries its source and date — audit-ready by design, not as an afterthought.' },
]

const SECTORS = [
  { icon: Landmark, t: 'Banking', d: 'Physical-risk disclosure and portfolio value-at-risk for loan books.', live: true },
  { icon: Umbrella, t: 'Insurance', d: 'Loss-curve pricing and parametric triggers on live hazard data.' },
  { icon: Sprout, t: 'Agriculture', d: 'Yield-at-risk and resilience across growing regions.' },
  { icon: Building2, t: 'And more', d: 'Real estate, energy, logistics, the public sector — same engine.' },
]

function Btn({ children, onClick, primary, dark }) {
  const base = 'inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-[14px] font-medium transition'
  const style = primary
    ? { background: '#0071e3', color: '#fff' }
    : dark
      ? { background: 'rgba(255,255,255,0.14)', color: '#fff', border: '1px solid rgba(255,255,255,0.25)' }
      : { background: '#fff', color: '#1d1d1f', border: '1px solid #e5e7eb' }
  return <button onClick={onClick} className={base} style={style}>{children}</button>
}

export default function LandingPage({ onEnter, onExplore, onLookup }) {
  const [summary, setSummary] = useState(null)
  useEffect(() => { fetchScoresSummary().then(setSummary).catch(() => {}) }, [])
  const liveScores = summary?.total_current_scores
  const hazards = summary?.hazards?.length

  return (
    <div className="h-screen overflow-y-auto bg-white text-[#1d1d1f]" style={{ scrollBehavior: 'smooth' }}>
      {/* nav */}
      <nav className="absolute inset-x-0 top-0 z-30 flex items-center justify-between px-8 py-4">
        <div className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-white"><BrandMark size={28} /><span>Tel<span className="text-sky-300">lumen</span></span></div>
        <div className="flex items-center gap-2">
          <button onClick={onExplore} className="hidden rounded-full px-4 py-2 text-[13px] font-medium text-white/85 hover:text-white sm:inline">Solutions</button>
          <a href="#how" className="hidden rounded-full px-4 py-2 text-[13px] font-medium text-white/85 hover:text-white sm:inline">How it works</a>
          <button onClick={onLookup} className="hidden rounded-full px-4 py-2 text-[13px] font-medium text-white/85 hover:text-white sm:inline">Check an address</button>
          <button onClick={onEnter} className="rounded-full bg-white px-4 py-2 text-[13px] font-medium text-[#1d1d1f]">Enter the platform</button>
        </div>
      </nav>

      {/* hero */}
      <LiveEarthHero height="92vh" showCaption={false}>
        <h1 className="text-5xl font-light leading-[1.05] text-white drop-shadow-[0_2px_24px_rgba(0,0,0,0.55)] md:text-7xl">
          One score. Every disaster.<br /><span className="text-sky-300">Any place on Earth.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-white/85 drop-shadow-[0_1px_12px_rgba(0,0,0,0.6)]">
          Tellumen turns live satellite and sensor data into one simple number that tells you how
          safe — or how risky — any place on the planet is, right now and in the future.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Btn primary onClick={onLookup}>Check an address <ArrowRight size={16} /></Btn>
          <Btn dark onClick={onExplore}>Explore solutions</Btn>
          <Btn dark onClick={onEnter}>Enter the platform</Btn>
        </div>
      </LiveEarthHero>

      {/* trust strip */}
      <section className="border-b border-gray-200 bg-[#f5f5f7] py-7">
        <p className="text-center text-[11px] uppercase tracking-[0.18em] text-gray-400">Built on the world’s primary climate data</p>
        <div className="mx-auto mt-4 flex max-w-4xl flex-wrap items-center justify-center gap-x-8 gap-y-3 px-6 text-[14px] font-medium text-gray-500">
          {SOURCES.map(s => <span key={s}>{s}</span>)}
        </div>
      </section>

      {/* why now — the customer's problem */}
      <section className="mx-auto max-w-5xl px-8 py-20">
        <p className="text-center text-xs font-medium uppercase tracking-[0.15em] text-gray-400">Why now</p>
        <h2 className="mt-2 text-center text-4xl font-semibold tracking-tight">Climate risk is now a business number.</h2>
        <p className="mx-auto mt-3 max-w-2xl text-center text-[16px] text-gray-500">
          It affects what you lend, insure, grow and build — and what you’re required to report.
        </p>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {WHY.map(w => (
            <div key={w.t} className="rounded-2xl border border-gray-200/70 bg-white p-6 shadow-sm">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0071e3]/10 text-[#0071e3]"><w.icon size={19} /></span>
              <h3 className="mt-3 text-[17px] font-semibold">{w.t}</h3>
              <p className="mt-1.5 text-[14px] leading-relaxed text-gray-500">{w.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="bg-[#f5f5f7] py-20">
        <div className="mx-auto max-w-5xl px-8">
          <p className="text-center text-xs font-medium uppercase tracking-[0.15em] text-gray-400">How it works</p>
          <h2 className="mt-2 text-center text-4xl font-semibold tracking-tight">From orbit to decision</h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-[16px] text-gray-500">Four steps, one continuous flow — always current.</p>
          <div className="mt-12 grid gap-5 md:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.k} className="relative rounded-2xl bg-white p-5 shadow-sm">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0071e3]/10 text-[#0071e3]"><s.icon size={19} /></span>
                <div className="mt-3 text-[11px] font-medium uppercase tracking-wide text-gray-400">{i + 1} · {s.k}</div>
                <h3 className="mt-0.5 text-[16px] font-semibold">{s.t}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-gray-500">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* why us */}
      <section className="mx-auto max-w-5xl px-8 py-20">
        <h2 className="text-center text-4xl font-semibold tracking-tight">Numbers you can put your name to</h2>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {PILLARS.map(p => (
            <div key={p.t} className="rounded-2xl border border-gray-200/70 bg-white p-6 shadow-sm">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 text-[#1d1d1f]"><p.icon size={19} /></span>
              <h3 className="mt-3 text-[17px] font-semibold">{p.t}</h3>
              <p className="mt-1.5 text-[14px] leading-relaxed text-gray-500">{p.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* live proof */}
      <section className="mx-auto max-w-5xl px-8 pb-20">
        <div className="rounded-3xl bg-[#04070f] px-8 py-12 text-center text-white">
          <p className="flex items-center justify-center gap-2 text-[12px] font-medium text-emerald-400">
            <Activity size={14} /> live right now
          </p>
          <div className="mt-6 grid gap-6 sm:grid-cols-3">
            <Stat v={liveScores ? liveScores.toLocaleString() : '—'} l="risk scores live across the globe" />
            <Stat v={hazards || '3'} l="hazards scored · flood, wildfire, seismic" />
            <Stat v="daily" l="forecasts checked against reality" />
          </div>
          <p className="mx-auto mt-8 max-w-xl text-[15px] text-white/70">
            We even publish where our models and reality diverge — because a risk number you can’t audit
            isn’t one you can disclose.
          </p>
        </div>
      </section>

      {/* sectors → solutions */}
      <section className="bg-[#f5f5f7] py-20">
        <div className="mx-auto max-w-5xl px-8">
          <p className="text-center text-xs font-medium uppercase tracking-[0.15em] text-gray-400">Built for</p>
          <h2 className="mt-2 text-center text-4xl font-semibold tracking-tight">One engine, every sector</h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-[16px] text-gray-500">
            The same live risk picture, shaped to how your industry actually works.
          </p>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {SECTORS.map(s => (
              <button key={s.t} onClick={onExplore}
                className="group rounded-2xl border border-gray-200/70 bg-white p-5 text-left shadow-sm transition hover:border-gray-300 hover:shadow">
                <div className="flex items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 text-[#1d1d1f]"><s.icon size={19} /></span>
                  {s.live
                    ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">live</span>
                    : <ArrowRight size={15} className="text-gray-300 transition group-hover:text-[#0071e3]" />}
                </div>
                <h3 className="mt-3 text-[16px] font-semibold">{s.t}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-gray-500">{s.d}</p>
              </button>
            ))}
          </div>
          <div className="mt-10 flex justify-center">
            <Btn primary onClick={onExplore}>Explore all solutions <ArrowRight size={16} /></Btn>
          </div>
        </div>
      </section>

      {/* final CTA */}
      <section className="mx-auto max-w-5xl px-8 py-24 text-center">
        <h2 className="text-5xl font-semibold tracking-tight">See your world, right now.</h2>
        <p className="mx-auto mt-4 max-w-xl text-[17px] text-gray-500">
          Every asset, every hazard, every scenario — projected live, in one place.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Btn primary onClick={onExplore}>Explore solutions <ArrowRight size={16} /></Btn>
          <Btn onClick={onEnter}>Enter the platform</Btn>
        </div>
      </section>

      <footer className="border-t border-gray-200 px-8 py-8 text-center text-[12px] text-gray-400">
        Tellumen — Light on the Earth · one engine, every sector · view powered by Sen
      </footer>
    </div>
  )
}

function Stat({ v, l }) {
  return (
    <div>
      <div className="text-4xl font-semibold tracking-tight">{v}</div>
      <div className="mt-1 text-[13px] text-white/60">{l}</div>
    </div>
  )
}
