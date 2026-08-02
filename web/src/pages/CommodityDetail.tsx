import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, ShieldAlert, TrendingUp, FlaskConical } from 'lucide-react'
import { api } from '../lib/api'
import { Card, Eyebrow, Stat } from '../components/ui'
import MiniMap from '../components/MiniMap'

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`
const pretty = (h?: string | null) => !h ? '—' : h.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
const hz = (s?: number | null) => s == null ? '#64748b' : s >= 60 ? '#fb7185' : s >= 40 ? '#f59e0b' : s >= 1 ? '#34d399' : '#64748b'
const scen = (s: string) => ({ baseline: 'Baseline', orderly_1_5c: 'Orderly 1.5°C', disorderly_2c: 'Disorderly 2°C', hot_house_3_5c: 'Hot-house 3.5°C' } as Record<string, string>)[s] || s

interface Plot { plot_id: string; plot_name: string; country: string | null; lat: number; lon: number; spend_eur: number; top_hazard: string | null; hazard_score: number | null }
interface Fit { origin: string; hazard_driver: string; r2: number | null; r2_oos: number | null; band_cov68: number | null; n_years: number | null; spei_scale: number | null; season_months: string | null; baseline_from: number | null; baseline_to: number | null; source_note: string | null; publishes: boolean; confidence_grade: string | null }
interface Proj { scenario: string; time_horizon: string; avg_score: number; ci_lo: number | null; ci_hi: number | null; n: number }
interface Adapt { hazard: string; label: string; actions: string[] }
interface Summary { annual_spend_eur: number; n_plots: number; calibration: string | null; held_reason: string | null; avg_hazard: number | null; top_hazard: string | null; yield_shock_pct: number | null; volume_at_risk_eur: number | null; volume_at_risk_low_eur: number | null; volume_at_risk_high_eur: number | null; fit_r2: number | null; confidence_grade: string | null; measured_basis: string | null }
interface Resp { commodity: string; eudr_covered: boolean; summary: Summary; plots: Plot[]; projections: Proj[]; fits: Fit[]; adaptation: Adapt[] }

export default function CommodityDetail() {
  const { id } = useParams()
  const q = useQuery({ queryKey: ['commodity', id], queryFn: () => api.get<Resp>(`/v1/supply/commodity/${id}`) })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load this commodity.</Center>
  const d = q.data, s = d.summary
  const published = s.calibration === 'backtested' || s.calibration === 'ranged'
  const varLabel = published
    ? (s.calibration === 'ranged' ? `${eur(s.volume_at_risk_low_eur)}–${eur(s.volume_at_risk_high_eur)}` : eur(s.volume_at_risk_eur))
    : '€ withheld'
  const lats = d.plots.filter(p => p.lat != null)
  const cLat = lats.length ? lats.reduce((a, p) => a + p.lat, 0) / lats.length : null
  const cLon = lats.length ? lats.reduce((a, p) => a + p.lon, 0) / lats.length : null

  // projections matrix: scenarios × horizons
  const horizons = [...new Set(d.projections.map(p => p.time_horizon))].sort()
  const scenarios = [...new Set(d.projections.map(p => p.scenario))]
  const at = (sc: string, h: string) => d.projections.find(p => p.scenario === sc && p.time_horizon === h) ?? null
  const cell = (sc: string, h: string) => at(sc, h)?.avg_score ?? null

  return (
    <div className="fadeup space-y-6">
      <Link to="/cogs" className="inline-flex items-center gap-1.5 text-[13px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><ArrowLeft size={15} /> back to COGS-at-risk</Link>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>Commodity · analytics</Eyebrow>
          <div className="flex items-center gap-3 mt-2">
            <h1 className="display text-3xl font-semibold">{d.commodity}</h1>
            {d.eudr_covered && <span className="mono text-[9px] px-2 py-0.5 rounded-full text-[var(--color-blue)] bg-[color-mix(in_oklab,var(--color-blue)_13%,transparent)]">EUDR</span>}
            {s.calibration && <span className="mono text-[9px] px-2 py-0.5 rounded-full text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_13%,transparent)]">{s.calibration}{s.fit_r2 != null ? ` · r² ${s.fit_r2.toFixed(2)}` : ''}</span>}
            {s.confidence_grade && <span className="mono text-[9px] px-2 py-0.5 rounded-full text-[var(--color-mute)] border border-[var(--color-line-2)]">Grade {s.confidence_grade}</span>}
          </div>
          <p className="text-[var(--color-mute)] text-sm mt-1">Driver hazard: <span className="mono" style={{ color: hz(s.avg_hazard) }}>{pretty(s.top_hazard)} {s.avg_hazard ?? '—'}</span></p>
        </div>
        <div className="text-right">
          <div className="display text-2xl font-semibold" style={{ color: published ? 'var(--color-warn)' : 'var(--color-faint)' }}>{varLabel}</div>
          <div className="text-[10px] text-[var(--color-faint)]">{published ? 'volume at risk' : 'exposure mapped — not €-published'}</div>
        </div>
      </div>

      <div className="grid sm:grid-cols-4 gap-4">
        <Stat big={eur(s.annual_spend_eur)} label="annual spend" />
        <Stat big={s.n_plots} label="sourcing plots" />
        <Stat big={s.yield_shock_pct != null ? `${s.yield_shock_pct}%` : '—'} label="of yield at risk" tone={published && (s.yield_shock_pct ?? 0) > 0 ? 'warn' : 'ink'} />
        <Stat big={s.confidence_grade ?? '—'} label="confidence grade" />
      </div>

      {!published && s.held_reason && (
        <Card className="p-4 border-l-2" style={{ borderLeftColor: 'var(--color-warn)' }}>
          <div className="text-[13px] text-[var(--color-ink)]"><span className="text-[var(--color-warn)] font-medium">€ withheld — </span>{s.held_reason}</div>
          <div className="text-[11px] text-[var(--color-faint)] mt-1">Exposure is fully mapped (spend, plots, hazard below). We publish a euro only once the hazard→yield chain reproduces real crop failures — not before.</div>
        </Card>
      )}

      <div className="grid lg:grid-cols-2 gap-5">
        {/* where it's sourced */}
        <div className="space-y-4">
          {cLat != null && cLon != null
            ? <MiniMap lat={cLat} lon={cLon} color={hz(s.avg_hazard)} zoom={4} />
            : <Card className="p-8 text-center text-[var(--color-faint)] text-sm">no geolocated plots</Card>}
          <Card className="p-5">
            <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-3">Sourcing plots</div>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase text-left"><th className="font-normal py-1 pr-3">Plot</th><th className="font-normal pr-3">Country</th><th className="font-normal pr-3 text-right">Spend</th><th className="font-normal">Hazard</th></tr></thead>
                <tbody>
                  {d.plots.map(p => (
                    <tr key={p.plot_id} onClick={() => window.open(`/detail/plot/${p.plot_id}`, '_blank')} className="border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-panel)]">
                      <td className="py-2 pr-3 text-[var(--color-ink)] hover:text-[var(--color-sky)]">{p.plot_name}</td>
                      <td className="pr-3 text-[var(--color-mute)] mono text-[11px]">{p.country ?? '—'}</td>
                      <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(p.spend_eur)}</td>
                      <td><span className="mono text-[12px]" style={{ color: hz(p.hazard_score) }}>{pretty(p.top_hazard)} {p.hazard_score != null ? Math.round(p.hazard_score) : '—'}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          {s.measured_basis && <div className="text-[11px] text-[var(--color-faint)]">Measures {s.measured_basis}</div>}
        </div>

        {/* analytics */}
        <div className="space-y-4">
          {/* calibration / validation */}
          <Card className="p-5">
            <div className="flex items-center gap-2 mb-3"><FlaskConical size={15} className="text-[var(--color-sky)]" /><span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Calibration & validation</span></div>
            {d.fits.length === 0 ? <div className="text-[13px] text-[var(--color-faint)]">No multi-year regression on record for this crop yet.</div> :
              <div className="space-y-3">
                {d.fits.map((f, i) => (
                  <div key={i} className="border-b border-[var(--color-line)] pb-3 last:border-0">
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] text-[var(--color-ink)]">{f.origin} · {pretty(f.hazard_driver)}</span>
                      <span className="mono text-[10px] px-2 py-0.5 rounded-full" style={{ color: f.publishes ? 'var(--color-good)' : 'var(--color-faint)', background: 'color-mix(in oklab, currentColor 12%, transparent)' }}>{f.publishes ? `publishes${f.confidence_grade ? ` · Grade ${f.confidence_grade}` : ''}` : 'tested — held'}</span>
                    </div>
                    <div className="grid grid-cols-3 gap-x-4 gap-y-1 mt-2 text-[12px]">
                      <Kv k="r²" v={f.r2?.toFixed(2) ?? '—'} /><Kv k="r² out-of-sample" v={f.r2_oos?.toFixed(2) ?? '—'} /><Kv k="band cover 68%" v={f.band_cov68 != null ? `${Math.round(f.band_cov68 * 100)}%` : '—'} />
                      <Kv k="years" v={f.n_years ?? '—'} /><Kv k="baseline" v={f.baseline_from && f.baseline_to ? `${f.baseline_from}–${f.baseline_to}` : '—'} /><Kv k="SPEI scale" v={f.spei_scale ?? '—'} />
                    </div>
                    {f.source_note && <div className="text-[11px] text-[var(--color-faint)] mt-1.5">{f.source_note}</div>}
                  </div>
                ))}
              </div>}
          </Card>

          {/* projections */}
          {horizons.length > 0 && (
            <Card className="p-5">
              <div className="flex items-center gap-2 mb-3"><TrendingUp size={15} className="text-[var(--color-sky)]" /><span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">{pretty(s.top_hazard)} projection — mean hazard by warming path</span></div>
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase text-left"><th className="font-normal py-1 pr-3">Scenario</th>{horizons.map(h => <th key={h} className="font-normal px-2 text-center">{h}</th>)}</tr></thead>
                  <tbody>
                    {scenarios.map(sc => (
                      <tr key={sc} className="border-t border-[var(--color-line)]">
                        <td className="py-1.5 pr-3 text-[var(--color-ink)]">{scen(sc)}</td>
                        {horizons.map(h => { const p = at(sc, h); const v = p?.avg_score ?? null; const band = p && p.ci_lo != null && p.ci_hi != null ? `${Math.round(p.ci_lo)}–${Math.round(p.ci_hi)}` : null
                          return <td key={h} className="px-2 text-center mono align-top">
                            <div style={{ color: hz(v) }}>{v != null ? Math.round(v) : '·'}</div>
                            {band && <div className="text-[9px] text-[var(--color-faint)] leading-tight mt-0.5" title="CMIP6 across-model 68% band">{band}</div>}
                          </td> })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="text-[10px] text-[var(--color-faint)] mt-2">Downscaled CMIP6 ensemble; higher = more hazard on this crop's cells. Small figure = the across-model 68% band (model disagreement) — shown only where the ensemble projects a forward change, never on the current reading.</div>
            </Card>
          )}

          {/* adaptation */}
          {d.adaptation.length > 0 && (
            <Card className="p-5">
              <div className="flex items-center gap-2 mb-3"><ShieldAlert size={15} className="text-[var(--color-sky)]" /><span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Adaptation — what to do</span></div>
              {d.adaptation.map((a, i) => (
                <div key={i}>
                  <div className="text-[13px] font-medium mb-1" style={{ color: hz(80) }}>{a.label}</div>
                  <ul className="space-y-1">{a.actions.map((act, j) => <li key={j} className="text-[12px] text-[var(--color-mute)] flex gap-2"><span className="text-[var(--color-sky)]">·</span>{act}</li>)}</ul>
                </div>
              ))}
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function Kv({ k, v }: { k: string; v: React.ReactNode }) {
  return <div><div className="text-[10px] text-[var(--color-faint)]">{k}</div><div className="mono text-[var(--color-ink)]">{v}</div></div>
}
function Center({ children }: { children: React.ReactNode }) {
  return <div className="py-20 text-center text-[var(--color-faint)] text-sm">{children}</div>
}
