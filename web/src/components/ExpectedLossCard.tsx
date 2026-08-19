import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Card } from './ui'

interface ELAsset {
  entity_id: string; entity_name: string; ead_eur: number; annual_el_eur: number; lifetime_el_eur: number
  p_event: number; damage_ratio: number; tenor_years: number; tenor_source: string; hazard: string | null; el_pct_of_ead: number
}
interface ELResp {
  total_ead_eur: number; annual_el_eur: number; lifetime_el_eur: number; annual_el_bps: number; lifetime_el_bps: number
  n_assets: number; maturity_fed: number; maturity_assumed: number; default_tenor_years: number; assets: ELAsset[]; basis: string
}

const eur = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const pct = (n: number) => `${(n * 100).toFixed(n < 0.1 ? 1 : 0)}%`

export default function ExpectedLossCard({ prefix, scenario, scenarioLabel }: { prefix: string; scenario: string; scenarioLabel: string }) {
  const q = useQuery({
    queryKey: ['expected-loss', prefix, scenario],
    queryFn: () => api.get<ELResp>(`/v1/${prefix}/expected-loss?scenario=${scenario}`),
  })
  const d = q.data
  if (!d) return null

  return (
    <Card className="p-0 overflow-hidden mt-4">
      <div className="px-5 py-3.5 border-b border-[var(--color-line)] flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">Climate expected loss · {scenarioLabel} · the € a physical event is expected to cost this book</div>
          <div className="text-[12.5px] text-[var(--color-mute)] mt-1">Exposure × chance of an event each year × how much value it impairs — accumulated over each loan&rsquo;s remaining life.</div>
        </div>
        <div className="mono text-[10px] text-[var(--color-faint)] px-2 py-1 rounded border border-[var(--color-line)]" title="Residual maturity comes from the loan tape where connected; otherwise a disclosed default tenor is assumed.">
          {d.maturity_fed}/{d.maturity_fed + d.maturity_assumed} loans use fed maturity{d.maturity_assumed ? ` · rest assume ${d.default_tenor_years}y` : ''}
        </div>
      </div>

      {/* headline: annual vs lifetime */}
      <div className="grid grid-cols-2 divide-x divide-[var(--color-line)] border-b border-[var(--color-line)]">
        <div className="px-5 py-4">
          <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">Expected loss · next 12 months</div>
          <div className="text-[26px] leading-tight text-[var(--color-ink)] mt-1" style={{ fontFamily: 'Georgia,serif' }}>{eur(d.annual_el_eur)}</div>
          <div className="mono text-[11px] text-[var(--color-mute)] mt-0.5 tabular-nums">{d.annual_el_bps} bps of exposure</div>
        </div>
        <div className="px-5 py-4">
          <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">Expected loss · over remaining loan life</div>
          <div className="text-[26px] leading-tight mt-1" style={{ fontFamily: 'Georgia,serif', color: 'var(--color-warn)' }}>{eur(d.lifetime_el_eur)}</div>
          <div className="mono text-[11px] text-[var(--color-mute)] mt-0.5 tabular-nums">{d.lifetime_el_bps} bps of exposure · maturity-matched</div>
        </div>
      </div>

      {/* top contributors */}
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">
              <th className="px-5 py-2 font-medium">Exposure</th>
              <th className="px-3 py-2 font-medium text-right">EAD</th>
              <th className="px-3 py-2 font-medium text-right" title="Chance a physical event hits this exposure in a year">Event / yr</th>
              <th className="px-3 py-2 font-medium text-right" title="Collateral-value impairment if an event hits">Severity</th>
              <th className="px-3 py-2 font-medium text-right" title="Remaining life of the loan; 'fed' from the loan tape, else assumed">Tenor</th>
              <th className="px-3 py-2 font-medium text-right">Lifetime EL</th>
              <th className="px-5 py-2 font-medium text-right">% of EAD</th>
            </tr>
          </thead>
          <tbody>
            {d.assets.slice(0, 8).map(a => (
              <tr key={a.entity_id} className="border-t border-[var(--color-line)]">
                <td className="px-5 py-1.5 text-[var(--color-ink)]">{a.entity_name}</td>
                <td className="px-3 py-1.5 text-right mono tabular-nums text-[var(--color-mute)]">{eur(a.ead_eur)}</td>
                <td className="px-3 py-1.5 text-right mono tabular-nums text-[var(--color-mute)]">{pct(a.p_event)}</td>
                <td className="px-3 py-1.5 text-right mono tabular-nums text-[var(--color-mute)]">{pct(a.damage_ratio)}</td>
                <td className="px-3 py-1.5 text-right mono tabular-nums text-[var(--color-mute)]">{a.tenor_years}y<span className="text-[var(--color-faint)] text-[9px]">·{a.tenor_source === 'fed' ? 'fed' : 'ass.'}</span></td>
                <td className="px-3 py-1.5 text-right mono tabular-nums text-[var(--color-ink)]">{eur(a.lifetime_el_eur)}</td>
                <td className="px-5 py-1.5 text-right mono tabular-nums" style={{ color: a.el_pct_of_ead >= 20 ? 'var(--color-bad,#e0574a)' : 'var(--color-mute)' }}>{a.el_pct_of_ead}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-5 py-2.5 mono text-[9.5px] text-[var(--color-faint)] leading-relaxed border-t border-[var(--color-line)]">{d.basis}</div>
    </Card>
  )
}
