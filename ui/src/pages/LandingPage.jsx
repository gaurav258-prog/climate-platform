import { useState, useEffect } from 'react'
import {
  Waves, Flame, Activity, Mountain, Umbrella as UmbrellaIcon,
  Landmark, Sprout, ArrowRight,
} from 'lucide-react'
import LiveEarthHero from '../components/LiveEarthHero'
import BrandMark from '../components/BrandMark'
import { fetchScoresSummary } from '../api/client'

// Dark/editorial redesign (2026-07-05), following the pptx explainer deck's
// narrative arc 1:1 (Problem -> Gap -> Idea -> How -> Data -> For Who ->
// Differentiation -> Proof -> Closing) -- see docs snapshot
// ~/Documents/TELLUMEN_LANDING.html for the source mock. CTAs are wired to
// the REAL product (onEnter/onExplore/onLookup), not the mock's mailto
// placeholders -- this is a working platform, not a pre-launch pitch page.

const HAZARDS = [
  { icon: Waves, name: 'Floods', desc: 'Wash away farmland and flood buildings.' },
  { icon: Flame, name: 'Wildfires', desc: 'Burn crops and destroy property fast.' },
  { icon: Activity, name: 'Earthquakes', desc: 'Shake cities with almost no warning.' },
  { icon: Mountain, name: 'Volcanoes', desc: 'Bury towns in ash or lava overnight.' },
]

const ISLANDS = ['Flood agencies', 'Weather services', 'Seismic networks', 'Volcano observatories']

const STEPS = [
  { k: 'Sense', d: 'Live data pours in from satellites, weather stations, seismic networks and volcano monitors.' },
  { k: 'Score', d: 'The engine turns raw signals into one 0–100 risk number, hazard by hazard, place by place.' },
  { k: 'Project', d: 'The same score runs forward under different climate futures — 2030, 2050, 2100.' },
  { k: 'Act', d: 'Banks, farms and insurers use the score to decide — before the disaster, not after.' },
]

const SOURCES = [
  { kind: 'Satellites', name: 'Copernicus Sentinel + NASA FIRMS', desc: 'Watching floods, fires and heat from orbit. Refreshed daily.' },
  { kind: 'Weather & rivers', name: 'Copernicus ERA5 & GloFAS', desc: 'Tracking rainfall, drought and river discharge worldwide.' },
  { kind: 'Seismic networks', name: 'EMSC & USGS', desc: 'Listening for earthquakes worldwide, minute by minute.' },
  { kind: 'Volcano monitors', name: 'Smithsonian Global Volcanism Program', desc: 'Tracking every active volcano on Earth.' },
]

const AUDIENCES = [
  {
    icon: Landmark, kind: 'For banks', h: 'See exactly which loans climate is coming for.',
    feats: [
      ['Command center', 'One live view of the whole loan book — every asset’s physical risk, at a glance.'],
      ['Portfolio screening', 'Every property ranked by projected risk, not guessed — sortable by risk and value.'],
      ['Regulatory disclosure', 'TCFD and EU Taxonomy reports built straight from the live data — audit-ready.'],
    ],
  },
  {
    icon: Sprout, kind: 'For farms & food companies', h: 'Know what climate is doing to your cost of goods.',
    feats: [
      ['Sourcing book', 'Every farm plot you buy from, scored for heat, drought, flood and volcanic risk.'],
      ['COGS-at-risk', 'Turns climate hazard into a real euro impact on ingredients — like cocoa and coffee.'],
      ['EUDR-ready', 'Prove your supply chain is deforestation-free and climate-resilient, in one record.'],
    ],
  },
  {
    icon: UmbrellaIcon, kind: 'For insurers', h: 'Price the risk you’re actually taking on.',
    feats: [
      ['Loss-curve pricing', 'Turns the live hazard score into a realistic, defensible premium.'],
      ['Parametric triggers', 'Automatic payouts the moment real data crosses a threshold — no lengthy claims process.'],
      ['One shared view', 'Underwriters and claims teams look at the exact same live number, always in sync.'],
    ],
  },
]

