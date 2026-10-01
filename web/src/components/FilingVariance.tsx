import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Minus, GitCompareArrows } from 'lucide-react'
import { api } from '../lib/api'
import { money } from '../lib/money'
import { Card, Lens } from './ui'
import { hazardLabel, bucketLabel } from '../lib/hazards'
import { DivergingBars, PairBars } from './Charts'

// "Why did the numbers move?" — decomposes a filing's change vs the prior version (the one it restates, or
// the previous period). A reviewer approves deltas, not absolutes. Honest: identical data → "no change".

interface D { now: number | null; prior: number | null; delta: number | null }
interface Mover { asset: string; value_eur: number | null; from_score: number; to_score: number; delta: number; from_bucket: string | null; to_bucket: string | null }
interface Entry { asset: string; value_eur: number | null; score: number | null; bucket: string | null; gone?: boolean }
interface Variance {
  supported: boolean; message?: string; prior_filing_id?: string; currency?: string
  basis?: { current: { period: string }; prior: { period: string } }
  headline?: { total_value: D; value_at_risk: D; pct_at_risk: D }
  at_risk_level?: { now: number | null; prior: number | null; changed: boolean; gap?: string }
  by_hazard?: ({ hazard: string } & D)[]
  drivers?: { new_at_risk: Entry[]; left_at_risk: Entry[]; movers: Mover[] }
  counts?: { assets_now: number; assets_prior: number; added: number; removed: number }
}

// for a RISK figure, up is bad (red), down is good (green)
const riskTone = (delta: number | null) => delta == null ? '#64748b' : delta > 0 ? '#fb7185' : delta < 0 ? '#34d399' : '#64748b'

export default function FilingVariance({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['variance', filingId], queryFn: () => api.get<Variance>(`/v1/filings/${filingId}/variance`) })
  const d = q.data
  if (!d || !d.supported) return null   // no prior to compare, or unsupported framework — show nothing
  const h = d.headline!
  // a filing's amounts are in its own (frozen) presentation currency — both filings share it, or there is no variance
  const ccy = d.currency ?? 'EUR'
  const eur = (n?: number | null) => money(n, ccy)
  const material = h.total_value.delta !== 0 || h.value_at_risk.delta !== 0 || (d.drivers?.movers.length ?? 0) > 0 || (d.counts?.added ?? 0) > 0 || (d.counts?.removed ?? 0) > 0

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] flex items-center gap-1.5">
          <GitCompareArrows size={12} /> Change vs {d.basis?.prior.period}
        </div>
        <Lens kind="insight" />
      </div>
      <Card className="p-4 space-y-3">
        {!material
          ? <p className="text-[12.5px] text-[var(--color-mute)]">No material change since {d.basis?.prior.period} — same book, same scores. A restatement with unchanged data reconciles exactly.</p>
          : <>
              {d.at_risk_level?.gap
                ? <p className="text-[11.5px] text-[var(--color-warn)]">At-risk figures not compared — {d.at_risk_level.gap} for {d.at_risk_level.now == null ? 'this filing' : 'the prior filing'}.</p>
                : d.at_risk_level?.changed && <p className="text-[11.5px] text-[var(--color-warn)]">The stated at-risk level changed from {d.at_risk_level.prior} to {d.at_risk_level.now} — part of the value-at-risk movement is the method, not the risk.</p>}
              <div className="grid grid-cols-3 gap-3">
                <Tile label="Book value" delta={h.total_value.delta} now={h.total_value.now} risk={false} ccy={ccy} />
                <Tile label="Value at risk" delta={h.value_at_risk.delta} now={h.value_at_risk.now} risk ccy={ccy} />
                <PctTile label="Share at risk" now={h.pct_at_risk.now} delta={h.pct_at_risk.delta} />
              </div>

              {(d.counts!.added > 0 || d.counts!.removed > 0) && (
                <div className="text-[11.5px] text-[var(--color-mute)]">
                  {d.counts!.added > 0 && <span>{d.counts!.added} asset{d.counts!.added === 1 ? '' : 's'} added</span>}
                  {d.counts!.added > 0 && d.counts!.removed > 0 && <span> · </span>}
                  {d.counts!.removed > 0 && <span>{d.counts!.removed} removed</span>}
                </div>
              )}

              {h.value_at_risk.prior != null && h.value_at_risk.now != null && (
                <div>
                  <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Value at risk · prior vs now</div>
                  <PairBars prior={h.value_at_risk.prior} now={h.value_at_risk.now} format={eur} />
                </div>
              )}

              {d.by_hazard!.filter(x => x.delta != null && x.delta !== 0).length > 0 && (
                <div>
                  <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Exposure shift by hazard (red = more risk)</div>
                  <DivergingBars data={d.by_hazard!.filter(x => x.delta != null && x.delta !== 0).slice(0, 6).map(x => ({ label: hazardLabel(x.hazard), value: x.delta as number }))} format={eur} />
                </div>
              )}

              {d.drivers!.new_at_risk.length > 0 && (
                <Driver title="Newly at risk" tone="#fb7185"
                  rows={d.drivers!.new_at_risk.map(e => `${e.asset} · ${eur(e.value_eur)} (${bucketLabel(e.bucket)})`)} />
              )}
              {d.drivers!.movers.length > 0 && (
                <Driver title="Biggest score movers" tone="#e8b24c"
                  rows={d.drivers!.movers.slice(0, 5).map(m => `${m.asset}: ${m.from_score}→${m.to_score} (${m.delta > 0 ? '+' : ''}${m.delta})`)} />
              )}
            </>}
      </Card>
    </div>
  )
}

function Tile({ label, delta, risk, ccy }: { label: string; delta: number | null; now: number | null; risk: boolean; ccy: string }) {
  const tone = risk ? riskTone(delta) : (delta === 0 ? '#64748b' : 'var(--color-ink)')
  const Icon = delta == null ? Minus : delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus
  return (
    <div>
      <div className="flex items-center gap-1 text-[15px] mono" style={{ color: tone }}>
        <Icon size={13} />{delta == null ? 'not comparable' : delta === 0 ? '±0' : `${delta > 0 ? '+' : ''}${money(delta, ccy)}`}
      </div>
      <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-1">{label}</div>
    </div>
  )
}

function PctTile({ label, delta }: { label: string; now: number | null; delta: number | null }) {
  const tone = riskTone(delta)
  const Icon = delta == null ? Minus : delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus
  return (
    <div>
      <div className="flex items-center gap-1 text-[15px] mono" style={{ color: tone }}>
        <Icon size={13} />{delta == null ? 'not comparable' : delta === 0 ? '±0' : `${delta > 0 ? '+' : ''}${delta}pp`}
      </div>
      <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-1">{label}</div>
    </div>
  )
}

function Driver({ title, tone, rows }: { title: string; tone: string; rows: string[] }) {
  return (
    <div>
      <div className="mono text-[10px] uppercase tracking-wide mb-1" style={{ color: tone }}>{title}</div>
      <ul className="space-y-0.5">
        {rows.map((r, i) => <li key={i} className="text-[12px] text-[var(--color-mute)]">{r}</li>)}
      </ul>
    </div>
  )
}
