import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { balance, flow } from '../lib/money'
import { Card, SectionHead, StatGrid, type StatItem } from './ui'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import MethodGap from './MethodGap'

// The bank's physical climate expected loss, next 12 months and over each loan's remaining life, on the bank's stated
// method (services/intelligence/expected_loss.py). The method, in the server's own words, sits behind "How it's
// calculated"; a loan without a maturity on the loan tape is named, never given an assumed one.

interface ELAsset {
  entity_id: string; entity_name: string; ead_eur: number; annual_el_eur: number | null; lifetime_el_eur: number | null
  p_event: number | null; damage_ratio: number | null; tenor_years: number | null; el_pct_of_ead: number | null
}
interface ELResp {
  annual_el_eur: number | null; lifetime_el_eur: number | null; annual_el_bps: number | null; lifetime_el_bps: number | null
  n_assets: number; assets: ELAsset[]; gap?: string; maturity_message?: Message; basis_message?: Message
}

const share = (n: number | null) => (n == null ? '—' : `${(n * 100).toFixed(n < 0.1 ? 1 : 0)}%`)
const bps = (n: number | null) => (n == null ? undefined : `${n} basis points of exposure`)

export default function ExpectedLossCard({ prefix, scenario, scenarioLabel }: { prefix: string; scenario: string; scenarioLabel: string }) {
  const q = useQuery({
    queryKey: ['expected-loss', prefix, scenario],
    queryFn: () => api.get<ELResp>(`/v1/${prefix}/expected-loss?scenario=${scenario}`),
  })
  const d = q.data
  if (!d) return null
  if (d.annual_el_eur == null && d.gap) return <MethodGap gap={d.gap} what="Climate expected loss" />
  const m = d.basis_message?.detail ?? {}
  const details = {
    title: 'Climate expected loss',
    sections: [
      { heading: HEADING.shows, body: `What physical climate events are expected to cost your loan book under ${scenarioLabel}: in the next 12 months, and over each loan’s remaining life.` },
      ...(m.what ? [{ heading: 'How it’s calculated', body: m.what }] : []),
      ...(m.why ? [{ heading: HEADING.limits, body: m.why }] : []),
    ],
  }
  const metrics: StatItem[] = [
    { label: 'Next 12 months', value: flow(d.annual_el_eur), sub: bps(d.annual_el_bps) },
    { label: 'Over the remaining loan life', value: balance(d.lifetime_el_eur), sub: bps(d.lifetime_el_bps), accent: 'var(--color-warn)' },
  ]
  const th = 'px-3 py-2 font-medium text-right'
  const td = 'px-3 py-1.5 text-right tabular-nums text-[var(--color-mute)]'
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-[var(--color-line)] flex flex-wrap items-center justify-between gap-3">
        <SectionHead hint={scenarioLabel}>Climate expected loss</SectionHead>
        <InfoButton details={details} label="How it’s calculated" />
      </div>
      <div className="px-5 py-4 border-b border-[var(--color-line)] space-y-3">
        <StatGrid items={metrics} cols={2} />
        {d.maturity_message && <div className="text-[12.5px] text-[var(--color-warn)]"><MessageLine m={d.maturity_message} /></div>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[11px] text-[var(--color-faint)]">
              <th className="px-5 py-2 font-medium">Largest expected losses</th>
              <th className={th}>Balance</th>
              <th className={th}>Event chance a year</th>
              <th className={th}>Damage if hit</th>
              <th className={th}>Years left</th>
              <th className={th}>Lifetime loss</th>
              <th className="px-5 py-2 font-medium text-right">Of the balance</th>
            </tr>
          </thead>
          <tbody>
            {d.assets.slice(0, 8).map(a => (
              <tr key={a.entity_id} className="border-t border-[var(--color-line)]">
                <td className="px-5 py-1.5 text-[var(--color-ink)]">{a.entity_name}</td>
                <td className={td}>{balance(a.ead_eur)}</td>
                <td className={td}>{share(a.p_event)}</td>
                <td className={td}>{share(a.damage_ratio)}</td>
                <td className={td}>{a.tenor_years ?? '—'}</td>
                <td className={`${td} text-[var(--color-ink)]`}>{balance(a.lifetime_el_eur)}</td>
                <td className="px-5 py-1.5 text-right tabular-nums" style={{ color: (a.el_pct_of_ead ?? 0) >= 20 ? 'var(--color-bad)' : 'var(--color-mute)' }}>{a.el_pct_of_ead == null ? '—' : `${a.el_pct_of_ead}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