const PROOFS = [
  {
    badge: 'Hit · cocoa 2023/24', hit: true, title: 'Model called it — heat, not drought.',
    body: 'The model said heat drove the crash, not drought. 2024 was the hottest year in 34. Heat was right.',
    m1: ['Predicted price move', '+173%'], m2: ['Real move', '+177%'],
  },
  {
    badge: 'Partial · coffee 2021', hit: false, title: 'Right direction, missing driver.',
    body: 'The model said drought drove it, not heat. 2021 was the driest year in 34. Predicted +27% — a frost we don’t model yet explains the rest, disclosed openly.',
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
  return <span className="tl-mono mb-5 inline-block text-[11px] font-medium uppercase tracking-[0.22em] text-[#38BDF8]">{children}</span>
}

export default function LandingPage({ onEnter, onExplore, onLookup }) {
  const [summary, setSummary] = useState(null)
  useEffect(() => { fetchScoresSummary().then(setSummary).catch(() => {}) }, [])

  return (
    <div className="tl-sans h-screen overflow-y-auto bg-[#0A0F1C] text-[#E8EEF7]" style={{ scrollBehavior: 'smooth' }}>
      {/* nav — fixed (not absolute) so it doesn't sit pinned-but-transparent over
          content while the page scrolls; solid blurred backdrop keeps it legible */}
      <nav className="fixed inset-x-0 top-0 z-30 flex items-center justify-between bg-[#0A0F1C]/70 px-8 py-5 backdrop-blur-md">
        <span className="tl-mono text-[11px] uppercase tracking-[0.14em] text-[#94A3B8]">Est. 2026 · Berlin</span>
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
            <h1 className="tl-serif text-[clamp(52px,8vw,96px)] font-light italic leading-none text-[#F4EFE6]">Tellumen</h1>
          </div>
          <div className="tl-mono mt-3 text-[12px] uppercase tracking-[0.24em] text-[#38BDF8] opacity-85">Light on the Earth</div>

          <p className="tl-serif mx-auto mt-14 max-w-3xl text-[clamp(28px,4.2vw,48px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            One score. Every disaster. <span className="text-[#7DD3FC]">Any place on Earth.</span>
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

      {/* problem */}
      <section id="problem" className="mx-auto max-w-4xl px-8 py-28">
        <Eyebrow>The problem</Eyebrow>
        <h2 className="tl-serif max-w-3xl text-[clamp(28px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
          Disasters don't send a warning email.
        </h2>
        <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-[#94A3B8]">
          Floods, wildfires, earthquakes, volcanoes — they hit banks, farms and insurers without warning, anywhere in the world.
        </p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {HAZARDS.map(h => (
            <div key={h.name} className="rounded-xl border border-white/[0.09] bg-white/[0.02] p-6 transition hover:border-[#38BDF8]/30 hover:bg-[#38BDF8]/[0.04]">
              <span className="mb-3.5 flex h-11 w-11 items-center justify-center rounded-[10px] bg-[#38BDF8]/10 text-[#7DD3FC]"><h.icon size={20} /></span>
              <div className="mb-1.5 text-[16px] font-medium text-[#F4EFE6]">{h.name}</div>
              <div className="text-[13.5px] leading-relaxed text-[#94A3B8]">{h.desc}</div>
            </div>
          ))}
        </div>
        <div className="mt-10 rounded-r-xl border-l-[3px] border-[#EF4444] bg-gradient-to-r from-[#EF4444]/[0.06] to-[#F59E0B]/[0.04] px-7 py-5">
          <p className="tl-serif text-[19px] italic leading-snug text-[#F4EFE6]">
            <span className="tl-sans not-italic font-medium text-[#EF4444]">The result · </span>
            climate risk has been invisible — until it's too late.
          </p>
        </div>
      </section>

      {/* gap */}
      <section className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-28">
        <div className="mx-auto max-w-4xl px-8">
          <Eyebrow>The gap</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(28px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            Every hazard has its own watchtower. None of them talk.
          </h2>
          <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-[#94A3B8]">
            A flood map here. A weather model there. An earthquake catalog somewhere else. A volcano bulletin
            in another. Each one is real and useful — but nobody puts them together, and nobody connects them
            to what you actually own or grow.
          </p>
          <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {ISLANDS.map((name, i) => (
              <div key={name} className="rounded-[10px] border border-white/[0.09] bg-white/[0.02] p-4.5 text-center">
                <div className="tl-mono mb-2.5 text-[11px] tracking-[0.14em] text-[#64748B]">{String(i + 1).padStart(2, '0')}</div>
                <div className="tl-serif text-[18px] italic text-[#F4EFE6]">{name}</div>
              </div>
            ))}
          </div>
          <p className="tl-serif mx-auto mt-8 max-w-2xl text-center text-[20px] italic leading-relaxed text-[#94A3B8]">
            Four separate islands of data — scattered, disconnected, and blind to each other.
          </p>
        </div>
      </section>

      {/* idea */}
      <section className="py-28 text-center">
        <div className="mx-auto max-w-4xl px-8">
          <Eyebrow>The idea</Eyebrow>
          <h2 className="tl-serif mx-auto max-w-3xl text-[clamp(28px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            So we built one engine that reads all of it.
          </h2>
          <p className="mx-auto mt-5 max-w-2xl text-[15px] leading-relaxed text-[#94A3B8]">
            Point Tellumen at any spot on Earth — a farm, a factory, a house — and it reads live satellite,
            weather, earthquake and volcano data, then boils it all down into one easy number.
          </p>

          <div className="mt-14 flex flex-wrap items-center justify-center gap-6">
            <span className="tl-serif text-[clamp(90px,16vw,200px)] font-light italic leading-[0.9] text-[#F4EFE6]">0</span>
            <span className="tl-mono text-[14px] uppercase tracking-[0.22em] text-[#94A3B8]">to</span>
            <span className="tl-serif text-[clamp(90px,16vw,200px)] font-light italic leading-[0.9] text-[#EF4444]">100</span>
          </div>
          <div className="tl-mono mt-5 flex flex-wrap justify-center gap-3 text-[12px] text-[#94A3B8]">
            <span className="rounded-full border border-[#34D399]/35 px-2.5 py-1 text-[#34D399]">0–33 · calm</span>
            <span className="rounded-full border border-[#F59E0B]/35 px-2.5 py-1 text-[#F59E0B]">34–66 · watch</span>
            <span className="rounded-full border border-[#EF4444]/35 px-2.5 py-1 text-[#EF4444]">67–100 · real danger</span>
          </div>

          <p className="mx-auto mt-10 max-w-xl text-[15px] leading-relaxed text-[#94A3B8]">
            One risk score for any hazard, any place. Low is calm, high means real danger — and it isn't fixed.
            Check it today, or fast-forward to see the risk in the future.
          </p>
          <div className="mt-10 flex flex-wrap justify-center gap-8">
            {[['2030', 'Near-term'], ['2050', 'Mid-century'], ['2100', 'Long horizon']].map(([y, note]) => (
              <div key={y} className="text-center">
                <div className="tl-serif text-[28px] italic text-[#7DD3FC]">{y}</div>
                <div className="tl-mono mt-1 text-[12px] uppercase tracking-[0.14em] text-[#94A3B8]">{note}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-28">
        <div className="mx-auto max-w-4xl px-8">
          <Eyebrow>How it works</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(28px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            Four steps. Running all the time.
          </h2>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.k} className="rounded-xl border border-white/[0.09] bg-white/[0.02] p-6">
                <div className="tl-serif text-[56px] italic font-light leading-none text-[#7DD3FC]">{String(i + 1).padStart(2, '0')}</div>
                <div className="tl-mono mt-3.5 mb-2.5 text-[12px] uppercase tracking-[0.20em] text-[#F4EFE6]">{s.k}</div>
                <div className="text-[13.5px] leading-relaxed text-[#94A3B8]">{s.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* data */}
      <section id="data" className="py-28">
        <div className="mx-auto max-w-4xl px-8">
          <Eyebrow>The data</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(28px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            Real feeds. From real space agencies.
          </h2>
          <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-[#94A3B8]">
            Nothing here is guessed or simulated — every score traces back to a live public data source.
            Reproducible, auditable, and free of black boxes.
          </p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {SOURCES.map(s => (
              <div key={s.kind} className="rounded-xl border border-white/[0.09] bg-white/[0.02] p-5.5">
                <div className="tl-mono mb-3 text-[10.5px] uppercase tracking-[0.16em] text-[#38BDF8]">{s.kind}</div>
                <div className="mb-1.5 text-[15px] font-medium text-[#F4EFE6]">{s.name}</div>
                <div className="text-[13px] leading-relaxed text-[#94A3B8]">{s.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* for who */}
      <section id="for" className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-28">
        <div className="mx-auto max-w-5xl px-8">
          <Eyebrow>Who it's for</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(28px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            Three industries. Same live score. Different decisions.
          </h2>
          <div className="mt-10 grid gap-5 lg:grid-cols-3">
            {AUDIENCES.map(a => (
              <button key={a.kind} onClick={onExplore}
                className="rounded-2xl border border-white/[0.09] bg-white/[0.02] p-7 text-left transition hover:-translate-y-0.5 hover:border-[#38BDF8]/35 hover:bg-[#38BDF8]/[0.03]">
                <span className="mb-3.5 flex h-10 w-10 items-center justify-center rounded-xl bg-[#38BDF8]/10 text-[#7DD3FC]"><a.icon size={19} /></span>
                <div className="tl-mono mb-3.5 text-[11px] uppercase tracking-[0.20em] text-[#38BDF8]">{a.kind}</div>
                <div className="tl-serif mb-5.5 text-[24px] italic font-light leading-tight text-[#F4EFE6]">{a.h}</div>
                {a.feats.map(([t, d], i) => (
                  <div key={t} className={`py-3 ${i > 0 ? 'border-t border-white/[0.09]' : ''}`}>
                    <strong className="mb-1 block text-[14px] font-medium text-[#F4EFE6]">{t}</strong>
                    <span className="text-[12.5px] leading-relaxed text-[#94A3B8]">{d}</span>
                  </div>
                ))}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* differentiation */}
      <section className="py-28">
        <div className="mx-auto max-w-4xl px-8">
          <Eyebrow>Why nothing else in the EU does this</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(28px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            Everyone else picks one thing. We do all of it.
          </h2>
          <div className="mt-10 grid gap-5 md:grid-cols-2">
            <div className="rounded-2xl border border-[#94A3B8]/20 bg-[#94A3B8]/[0.06] p-7">
              <div className="tl-mono mb-4.5 text-[11px] uppercase tracking-[0.20em] text-[#64748B]">Other tools</div>
              <div className="tl-serif text-[22px] italic font-light leading-snug text-[#94A3B8]">One hazard at a time.</div>
              <div className="mt-2 text-[12.5px] leading-relaxed text-[#64748B]">Just flood, or just fire, never both.</div>
              <div className="my-5 border-t border-[#94A3B8]/20" />
              <div className="tl-serif text-[22px] italic font-light leading-snug text-[#94A3B8]">One industry at a time.</div>
              <div className="mt-2 text-[12.5px] leading-relaxed text-[#64748B]">Just banks, or just farms, never both.</div>
            </div>
            <div className="rounded-2xl border border-[#38BDF8]/35 bg-gradient-to-br from-[#38BDF8]/10 to-[#34D399]/5 p-7">
              <div className="tl-mono mb-4.5 text-[11px] uppercase tracking-[0.20em] text-[#7DD3FC]">Tellumen</div>
              <div className="tl-serif text-[22px] italic font-light leading-snug text-[#F4EFE6]">Every hazard, one engine.</div>
              <div className="mt-2 text-[12.5px] leading-relaxed text-[#94A3B8]">Flood + fire + quake + volcano + more, together.</div>
              <div className="my-5 border-t border-[#38BDF8]/30" />
              <div className="tl-serif text-[22px] italic font-light leading-snug text-[#F4EFE6]">Every industry, same score.</div>
              <div className="mt-2 text-[12.5px] leading-relaxed text-[#94A3B8]">Banking, farming and insurance, together.</div>
            </div>
          </div>
        </div>
      </section>

      {/* proof */}
      <section id="proof" className="bg-gradient-to-b from-[#0A0F1C] to-[#111827] py-28">
        <div className="mx-auto max-w-5xl px-8">
          <Eyebrow>Proof, not promises</Eyebrow>
          <h2 className="tl-serif max-w-3xl text-[clamp(28px,4vw,44px)] font-light italic leading-[1.1] text-[#F4EFE6]">
            We test our model against real disasters — misses included.
          </h2>
          <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-[#94A3B8]">
            Before we trust a number, we check it against something that already happened. When we're wrong, we say so.
          </p>
          <div className="mt-10 grid gap-5 lg:grid-cols-3">
            {PROOFS.map(p => (
              <div key={p.badge} className="rounded-xl border border-white/[0.09] bg-white/[0.02] p-6.5">
                <span className={`tl-mono mb-3.5 inline-block rounded-full px-2.5 py-1 text-[10.5px] uppercase tracking-[0.14em] ${p.hit ? 'bg-[#34D399]/10 text-[#34D399]' : 'bg-[#F59E0B]/10 text-[#F59E0B]'}`}>
                  {p.badge}
                </span>
                <div className="tl-serif mb-3 text-[21px] italic font-light leading-snug text-[#F4EFE6]">{p.title}</div>
                <p className="text-[13.5px] leading-relaxed text-[#94A3B8]">{p.body}</p>
                <div className="tl-mono mt-3.5 flex gap-4 border-t border-white/[0.09] pt-3.5 text-[12px] text-[#94A3B8]">
                  <span>{p.m1[0]} <b className="ml-1 font-medium text-[#7DD3FC]">{p.m1[1]}</b></span>
                  <span>{p.m2[0]} <b className="ml-1 font-medium text-[#7DD3FC]">{p.m2[1]}</b></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* closing */}
      <section className="relative overflow-hidden bg-gradient-to-b from-[#0A0F1C] to-[#050810] px-8 py-36 text-center">
        <div className="tl-starfield absolute inset-0 pointer-events-none" />
        <div className="relative">
          <p className="tl-serif mx-auto max-w-3xl text-[clamp(32px,5.5vw,68px)] font-light italic leading-[1.05] text-[#F4EFE6]">
            The next disaster <span className="text-[#7DD3FC]">won't be invisible.</span>
          </p>
          <p className="mx-auto mt-7 max-w-xl text-[16px] leading-relaxed text-[#94A3B8]">
            One live score. Every hazard. Every industry. Tested against reality, not just theory — so the
            businesses that feed us, insure us and lend to us can see risk coming, instead of finding out the hard way.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Btn primary onClick={onExplore}>Explore solutions <ArrowRight size={16} /></Btn>
            <Btn onClick={onEnter}>Enter the platform</Btn>
          </div>
          <div className="tl-mono mt-14 text-[12px] uppercase tracking-[0.24em] text-[#38BDF8]">Tellumen · Light on the Earth</div>
        </div>
      </section>

      <footer className="border-t border-white/[0.09] px-8 py-9 text-center">
        <span className="tl-mono text-[11px] tracking-[0.10em] text-[#64748B]">
          © 2026 Tellumen. Every number traces back to a live public data source.
          {summary?.total_current_scores ? ` · ${summary.total_current_scores.toLocaleString()} risk scores live right now.` : ''}
        </span>
      </footer>
    </div>
  )
}
