import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Minus, GitCompareArrows } from 'lucide-react'
import { api } from '../lib/api'
import { Card } from './ui'
import { hazardLabel } from '../lib/hazards'

// "Why did the numbers move?" — decomposes a filing's change vs the prior version (the one it restates, or
// the previous period). A reviewer approves deltas, not absolutes. Honest: identical data → "no change".

interface D { now: number; prior: number; delta: number }
interface Mover { asset: string; value_eur: number | null; from_score: number; to_score: number; delta: number; from_bucket: string | null; to_bucket: string | null }
interface Entry { asset: string; value_eur: number | null; score: number | null; bucket: string | null; gone?: boolean }
interface Variance {
  supported: boolean; message?: string; prior_filing_id?: string
  basis?: { current: { period: string }; prior: { period: string } }
  headline?: { total_value: D; value_at_risk: D; pct_at_risk: { now: number; prior: number; delta: number } }
  by_hazard?: ({ hazard: string } & D)[]
  drivers?: { new_at_risk: Entry[]; left_at_risk: Entry[]; movers: Mover[] }
  counts?: { assets_now: number; assets_prior: number; added: number; removed: number }
}

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const signedEur = (n: number) => (n > 0 ? '+' : n < 0 ? '−' : '±') + eur(Math.abs(n)).replace('€', '€')
// for a RISK figure, up is bad (red), down is good (green)
const riskTone = (delta: number) => delta > 0 ? '#fb7185' : delta < 0 ? '#34d399' : '#64748b'

export default function FilingVariance({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['variance', filingId], queryFn: () => api.get<Variance>(`/v1/filings/${filingId}/variance`) })
  const d = q.data
  if (!d || !d.supported) return null   // no prior to compare, or unsupported framework — show nothing
  const h = d.headline!
  const material = h.total_value.delta !== 0 || h.value_at_risk.delta !== 0 || (d.drivers?.movers.length ?? 0) > 0 || (d.counts?.added ?? 0) > 0 || (d.counts?.removed ?? 0) > 0

  return (
    <div>
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2 flex items-center gap-1.5">
        <GitCompareArrows size={12} /> Change vs {d.basis?.prior.period}
      </div>
      <Card className="p-4 space-y-3">
        {!material
          ? <p className="text-[12.5px] text-[var(--color-mute)]">No material change since {d.basis?.prior.period} — same book, same scores. A restatement with unchanged data reconciles exactly.</p>
          : <>
              <div className="grid grid-cols-3 gap-3">
                <Tile label="Book value" delta={h.total_value.delta} now={h.total_value.now} risk={false} />
                <Tile label="Value at risk" delta={h.value_at_risk.delta} now={h.value_at_risk.now} risk />
                <PctTile label="Share at risk" now={h.pct_at_risk.now} delta={h.pct_at_risk.delta} />
              </div>

              {(d.counts!.added > 0 || d.counts!.removed > 0) && (
                <div className="text-[11.5px] text-[var(--color-mute)]">
                  {d.counts!.added > 0 && <span>{d.counts!.added} asset{d.counts!.added === 1 ? '' : 's'} added</span>}
                  {d.counts!.added > 0 && d.counts!.removed > 0 && <span> · </span>}
                  {d.counts!.removed > 0 && <span>{d.counts!.removed} removed</span>}
                </div>
              )}

              {d.by_hazard!.filter(x => x.delta !== 0).length > 0 && (
                <div>
                  <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Exposure shift by hazard</div>
                  <div className="space-y-1">
                    {d.by_hazard!.filter(x => x.delta !== 0).slice(0, 5).map(x => (
                      <div key={x.hazard} className="flex items-center justify-between text-[12px]">
                        <span className="text-[var(--color-mute)]">{hazardLabel(x.hazard)}</span>
                        <span className="mono" style={{ color: riskTone(x.delta) }}>{signedEur(x.delta)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {d.drivers!.new_at_risk.length > 0 && (
                <Driver title="Newly at risk" tone="#fb7185"
                  rows={d.drivers!.new_at_risk.map(e => `${e.asset} · ${eur(e.value_eur)} (${e.bucket})`)} />
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

function Tile({ label, delta, risk }: { label: string; delta: number; now: number; risk: boolean }) {
  const tone = risk ? riskTone(delta) : (delta === 0 ? '#64748b' : 'var(--color-ink)')
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus
  return (
    <div>
      <div className="flex items-center gap-1 text-[15px] mono" style={{ color: tone }}>
        <Icon size={13} />{delta === 0 ? '±0' : signedEur(delta)}
      </div>
      <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-1">{label}</div>
    </div>
  )
}

function PctTile({ label, delta }: { label: string; now: number; delta: number }) {
  const tone = riskTone(delta)
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus
  return (
    <div>
      <div className="flex items-center gap-1 text-[15px] mono" style={{ color: tone }}>
        <Icon size={13} />{delta === 0 ? '±0' : `${delta > 0 ? '+' : ''}${delta}pp`}
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
