import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FlaskConical, CheckCircle2, AlertTriangle, ChevronRight } from 'lucide-react'
import { api } from '../lib/api'
import { Eyebrow, Card } from '../components/ui'

// Model validation — the credibility layer. Tests Tellumen's own hazard scores against the observed event
// catalogues it holds (seismic, storm): do higher-scored locations actually carry more observed near-field
// events? Reports a per-band table + a Spearman discrimination metric + an honest verdict. In-sample
// consistency (faithfulness), not out-of-sample prediction — stated plainly, and weak results shown as weak.

interface Sample { h3_cell: string; lat: number; lon: number; score: number; observed_events: number }
interface Band { band: string; n_cells: number; mean_events: number | null; pct_with_event: number | null; samples: Sample[] }
interface Peril {
  available: boolean; peril: string; label: string; near_field_km: number
  n_cells_scored: number; n_events_observed: number; observed_window_years: number
  pct_cells_with_event: number; spearman: number | null; auc: number | null
  monotonic: boolean | null; passed: boolean; bands: Band[]; verdict: string; note: string
}
interface CropFit { region: string; crop: string | null; hazard_driver: string; r2: number | null; r2_oos: number; n_years: number | null; passed: boolean }
interface CropEvent { event: string; commodity: string; hazard: string; observed_shock_pct: number | null; model_shock_pct: number | null; tolerance_pct: number | null; passed: boolean }
interface Economic {
  available: boolean; gate_r2_oos: number; n_fits: number; n_pass: number; hazards_covered: string[]
  fits: CropFit[]; events: CropEvent[]; note: string
}
interface Resp { perils: Peril[]; economic?: Economic }

const BAND_COLOR: Record<string, string> = { VH: '#D23B3B', H: '#E8744A', M: '#E8B24C', L: '#7BBF8F' }
const num = (n: number) => n.toLocaleString('en-US')
const prettyRegion = (s: string) => s.replace(/_/g, ' ')

const BAND_FULL: Record<string, string> = { VH: 'Very high', H: 'High', M: 'Medium', L: 'Low' }

