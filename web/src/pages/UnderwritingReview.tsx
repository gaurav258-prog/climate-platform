import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck, History, ShieldAlert } from 'lucide-react'
import { api } from '../lib/api'
import { Eyebrow, Card } from '../components/ui'

// Underwriting review — the insurance product line on top of Realized Exposure. For the carrier's own book:
// the real events that have already crossed each policy (observed loss experience), plus — for perils we hold
// an observed catalogue for — whether the observed hit-rate matches the modelled return period the policy is
// priced on. The empirical check behind a parametric-trigger book. Honest about coverage.

interface REvent { kind: string; name?: string; year: number | null; severity: string; closest_km?: number }
interface Freq {
  peril: string; catalogue: string; observed_events: number; observed_window_years: number
  modelled_return_period_years: number; expected_events_in_window: number
  implied_observed_return_period_years: number | null; observed_vs_modelled_ratio: number | null; verdict: string
}
interface Policy {
  policy_id: string; policy_name: string; region: string; country: string
  sum_insured_eur: number | null; headline_hazard: string; headline_bucket: string
  gross_premium_eur: number | null; n_observed_events: number; n_storm: number; n_quake: number
  events: REvent[]; frequency: Freq | null
}
interface Review {
  available: boolean; reason?: string; headline?: string
  n_policies: number; n_policies_hit: number; n_events_observed: number; sum_insured_hit_eur: number
  frequency: {
    n_validatable: number; n_under_priced: number; n_conservative: number
    n_priced_against_uncatalogued_peril: number
    catalogue_windows: { storm_years: number | null; seismic_years: number | null }
    under_priced: (Freq & { policy_name: string; region: string; sum_insured_eur: number | null })[]
  }
  most_exposed: Policy[]; note?: string
}

