import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FlaskConical, CheckCircle2, AlertTriangle } from 'lucide-react'
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

function PerilCard({ p }: { p: Peril }) {
  const [openBand, setOpenBand] = useState<string | null>(null)
  if (!p.available) return null
  const maxMean = Math.max(...p.bands.map(b => b.mean_events ?? 0), 0.01)
  const ok = p.passed
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="display text-lg font-semibold text-[var(--color-ink)] capitalize">{p.peril}</span>
            <span className="mono text-[10px] text-[var(--color-faint)]">{p.label}</span>
          </div>
          <div className="mono text-[10.5px] text-[var(--color-faint)] mt-0.5">
            {num(p.n_cells_scored)} scored cells · {num(p.n_events_observed)} observed events · {p.observed_window_years}-yr window · near field {p.near_field_km}km
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 mono text-[11px] font-semibold"
          style={{ background: ok ? '#7BBF8F22' : '#E8B24C22', color: ok ? '#4FA46E' : '#C68A1E' }}>
          {ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}{ok ? 'Consistent' : 'Review'}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div><div className="display text-[22px] font-semibold tabular-nums" style={{ color: (p.spearman ?? 0) >= 0.5 ? '#4FA46E' : (p.spearman ?? 0) >= 0.3 ? '#C68A1E' : '#D23B3B' }}>{p.spearman?.toFixed(2) ?? '—'}</div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-0.5">Spearman ρ (score↔events)</div></div>
        <div><div className="display text-[22px] font-semibold tabular-nums text-[var(--color-ink)]">{p.auc?.toFixed(2) ?? '—'}</div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-0.5">AUC (any event)</div></div>
        <div><div className="display text-[22px] font-semibold tabular-nums text-[var(--color-ink)]">{p.monotonic ? 'Yes' : 'No'}</div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-0.5">Monotonic by band</div></div>
      </div>

      {/* mean observed events by score band — click a band to inspect representative cells */}
      <div className="space-y-1.5">
        {p.bands.map(b => {
          const open = openBand === b.band
          return (
            <div key={b.band}>
              <div onClick={() => b.n_cells && setOpenBand(open ? null : b.band)}
                className={`flex items-center gap-2 text-[12px] ${b.n_cells ? 'cursor-pointer' : ''}`}>
                <span className="mono w-6 font-semibold" style={{ color: BAND_COLOR[b.band] }}>{b.band}</span>
                <div className="flex-1 h-4 rounded bg-[var(--color-panel-2)] overflow-hidden">
                  <div className="h-full rounded" style={{ width: `${Math.max(1.5, 100 * (b.mean_events ?? 0) / maxMean)}%`, background: BAND_COLOR[b.band], opacity: 0.85 }} />
                </div>
                <span className="mono text-[10.5px] text-[var(--color-mute)] tabular-nums w-40 text-right">
                  {b.mean_events ?? '—'} events/cell · {b.pct_with_event ?? '—'}% hit · {num(b.n_cells)} cells
                </span>
              </div>
              {open && b.samples?.length > 0 && (
                <div className="pl-8 pr-1 py-1.5 space-y-0.5">
                  <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Representative cells (most-active first; quiet cells shown too)</div>
                  {b.samples.map(s => (
                    <div key={s.h3_cell} className="flex items-center gap-2 text-[11px] tabular-nums">
                      <span className="mono text-[var(--color-faint)]">{s.lat.toFixed(2)}, {s.lon.toFixed(2)}</span>
                      <span className="mono text-[9.5px] text-[var(--color-faint)]">H3 {s.h3_cell.slice(0, 8)}…</span>
                      <span className="flex-1" />
                      <span className="mono text-[var(--color-mute)]">score {s.score}</span>
                      <span className="mono px-1.5 py-0.5 rounded" style={{ background: s.observed_events > 0 ? '#7BBF8F22' : '#E8B24C22', color: s.observed_events > 0 ? '#4FA46E' : '#C68A1E' }}>
                        {s.observed_events} observed
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <p className="text-[12px] mt-3.5" style={{ color: ok ? 'var(--color-mute)' : '#C68A1E' }}>{p.verdict}</p>
    </Card>
  )
}

// Economic-impact validation — the stronger, out-of-sample test: the hazard score regressed on ~31 years of
// real crop yield, gated at r²≥0.40. Covers drought/heat/soil-water, which have no discrete event catalogue.
function EconomicCard({ e }: { e: Economic }) {
  const gate = e.gate_r2_oos
  const pass = e.fits.filter(f => f.passed)
  const held = e.fits.filter(f => !f.passed)
  const maxR2 = Math.max(...e.fits.map(f => f.r2_oos), gate, 0.6)
  const Row = ({ f }: { f: CropFit }) => (
    <div className="flex items-center gap-2 text-[12px] py-1">
      <span className="min-w-0 w-40 truncate capitalize text-[var(--color-ink)]">{prettyRegion(f.region)}</span>
      <span className="mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)] shrink-0">{f.crop ?? f.hazard_driver}</span>
      <div className="flex-1 h-3.5 rounded bg-[var(--color-panel-2)] overflow-hidden relative min-w-[60px]">
        {/* the r²≥0.40 gate line */}
        <div className="absolute top-0 bottom-0 w-px bg-[var(--color-faint)]" style={{ left: `${100 * gate / maxR2}%` }} />
        <div className="h-full rounded" style={{ width: `${Math.max(2, 100 * f.r2_oos / maxR2)}%`, background: f.passed ? '#4FA46E' : '#C68A1E', opacity: 0.85 }} />
      </div>
      <span className="mono text-[10.5px] tabular-nums w-28 text-right" style={{ color: f.passed ? '#4FA46E' : 'var(--color-mute)' }}>
        r²{f.r2_oos.toFixed(2)} · {f.n_years}yr
      </span>
    </div>
  )
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
        <div>
          <span className="display text-lg font-semibold text-[var(--color-ink)]">Economic impact · agriculture</span>
          <div className="mono text-[10.5px] text-[var(--color-faint)] mt-0.5">
            hazard score vs ~31 yrs of real crop yield · out-of-sample r² · covers {e.hazards_covered.join(', ')}
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 mono text-[11px] font-semibold" style={{ background: '#7BBF8F22', color: '#4FA46E' }}>
          <CheckCircle2 size={13} />{e.n_pass}/{e.n_fits} clear r²≥{gate.toFixed(2)}
        </span>
      </div>
      <p className="text-[12px] text-[var(--color-mute)] max-w-3xl mb-3">
        The stronger test, where we hold real impact: yield is <em>not</em> an input to the score, so this measures genuine out-of-sample skill — not the in-sample faithfulness the catalogue test measures. A crop euro is published only above the r²≥{gate.toFixed(2)} bar; the rest are held.
      </p>

      <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Clears the bar · published</div>
      {pass.map(f => <Row key={f.region + f.hazard_driver} f={f} />)}
      {held.length > 0 && <>
        <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-3 mb-1">Held below the bar · not published ({held.length})</div>
        {held.slice(0, 6).map(f => <Row key={f.region + f.hazard_driver} f={f} />)}
        {held.length > 6 && <div className="mono text-[10px] text-[var(--color-faint)] mt-1">+{held.length - 6} more held</div>}
      </>}

      {e.events.length > 0 && <>
        <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-4 mb-1.5">Named production-shock events · observed vs modelled</div>
        <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
          {e.events.map((ev, i) => (
            <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 py-1.5 text-[12px]">
              <span className="text-[var(--color-ink)]">{ev.event}</span>
              <span className="mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)]">{ev.hazard}</span>
              <span className="flex-1" />
              {ev.observed_shock_pct != null && ev.model_shock_pct != null
                ? <span className="mono text-[10.5px] text-[var(--color-mute)] tabular-nums">observed {ev.observed_shock_pct}% · modelled {ev.model_shock_pct}%</span>
                : <span className="mono text-[10.5px] text-[var(--color-faint)]">indicative — no clean anchor</span>}
              <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: ev.passed ? '#7BBF8F22' : '#E8B24C22', color: ev.passed ? '#4FA46E' : '#C68A1E' }}>{ev.passed ? 'pass' : 'held'}</span>
            </div>
          ))}
        </div>
      </>}
    </Card>
  )
}

export default function ModelValidation() {
  const q = useQuery({ queryKey: ['model-validation'], queryFn: () => api.get<Resp>('/v1/realized-exposure/model-validation') })
  const d = q.data
  const note = d?.perils?.[0]?.note

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Assess · model validation</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Score vs observed record</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          The credibility check a model-validation team or supervisor asks for: don't just publish a score — show it is consistent with what actually happened. Each hazard is validated against the ground truth that fits it — a discrete event catalogue where we hold one, real economic impact where we don't.
        </p>
      </div>

      {q.isLoading && <Card className="p-5 text-[13px] text-[var(--color-mute)]">Running the backtest…</Card>}

      <div className="flex items-center gap-2">
        <FlaskConical size={15} className="text-[var(--color-sky)]" />
        <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Observed event catalogue · seismic, storm</span>
      </div>

      {d?.perils?.map(p => <PerilCard key={p.peril} p={p} />)}

      {d?.economic?.available && (
        <>
          <div className="flex items-center gap-2 pt-1">
            <FlaskConical size={15} className="text-[var(--color-sky)]" />
            <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Economic impact · drought, heat, soil-water</span>
          </div>
          <EconomicCard e={d.economic} />
          <Card className="p-4 bg-[var(--color-panel-2)]">
            <div className="mono text-[9px] uppercase tracking-[0.16em] text-[var(--color-faint)] mb-1.5">Method &amp; honesty · economic</div>
            <p className="text-[11.5px] text-[var(--color-mute)] leading-relaxed">{d.economic.note}</p>
          </Card>
        </>
      )}

      {note && (
        <Card className="p-4 bg-[var(--color-panel-2)]">
          <div className="mono text-[9px] uppercase tracking-[0.16em] text-[var(--color-faint)] mb-1.5">Method &amp; honesty · catalogue</div>
          <p className="text-[11.5px] text-[var(--color-mute)] leading-relaxed">{note}</p>
        </Card>
      )}
    </div>
  )
}