function PerilCard({ p }: { p: Peril }) {
  const [open, setOpen] = useState(false)
  if (!p.available) return null
  const ok = p.passed
  const maxMean = Math.max(...p.bands.map(b => b.mean_events ?? 0), 0.01)
  const vh = p.bands.find(b => b.band === 'VH')
  const lo = p.bands.find(b => b.band === 'L')
  const quake = p.peril === 'seismic'
  const noun = quake ? 'earthquake' : 'storm'
  // the plain-language headline, computed from the real band figures
  const headline = ok
    ? <>Places we scored <b className="text-[var(--color-ink)]">Very high</b> took a real {noun} <b className="text-[var(--color-ink)]">{vh?.pct_with_event}%</b> of the time. Places we scored <b className="text-[var(--color-ink)]">Low</b>, <b className="text-[var(--color-ink)]">{lo?.pct_with_event}%</b>. The score sorts the risk the right way.</>
    : <>High-scored and low-scored places took {noun}s at <b style={{ color: '#C68A1E' }}>similar rates</b> — the score and the real record don't line up here, so this one is flagged for a look.</>

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-baseline gap-2.5">
          <h3 className="display text-[22px] font-semibold text-[var(--color-ink)] capitalize">{p.peril === 'seismic' ? 'Earthquakes' : 'Storms'}</h3>
          <span className="text-[12px] text-[var(--color-faint)]">{num(p.n_cells_scored)} locations · last {p.observed_window_years} years</span>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-semibold"
          style={{ background: ok ? '#7BBF8F22' : '#E8B24C22', color: ok ? '#4FA46E' : '#C68A1E' }}>
          {ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}{ok ? 'Score matches reality' : 'Needs a look'}
        </span>
      </div>

      <p className="text-[14.5px] leading-relaxed text-[var(--color-mute)] max-w-2xl mb-5">{headline}</p>

      {/* the one hero chart: real events per location, by score band */}
      <div className="text-[11px] text-[var(--color-faint)] mb-2">Real {noun}s per location, by how we scored it</div>
      <div className="space-y-2.5">
        {p.bands.map(b => (
          <div key={b.band} className="flex items-center gap-3">
            <span className="w-20 shrink-0 text-[13px] font-medium" style={{ color: BAND_COLOR[b.band] }}>{BAND_FULL[b.band]}</span>
            <div className="flex-1 h-7 rounded-md bg-[var(--color-panel-2)] overflow-hidden relative">
              <div className="h-full rounded-md flex items-center justify-end pr-2" style={{ width: `${Math.max(6, 100 * (b.mean_events ?? 0) / maxMean)}%`, background: BAND_COLOR[b.band] }}>
                <span className="text-[12px] font-semibold text-white tabular-nums whitespace-nowrap">{b.mean_events ?? '—'}</span>
              </div>
            </div>
            <span className="w-24 shrink-0 text-right text-[12px] text-[var(--color-mute)] tabular-nums">{b.pct_with_event ?? '—'}% hit</span>
          </div>
        ))}
      </div>
      <div className="text-[11px] text-[var(--color-faint)] mt-2">Longer bar = more real events. A working score is tall at the top, short at the bottom.</div>

      {/* quiet numbers footer + optional detail */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 mt-5 pt-3 border-t border-[var(--color-line)] text-[12px]">
        <span className="text-[var(--color-faint)]">Rank agreement <b className="text-[var(--color-ink)]">{p.spearman?.toFixed(2) ?? '—'}</b> <span className="text-[var(--color-faint)]">/ 1.0</span></span>
        <span className="text-[var(--color-faint)]">Hit-vs-quiet score <b className="text-[var(--color-ink)]">{p.auc?.toFixed(2) ?? '—'}</b> <span className="text-[var(--color-faint)]">/ 1.0</span></span>
        {vh?.samples && vh.samples.length > 0 && (
          <button onClick={() => setOpen(o => !o)} className="ml-auto inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">
            {open ? 'Hide' : 'See'} example locations <ChevronRight size={13} className={open ? 'rotate-90 transition' : 'transition'} />
          </button>
        )}
      </div>
      {open && vh?.samples && (
        <div className="mt-3 rounded-lg bg-[var(--color-panel-2)] p-3">
          <div className="text-[11px] text-[var(--color-faint)] mb-2">A few of the {BAND_FULL['VH'].toLowerCase()}-scored locations and the real {noun}s counted near each:</div>
          <div className="space-y-1">
            {vh.samples.slice(0, 6).map(s => (
              <div key={s.h3_cell} className="flex items-center gap-3 text-[12.5px] tabular-nums">
                <span className="text-[var(--color-mute)]">{s.lat.toFixed(2)}, {s.lon.toFixed(2)}</span>
                <span className="flex-1" />
                <span className="text-[var(--color-faint)]">score {s.score}</span>
                <span className="px-2 py-0.5 rounded text-[11.5px] font-medium" style={{ background: s.observed_events > 0 ? '#7BBF8F22' : '#E8B24C22', color: s.observed_events > 0 ? '#4FA46E' : '#C68A1E' }}>
                  {s.observed_events} real {s.observed_events === 1 ? noun : noun + 's'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

// Economic-impact validation — the stronger, out-of-sample test: the hazard score regressed on ~31 years of
// real crop yield, gated at r²≥0.40. Covers drought/heat/soil-water, which have no discrete event catalogue.
function EconomicCard({ e }: { e: Economic }) {
  const [showHeld, setShowHeld] = useState(false)
  const gate = e.gate_r2_oos
  const pass = e.fits.filter(f => f.passed)
  const held = e.fits.filter(f => !f.passed)
  // scale bars 0..1 r² across the full [0,1] range so the 0.40 gate sits at a fixed, readable spot
  const CropRow = ({ f }: { f: CropFit }) => (
    <div className="flex items-center gap-3 py-1.5">
      <span className="w-36 shrink-0 text-[13px] capitalize text-[var(--color-ink)] truncate">{prettyRegion(f.region)}</span>
      <span className="w-16 shrink-0 text-[11.5px] text-[var(--color-faint)] truncate">{f.crop ?? f.hazard_driver}</span>
      <div className="flex-1 h-6 rounded-md bg-[var(--color-panel-2)] overflow-hidden relative min-w-[80px]">
        <div className="absolute top-0 bottom-0 w-0.5 bg-[var(--color-faint)] z-10" style={{ left: `${100 * gate}%` }} title={`publish bar: r²≥${gate.toFixed(2)}`} />
        <div className="h-full rounded-md" style={{ width: `${Math.max(3, 100 * f.r2_oos)}%`, background: f.passed ? '#4FA46E' : '#C68A1E', opacity: 0.9 }} />
      </div>
      <span className="w-10 shrink-0 text-right text-[12.5px] font-semibold tabular-nums" style={{ color: f.passed ? '#4FA46E' : 'var(--color-mute)' }}>{f.r2_oos.toFixed(2)}</span>
    </div>
  )
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-baseline gap-2.5">
          <h3 className="display text-[22px] font-semibold text-[var(--color-ink)]">Crop yield</h3>
          <span className="text-[12px] text-[var(--color-faint)]">vs 31 years of real harvests · {e.hazards_covered.join(', ')}</span>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-semibold" style={{ background: '#7BBF8F22', color: '#4FA46E' }}>
          <CheckCircle2 size={15} />{e.n_pass} of {e.n_fits} crops predict real losses
        </span>
      </div>

      <p className="text-[14.5px] leading-relaxed text-[var(--color-mute)] max-w-2xl mb-5">
        We tested each crop's score against <b className="text-[var(--color-ink)]">31 years of actual harvests</b>. Because yield never feeds the score, a crop it predicts well is real skill — and <b className="text-[var(--color-ink)]">{e.n_pass}</b> clear our bar to publish a euro figure. The rest we hold back rather than guess.
      </p>

      {/* the wins — prominent */}
      <div className="text-[12px] font-medium mb-2" style={{ color: '#4FA46E' }}>Good enough to publish — the score explains real yield swings</div>
      <div className="space-y-0.5 mb-1">{pass.map(f => <CropRow key={f.region + f.hazard_driver} f={f} />)}</div>
      <div className="text-[11px] text-[var(--color-faint)] mt-1">Bar = r² (0–1, how much of real yield the score explains). The vertical line is the r²≥{gate.toFixed(2)} publish bar.</div>

      {/* the held ones — collapsed by default */}
      {held.length > 0 && (
        <div className="mt-4">
          <button onClick={() => setShowHeld(s => !s)} className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">
            <ChevronRight size={14} className={showHeld ? 'rotate-90 transition' : 'transition'} />
            {held.length} more crops below the bar — number held back
          </button>
          {showHeld && <div className="space-y-0.5 mt-2 opacity-80">{held.map(f => <CropRow key={f.region + f.hazard_driver} f={f} />)}</div>}
        </div>
      )}

      {/* named disasters */}
      {e.events.length > 0 && (
        <div className="mt-6 pt-4 border-t border-[var(--color-line)]">
          <div className="text-[13px] font-medium text-[var(--color-ink)] mb-1">Named disasters — did the model match what happened?</div>
          <p className="text-[12.5px] text-[var(--color-mute)] mb-3 max-w-2xl leading-relaxed">We replayed real crop disasters and compared the model's predicted production loss to what was actually recorded.</p>
          <div className="space-y-2">
            {e.events.map((ev, i) => (
              <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
                <span className="text-[var(--color-ink)] font-medium">{ev.event}</span>
                <span className="flex-1 min-w-0" />
                {ev.observed_shock_pct != null && ev.model_shock_pct != null
                  ? <span className="text-[12.5px] text-[var(--color-mute)] tabular-nums">predicted <b className="text-[var(--color-ink)]">{Math.abs(ev.model_shock_pct)}%</b> vs actual <b className="text-[var(--color-ink)]">{Math.abs(ev.observed_shock_pct)}%</b> loss</span>
                  : <span className="text-[12px] text-[var(--color-faint)]">no clean figure to check against</span>}
                <span className="px-2 py-0.5 rounded text-[11.5px] font-medium" style={{ background: ev.passed ? '#7BBF8F22' : '#E8B24C22', color: ev.passed ? '#4FA46E' : '#C68A1E' }}>{ev.passed ? 'match' : 'held'}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

// One beat of the validation story. Numbered, and — where there's evidence below — clickable to drill straight
// into it (which then drills further: band → cells, fit → r², event → observed vs modelled).
function StoryRow({ n, title, tag, accent, drill, chips, children }: {
  n: string; title: string; tag?: string; accent?: string; drill?: () => void; chips?: ReactNode; children: ReactNode
}) {
  const a = accent || 'var(--color-sky)'
  return (
    <div onClick={drill}
      className={`group relative flex gap-3.5 rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] p-3.5 ${drill ? 'cursor-pointer lift' : ''}`}>
      <div className="shrink-0 mono text-[12px] font-semibold tabular-nums w-7 h-7 grid place-items-center rounded-lg"
        style={{ color: a, background: `color-mix(in oklab, ${a} 13%, transparent)` }}>{n}</div>
      <div className="min-w-0 flex-1">
        {tag && <div className="mono text-[9.5px] uppercase tracking-[0.16em] mb-1" style={{ color: accent || 'var(--color-faint)' }}>{tag}</div>}
        <div className="display text-[16px] font-semibold text-[var(--color-ink)] leading-snug">{title}</div>
        <p className="text-[13px] text-[var(--color-mute)] mt-1 leading-relaxed max-w-2xl">{children}</p>
        {chips && <div className="flex flex-wrap gap-2 mt-2.5">{chips}</div>}
      </div>
      {drill && (
        <span className="shrink-0 self-center inline-flex items-center gap-1 mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] group-hover:text-[var(--color-sky)] transition">
          drill <ChevronRight size={14} />
        </span>
      )}
    </div>
  )
}

export default function ModelValidation() {
  const q = useQuery({ queryKey: ['model-validation'], queryFn: () => api.get<Resp>('/v1/realized-exposure/model-validation') })
  const d = q.data
  const note = d?.perils?.[0]?.note
  const [flash, setFlash] = useState<string | null>(null)
  // scroll by element id (queried at click time) rather than a React ref — robust against ref-timing.
  const drillTo = (id: string, key: string) => {
    // this app's scroll container honours 'auto' but no-ops on 'smooth' scrollIntoView, so use 'auto'
    document.getElementById(id)?.scrollIntoView({ behavior: 'auto', block: 'start' })
    setFlash(key); window.setTimeout(() => setFlash(cur => (cur === key ? null : cur)), 1600)
  }
  const flashStyle = (key: string) => ({
    outline: flash === key ? '2px solid var(--color-sky)' : '2px solid transparent',
    outlineOffset: 6, borderRadius: 16, transition: 'outline-color .45s ease',
  })

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Assess · model validation</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-2">Does the score hold up against what happened?</h1>
        <p className="text-[15px] leading-relaxed text-[var(--color-mute)] max-w-2xl">
          A score is only worth what it can be checked against. So we don't publish one validation — we test each hazard against the <span className="text-[var(--color-ink)]">ground truth that actually fits it</span>, and we show you where it fails.
        </p>
      </div>

      {/* ── The story, as a workflow you drill: each beat clicks into the evidence below ── */}
      <div className="space-y-2">
        <StoryRow n="01" title="A score is only worth what it can be checked against">
          Two hazards have a full record of real events; others don't. So we check each against the ground truth that actually fits it.
        </StoryRow>

        <StoryRow n="02" tag="in-sample · faithfulness" title="Does the score reflect the record we hold?"
          drill={() => drillTo('mv-catalogue', 'cat')}
          chips={d?.perils?.map(p => (
            <span key={p.peril} className="inline-flex items-center gap-1 mono text-[10.5px] px-2 py-0.5 rounded capitalize"
              style={{ background: p.passed ? '#7BBF8F22' : '#E8B24C22', color: p.passed ? '#4FA46E' : '#C68A1E' }}>
              {p.passed ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}{p.peril}
            </span>
          ))}>
          For earthquakes and storms we hold every real event — so we can check whether high-scored places actually got hit more.
        </StoryRow>

        <StoryRow n="03" tag="out-of-sample · skill · the stronger test" accent="#4FA46E"
          title="Does it predict impact it never saw?"
          drill={() => drillTo('mv-economic', 'eco')}
          chips={d?.economic?.available ? [
            <span key="p" className="mono text-[10.5px] px-2 py-0.5 rounded" style={{ background: '#7BBF8F22', color: '#4FA46E' }}>{d.economic.n_pass} published</span>,
            <span key="h" className="mono text-[10.5px] px-2 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)]">{d.economic.n_fits - d.economic.n_pass} held</span>,
            <span key="g" className="mono text-[10.5px] px-2 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-faint)]">gate r²≥{d.economic.gate_r2_oos.toFixed(2)}</span>,
          ] : undefined}>
          For crops we hold 31 years of real harvests — so we can check whether the score predicts losses it never saw. The stronger test.
        </StoryRow>

        <StoryRow n="04" title="Where it fails, we say so" drill={() => drillTo('mv-economic', 'eco')}>
          Storms are flagged; most crops are held back. A dashboard that's all green is engineered — the honest gaps are what make the passes believable.
        </StoryRow>
      </div>

      {q.isLoading && <Card className="p-5 text-[13px] text-[var(--color-mute)]">Running the backtest…</Card>}

      <div id="mv-catalogue" style={flashStyle('cat')} className="space-y-4">
        <div className="flex items-center gap-2">
          <FlaskConical size={15} className="text-[var(--color-sky)]" />
          <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Step 02 · observed event catalogue · seismic, storm</span>
        </div>
        {d?.perils?.map(p => <PerilCard key={p.peril} p={p} />)}
        {note && (
          <Card className="p-4 bg-[var(--color-panel-2)]">
            <div className="mono text-[9px] uppercase tracking-[0.16em] text-[var(--color-faint)] mb-1.5">Method &amp; honesty · catalogue</div>
            <p className="text-[11.5px] text-[var(--color-mute)] leading-relaxed">{note}</p>
          </Card>
        )}
      </div>

      {d?.economic?.available && (
        <div id="mv-economic" style={flashStyle('eco')} className="space-y-4">
          <div className="flex items-center gap-2 pt-1">
            <FlaskConical size={15} className="text-[var(--color-sky)]" />
            <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Step 03 · economic impact · drought, heat, soil-water</span>
          </div>
          <EconomicCard e={d.economic} />
          <Card className="p-4 bg-[var(--color-panel-2)]">
            <div className="mono text-[9px] uppercase tracking-[0.16em] text-[var(--color-faint)] mb-1.5">Method &amp; honesty · economic</div>
            <p className="text-[11.5px] text-[var(--color-mute)] leading-relaxed">{d.economic.note}</p>
          </Card>
        </div>
      )}
    </div>
  )
}