const eur = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`

function Stat({ n, label, tone }: { n: string; label: string; tone?: string }) {
  return (
    <div>
      <div className="display text-[26px] font-semibold tabular-nums" style={{ color: tone || 'var(--color-ink)' }}>{n}</div>
      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mt-0.5">{label}</div>
    </div>
  )
}

export default function UnderwritingReview() {
  const q = useQuery({ queryKey: ['underwriting-review'], queryFn: () => api.get<Review>('/v1/realized-exposure/underwriting-review') })
  const d = q.data

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Assess · insurance underwriting</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Underwriting review</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Your policies are priced against a <em>modelled</em> return period. Tellumen holds the <em>observed</em> record — the real storms and earthquakes that have already crossed each risk. Here they are, per policy, with a frequency check where we hold an observed catalogue for the priced peril.
        </p>
      </div>

      {q.isLoading && <Card className="p-5 text-[13px] text-[var(--color-mute)]">Building the review…</Card>}
      {d && !d.available && (
        <Card className="p-5 text-[13px] text-[var(--color-mute)]">
          {d.reason === 'insurance_only' ? 'The underwriting review is an insurance deliverable — available on an insurer workspace.' : 'Not available.'}
        </Card>
      )}

      {d && d.available && (
        <>
          <Card className="p-5" style={{ borderColor: 'var(--color-blued)', background: 'linear-gradient(180deg,#0e2338,var(--color-panel))' }}>
            <div className="flex items-center gap-2 mb-1"><History size={15} className="text-[var(--color-sky)]" />
              <span className="mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-sky)]">Observed loss experience · this book</span></div>
            <h2 className="display text-[22px] font-semibold text-[#F4EFE6] leading-snug max-w-3xl">{d.headline}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-5 mt-4">
              <Stat n={`${d.n_policies_hit}`} label="policies already hit" tone="#E8B24C" />
              <Stat n={`${d.n_events_observed}`} label="real crossings" />
              <Stat n={eur(d.sum_insured_hit_eur)} label="sum insured at hit sites" />
              <Stat n={`${d.frequency.n_validatable}`} label="frequency-validatable" />
            </div>
          </Card>

          {/* Frequency validation */}
          <Card className="p-5">
            <div className="flex items-center gap-1.5 mb-1"><ClipboardCheck size={15} className="text-[var(--color-sky)]" />
              <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Observed vs modelled frequency</span></div>
            <p className="text-[12.5px] text-[var(--color-mute)] max-w-3xl mb-3">
              For perils Tellumen holds an observed catalogue for (storm, seismic), we compare the real hit-rate at each location to the modelled return period it is priced on.
            </p>
            <div className="flex flex-wrap gap-6">
              <Stat n={`${d.frequency.n_under_priced}`} label="observed > priced (review)" tone={d.frequency.n_under_priced ? '#D23B3B' : undefined} />
              <Stat n={`${d.frequency.n_conservative}`} label="observed < priced" tone="#7BBF8F" />
              <Stat n={`${d.frequency.n_validatable}`} label="validatable" />
              <Stat n={`${d.frequency.n_priced_against_uncatalogued_peril}`} label="peril not yet catalogued" tone="#6d8299" />
            </div>
            {d.frequency.under_priced.length > 0 ? (
              <div className="mt-4 divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
                {d.frequency.under_priced.map((f, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-[12.5px]">
                    <span className="font-semibold text-[var(--color-ink)]">{f.policy_name}</span>
                    <span className="mono text-[10.5px] text-[var(--color-faint)]">{f.region}</span>
                    <span className="flex-1 min-w-0" />
                    <span className="mono text-[11px] text-[var(--color-mute)] tabular-nums">
                      observed ~1-in-{f.implied_observed_return_period_years} vs priced 1-in-{f.modelled_return_period_years}
                    </span>
                    <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: '#D23B3B22', color: '#D23B3B' }}>{f.observed_vs_modelled_ratio}× priced freq</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-3 text-[12px] text-[var(--color-mute)]">
                No policy in this book shows an observed hit-rate materially above its priced return period. Catalogue windows: storm {d.frequency.catalogue_windows.storm_years} yr · seismic {d.frequency.catalogue_windows.seismic_years} yr.
              </div>
            )}
          </Card>

          {/* Most physically-exposed policies */}
          <Card className="p-5">
            <div className="flex items-center gap-1.5 mb-1"><ShieldAlert size={15} className="text-[var(--color-warn)]" />
              <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Most physically-exposed policies · real event history</span></div>
            <p className="text-[12.5px] text-[var(--color-mute)] max-w-3xl mb-3">The underwriting attention list — policies whose locations have taken the most real catalogued events. A data point the file does not otherwise hold.</p>
            {d.most_exposed.length === 0
              ? <div className="text-[12.5px] text-[var(--color-mute)]">No catalogued storm or earthquake has crossed any located policy.</div>
              : <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
                  {d.most_exposed.map((p) => (
                    <div key={p.policy_id} className="py-2.5">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
                        <span className="font-semibold text-[var(--color-ink)]">{p.policy_name}</span>
                        <span className="mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)]">{p.headline_hazard}</span>
                        <span className="flex-1 min-w-0" />
                        <span className="mono text-[11px] text-[var(--color-ink)] tabular-nums">{p.n_observed_events} event{p.n_observed_events === 1 ? '' : 's'}</span>
                        <span className="mono text-[11px] text-[var(--color-mute)] tabular-nums">{eur(p.sum_insured_eur)} SI</span>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 pl-0.5">
                        {p.events.slice(0, 4).map((e, i) => (
                          <span key={i} className="mono text-[10.5px] text-[var(--color-faint)]">
                            {e.kind === 'earthquake' ? '⊕' : '🌀'} {e.name} {e.year ?? ''} · {e.closest_km}km
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>}
          </Card>

          <div className="mono text-[9.5px] text-[var(--color-faint)]">{d.note}</div>
        </>
      )}
    </div>
  )
}
