import { useState, useEffect } from 'react'
import {
  Waves, Flame, Activity, Mountain, Umbrella as UmbrellaIcon,
  Landmark, Sprout, Building2, TrendingUp, ArrowRight,
} from 'lucide-react'
import LiveEarthHero from '../components/LiveEarthHero'
import BrandMark from '../components/BrandMark'
import { fetchScoresSummary } from '../api/client'

// Dark/editorial redesign (2026-07-05), condensed 2026-07-07 to cut scroll
// depth: Problem+Gap merged into one section, Idea+How-it-works merged into
// one section, Who's-it-for trimmed to a teaser (full detail now lives on
// /solutions). CTAs are wired to the REAL product (onEnter/onExplore/
// onLookup), not a mock -- this is a working platform, not a pitch page.

const HAZARDS = [
  { icon: Waves, name: 'Floods', desc: 'Wash away farmland and flood buildings.' },
  { icon: Flame, name: 'Wildfires', desc: 'Burn crops and destroy property fast.' },
  { icon: Activity, name: 'Earthquakes', desc: 'Shake cities with almost no warning.' },
  { icon: Mountain, name: 'Volcanoes', desc: 'Bury towns in ash or lava overnight.' },
]

const STEPS = [
  { k: 'Sense', d: 'Live data pours in from satellites, weather stations, seismic networks and volcano monitors.' },
  { k: 'Score', d: 'The engine turns raw signals into one 0–100 risk number, hazard by hazard, place by place.' },
  { k: 'Project', d: 'The same score runs forward under different climate futures — 2030, 2050, 2100.' },
  { k: 'Act', d: 'Banks, farms and insurers use the score to decide — before the disaster, not after.' },
]

const SOURCES = [
  { kind: 'Satellites', name: 'European & U.S. Government Earth-Observation Satellites', desc: 'Real-time orbital monitoring of floods, wildfires and extreme heat — refreshed daily.' },
  { kind: 'Weather & rivers', name: 'European & U.S. Government Meteorological Agencies', desc: 'Rainfall, drought and river-discharge tracking, worldwide.' },
  { kind: 'Seismic networks', name: 'European & U.S. Government Seismological Networks', desc: 'Earthquake detection worldwide, minute by minute.' },
  { kind: 'Volcano monitors', name: 'European & U.S. Government Volcanological Institutions', desc: 'Tracking every active volcano on Earth.' },
]

// Titles here are kept identical to each sector's "Key deliverables" on
// /solutions (same deliverable, same name) — only the descriptions are
// allowed to differ in phrasing between the teaser and the full page.
const AUDIENCES = [
  {
    id: 'banking', icon: Landmark, kind: 'For banks', h: 'See exactly which loans climate is coming for.',
    feats: [
      ['Command center', 'One live view of the whole loan book — every asset’s physical risk, at a glance.'],
      ['Portfolio screening', 'Every property ranked by projected risk, not guessed — sortable by risk and value.'],
      ['Regulatory reporting', 'TCFD and EU Taxonomy reports built straight from the live data — audit-ready.'],
    ],
  },
  {
    id: 'insurance', icon: UmbrellaIcon, kind: 'For insurers', h: 'Price the risk you’re actually taking on.',
    feats: [
      ['Risk pricing', 'Turns the live hazard score into a realistic, defensible premium.'],
      ['Accumulation', 'See concentration before it becomes a catastrophe.'],
      ['Parametric design', 'Automatic payouts the moment real data crosses a threshold — no lengthy claims process.'],
    ],
  },
  {
    id: 'agriculture', icon: Sprout, kind: 'For farms & food companies', h: 'Know what climate is doing to your cost of goods.',
    feats: [
      ['Sourcing book + map', 'Every farm plot you buy from, scored for heat, drought, flood and volcanic risk.'],
      ['COGS-at-risk', 'Turns climate hazard into a real euro impact on ingredients — like cocoa and coffee.'],
      ['EUDR + CSRD disclosure', 'Prove your supply chain is deforestation-free and climate-resilient, in one record.'],
    ],
  },
  {
    id: 'real-estate', icon: Building2, kind: 'For real estate', h: 'Know what climate costs your NOI — before it does.',
    feats: [
      ['Portfolio & NOI impact', 'Climate-adjusted value and NOI impact for every property you own.'],
      ['Climate-adjusted valuation', 'The same risk-based haircut schedule banks use, applied to your portfolio.'],
      ['EU Taxonomy status', 'Know which properties qualify, and why, for every holding.'],
    ],
  },
  {
    id: 'asset-management', icon: TrendingUp, kind: 'For asset managers', h: 'See portfolio climate risk the way your banks already do.',
    feats: [
      ['Portfolio climate VaR', 'Value-weighted climate exposure across the whole book, from one number.'],
      ['Screening', 'Holdings sitting in high and very-high risk zones, flagged automatically.'],
      ['EU Taxonomy eligibility', 'Per-holding taxonomy status wherever a NACE code is supplied.'],
    ],
  },
]

const PROOFS = [
  {
    badge: 'Hit · cocoa 2023/24', hit: true, title: 'Model called it — heat, not drought.',
    body: 'The model said heat drove the crash, not drought. 2024 ranks as the hottest year in our 34-year regional climate baseline (1991–2024) for the West Africa cocoa belt. Heat was right.',
    m1: ['Predicted price move', '+173%'], m2: ['Real move', '+177%'],
  },
  {
    badge: 'Partial · coffee 2021', hit: false, title: 'Right direction, missing driver.',
    body: 'The model said drought drove it, not heat. 2021 ranks as the driest year in our 34-year regional climate baseline for Brazil’s coffee belt. Predicted +27% — a frost we don’t model yet explains the rest, disclosed openly.',
    m1: ['Model share', '+27%'], m2: ['Gap disclosed', 'Frost'],
  },
  {
    badge: 'Hit · Fuego volcano 2018', hit: true, title: 'Told two neighbouring villages apart.',
    body: 'The model correctly separated the village destroyed by lava & ash flow from the nearby town that only got light ashfall — usually lumped together as "near a volcano."',
    m1: ['Resolution', 'Village-level'], m2: ['Ground truth', 'Matched'],
  },
]

function Btn({ children, onClick, href, primary }) {
  const cls = 'inline-flex items-center gap-2 rounded-lg px-[22px] py-3.5 text-[14px] font-medium transition ' +
    (primary
      ? 'bg-[#7DD3FC] text-[#0A0F1C] hover:bg-[#38BDF8]'
      : 'border border-white/10 text-[#E8EEF7] hover:border-[#7DD3FC] hover:text-[#7DD3FC] hover:bg-[#38BDF8]/5')
  if (href) return <a href={href} className={cls}>{children}</a>
  return <button onClick={onClick} className={cls}>{children}</button>
}

function Eyebrow({ children }) {
  return <span className="tl-mono mb-5 inline-block text-[13.5px] font-semibold uppercase tracking-[0.16em] text-[#38BDF8]">{children}</span>
}

export default function LandingPage({ onEnter, onExplore, onLookup }) {
  const [summary, setSummary] = useState(null)
  useEffect(() => { fetchScoresSummary().then(setSummary).catch(() => {}) }, [])

  return (
    <div className="tl-sans h-screen overflow-y-auto bg-[#0A0F1C] text-[#E8EEF7]" style={{ scrollBehavior: 'smooth' }}>
      {/* nav — fixed (not absolute) so it doesn't sit pinned-but-transparent over
          content while the page scrolls; solid blurred backdrop keeps it legible */}
      <nav className="fixed inset-x-0 top-0 z-30 flex items-center justify-between bg-[#0A0F1C]/70 px-8 py-5 backdrop-blur-md">
        <span className="tl-mono text-[12px] uppercase tracking-[0.14em] text-[#94A3B8]">Est. 2026 · Frankfurt</span>
        <div className="flex items-center gap-5 text-[13px] text-[#94A3B8]">
          <a href="#how" className="hidden hover:text-[#7DD3FC] sm:inline">How it works</a>
          <a href="#for" className="hidden hover:text-[#7DD3FC] sm:inline">Who it's for</a>
          <a href="#proof" className="hidden hover:text-[#7DD3FC] sm:inline">Proof</a>
          <button onClick={onLookup} className="hidden hover:text-[#7DD3FC] sm:inline">Check an address</button>
          <button onClick={onEnter} className="rounded-lg bg-[#7DD3FC] px-4 py-2 text-[13px] font-medium text-[#0A0F1C] hover:bg-[#38BDF8]">Enter the platform</button>
        </div>
      </nav>

      {/* hero */}
      <LiveEarthHero height="100vh" showCaption={false} showBadge={false}>
        <div className="tl-starfield absolute inset-0 pointer-events-none" />
        <div className="relative">
          <div className="flex items-center justify-center gap-3">
            <BrandMark size={44} />
            <h1 className="tl-serif text-[clamp(52px,8vw,96px)] font-light italic leading-none text-[#F4EFE6]">Tel<span className="text-[#7DD3FC]">lumen</span></h1>
          </div>
          <div className="tl-mono mt-3 text-[12px] uppercase tracking-[0.24em] text-[#38BDF8] opacity-85">Light on the Earth</div>

          <p className="tl-serif mx-auto mt-14 max-w-3xl text-[clamp(28px,4.2vw,48px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            See what's coming. <span className="text-[#7DD3FC]">Any place on Earth.</span>
          </p>
          <p className="mx-auto mt-6 max-w-xl text-[16px] leading-relaxed text-[#94A3B8]">
            Tellumen turns live satellite and sensor data into one simple number that tells you how
            safe — or how risky — any place on the planet is, right now and in the future.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Btn primary onClick={onLookup}>Check an address <ArrowRight size={16} /></Btn>
            <Btn onClick={onExplore}>Explore solutions</Btn>
          </div>
        </div>
      </LiveEarthHero>

      {/* the gap — problem + siloed-data gap, merged into one compact section */}
      <section id="problem" className="mx-auto max-w-4xl px-8 py-14">
        <Eyebrow>The gap</Eyebrow>
        <h2 className="tl-serif max-w-3xl text-[clamp(26px,3.6vw,40px)] font-light italic leading-[1.1] text-[#F4EFE6]">
          Disasters don't send a warning email — and the data to see them coming is scattered.
        </h2>
        <p className="mt-4 max-w-2xl text-[14.5px] leading-relaxed text-[#94A3B8]">
          Floods, wildfires, earthquakes, volcanoes hit banks, farms and insurers without warning. A flood map
          here, a weather model there, an earthquake catalog somewhere else — each real, none connected, none
          tied to what you actually own or grow. The result: climate risk has stayed invisible until it's too late.
        </p>
        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {HAZARDS.map(h => (
            <div key={h.name} className="flex items-center gap-3 rounded-xl border border-white/[0.09] bg-white/[0.02] p-4 transition hover:border-[#38BDF8]/30 hover:bg-[#38BDF8]/[0.04]">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-[#38BDF8]/10 text-[#7DD3FC]"><h.icon size={17} /></span>
              <div className="text-[14px] font-medium text-[#F4EFE6]">{h.name}</div>
            </div>
          ))}
        </div>
      </section>

      {/* how it works — one score visual + the 4-step loop, merged */}
      <section id="how" className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-14 text-center">
        <div className="mx-auto max-w-4xl px-8">
          <Eyebrow>How it works</Eyebrow>
          <h2 className="tl-serif mx-auto max-w-3xl text-[clamp(26px,3.6vw,40px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            One engine reads all of it. One score, 0 to 100.
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-[14.5px] leading-relaxed text-[#94A3B8]">
            Point Tellumen at any spot on Earth and it reads live satellite, weather, earthquake and volcano
            data — low is calm, high is real danger. Run it today, or fast-forward to 2030, 2050 or 2100.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <span className="tl-serif text-[clamp(48px,7vw,80px)] font-light italic leading-[0.9] text-[#F4EFE6]">0</span>
            <span className="tl-mono text-[13px] uppercase tracking-[0.22em] text-[#94A3B8]">to</span>
            <span className="tl-serif text-[clamp(48px,7vw,80px)] font-light italic leading-[0.9] text-[#EF4444]">100</span>
            <div className="tl-mono ml-2 flex flex-wrap gap-2 text-[11px] text-[#94A3B8]">
              <span className="rounded-full border border-[#34D399]/35 px-2 py-1 text-[#34D399]">calm</span>
              <span className="rounded-full border border-[#F59E0B]/35 px-2 py-1 text-[#F59E0B]">watch</span>
              <span className="rounded-full border border-[#EF4444]/35 px-2 py-1 text-[#EF4444]">danger</span>
            </div>
          </div>

          <div className="mt-9 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.k} className="rounded-xl border border-white/[0.09] bg-white/[0.02] p-4 text-left">
                <div className="flex items-baseline gap-2">
                  <span className="tl-serif text-[26px] italic font-light leading-none text-[#7DD3FC]">{String(i + 1).padStart(2, '0')}</span>
                  <span className="tl-mono text-[13px] font-semibold uppercase tracking-[0.14em] text-[#F4EFE6]">{s.k}</span>
                </div>
                <div className="mt-2 text-[12.5px] leading-relaxed text-[#94A3B8]">{s.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* data */}
      <section id="data" className="py-11">
        <div className="mx-auto max-w-4xl px-8">
          <Eyebrow>The data</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(24px,3.2vw,34px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            Real feeds. From real space agencies.
          </h2>
          <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-[#94A3B8]">
            Nothing here is guessed or simulated — every score traces to a live public data source.
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {SOURCES.map(s => (
              <div key={s.kind} className="rounded-xl border border-white/[0.09] bg-white/[0.02] p-4">
                <div className="tl-mono mb-1.5 text-[12px] font-medium uppercase tracking-[0.14em] text-[#38BDF8]">{s.kind}</div>
                <div className="text-[15px] font-medium text-[#F4EFE6]">{s.name}</div>
                <div className="mt-1 text-[13px] leading-relaxed text-[#94A3B8]">{s.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* for who — compact teaser; full detail lives on /solutions */}
      <section id="for" className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-14">
        <div className="mx-auto max-w-5xl px-8">
          <Eyebrow>Who it's for</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(26px,3.6vw,40px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            Five sectors live today. Same live score. Different decisions.
          </h2>
          <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-[#94A3B8]">
            Everyone else picks one hazard, one industry. We read every hazard, into every industry, from the
            same score — five sectors live now, three more on the roadmap.
          </p>
          <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {AUDIENCES.map(a => (
              <button key={a.kind} onClick={() => onExplore(a.id)}
                className="flex items-center gap-3.5 rounded-xl border border-white/[0.09] bg-white/[0.02] p-4.5 text-left transition hover:border-[#38BDF8]/35 hover:bg-[#38BDF8]/[0.03]">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#38BDF8]/10 text-[#7DD3FC]"><a.icon size={17} /></span>
                <div>
                  <div className="tl-mono text-[12px] font-medium uppercase tracking-[0.14em] text-[#38BDF8]">{a.kind}</div>
                  <div className="mt-0.5 text-[14px] font-medium leading-snug text-[#F4EFE6]">{a.h}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* differentiation */}
      <section className="py-11">
        <div className="mx-auto max-w-4xl px-8">
          <Eyebrow>Why nothing else in the EU does this</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(24px,3.2vw,34px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            Everyone else picks one thing. We do all of it.
          </h2>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-[#94A3B8]/20 bg-[#94A3B8]/[0.06] p-5">
              <div className="tl-mono mb-2.5 text-[12px] font-medium uppercase tracking-[0.14em] text-[#64748B]">Other tools</div>
              <div className="tl-serif text-[17px] italic font-light leading-snug text-[#94A3B8]">One hazard, one industry at a time.</div>
            </div>
            <div className="rounded-xl border border-[#38BDF8]/35 bg-gradient-to-br from-[#38BDF8]/10 to-[#34D399]/5 p-5">
              <div className="tl-mono mb-2.5 text-[12px] font-medium uppercase tracking-[0.14em] text-[#7DD3FC]">Tellumen</div>
              <div className="tl-serif text-[17px] italic font-light leading-snug text-[#F4EFE6]">Every hazard, every industry, one engine.</div>
            </div>
          </div>
        </div>
      </section>

      {/* proof */}
      <section id="proof" className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-14">
        <div className="mx-auto max-w-5xl px-8">
          <Eyebrow>Proof, not promises</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(26px,3.6vw,40px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            We test our model against real disasters — misses included.
          </h2>
          <p className="mt-4 max-w-2xl text-[14.5px] leading-relaxed text-[#94A3B8]">
            Before we trust a number, we check it against something that already happened. When we're wrong, we say so.
          </p>
          <div className="mt-8 grid gap-4 lg:grid-cols-3">
            {PROOFS.map(p => (
              <div key={p.badge} className="rounded-xl border border-white/[0.09] bg-white/[0.02] p-5">
                <span className={`tl-mono mb-3 inline-block rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.12em] ${p.hit ? 'bg-[#34D399]/10 text-[#34D399]' : 'bg-[#F59E0B]/10 text-[#F59E0B]'}`}>
                  {p.badge}
                </span>
                <div className="tl-serif mb-2.5 text-[18px] italic font-light leading-snug text-[#F4EFE6]">{p.title}</div>
                <p className="text-[13px] leading-relaxed text-[#94A3B8]">{p.body}</p>
                <div className="tl-mono mt-3 flex gap-4 border-t border-white/[0.09] pt-3 text-[11.5px] text-[#94A3B8]">
                  <span>{p.m1[0]} <b className="ml-1 font-medium text-[#7DD3FC]">{p.m1[1]}</b></span>
                  <span>{p.m2[0]} <b className="ml-1 font-medium text-[#7DD3FC]">{p.m2[1]}</b></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* closing + footer, merged into one compact band */}
      <section className="relative overflow-hidden bg-gradient-to-b from-[#0A0F1C] to-[#050810] px-8 py-14 text-center">
        <div className="tl-starfield absolute inset-0 pointer-events-none" />
        <div className="relative">
          <p className="tl-serif mx-auto max-w-2xl text-[clamp(26px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            The next disaster <span className="text-[#7DD3FC]">won't be invisible.</span>
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <Btn primary onClick={onExplore}>Explore solutions <ArrowRight size={16} /></Btn>
            <Btn onClick={onEnter}>Enter the platform</Btn>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/[0.09] px-8 py-8 text-center">
        <span className="tl-mono text-[11px] tracking-[0.10em] text-[#64748B]">
          © 2026 Tellumen. Every number traces back to a live public data source.
          {summary?.total_current_scores ? ` · ${summary.total_current_scores.toLocaleString()} risk scores live right now.` : ''}
        </span>
      </footer>
    </div>
  )
}
