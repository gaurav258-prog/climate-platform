import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Minus, GitCompareArrows } from 'lucide-react'
import { api } from '../lib/api'
import { money } from '../lib/money'
import { Card, Lens, SectionHead } from './ui'
import { hazardLabel, bucketLabel } from '../lib/hazards'
import { DivergingBars, PairBars } from './Charts'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Said, plural } from './intake/parts'

// "Why did the numbers move?" — a filing's change against the prior one (the one it restates, or the previous period),
// read from both frozen filings (services/governance/filing_variance.py). A reviewer approves deltas, not absolutes.
// Identical data shows "no change"; a comparison that cannot be made says why in the catalogue's words.

interface D { now: number | null; prior: number | null; delta: number | null }
interface Mover { asset: string; value_eur: number | null; from_score: number; to_score: number; delta: number; from_bucket: string | null; to_bucket: string | null }
interface Entry { asset: string; value_eur: number | null; score: number | null; bucket: string | null; gone?: boolean }
interface Variance {
  supported: boolean; msg?: Message; prior_filing_id?: string; currency?: string
  basis?: { current: { period: string }; prior: { period: string } }
  headline?: { total_value: D; value_at_risk: D; pct_at_risk: D }
  at_risk_level?: { now: number | null; prior: number | null; changed: boolean; msg?: Message }
  by_hazard?: ({ hazard: string } & D)[]
  drivers?: { new_at_risk: Entry[]; left_at_risk: Entry[]; movers: Mover[] }
  counts?: { assets_now: number; assets_prior: number; added: number; removed: number }
}

// for a RISK figure, up is bad, down is good
const riskTone = (delta: number | null) => delta == null || delta === 0 ? 'var(--color-slate)' : delta > 0 ? 'var(--color-bad)' : 'var(--color-good)'
const ABOUT = [
  { heading: HEADING.shows, body: 'How this filing’s figures moved against the prior one: the book value, the value at risk and the share at risk, which hazards moved, and the assets behind the change.' },
  { heading: HEADING.read, body: 'For a risk figure, red is more risk and green is less. A change in your at-risk threshold between the two filings is flagged: part of the move is then the method, not the risk.' },
  { heading: HEADING.sources, body: 'Both frozen filings, in the currency they present in.' },
]

export default function FilingVariance({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['variance', filingId], queryFn: () => api.get<Variance>(`/v1/filings/${filingId}/variance`) })
  const d = q.data
  if (!d) return null
  if (!d.supported) {                  // a prior filing exists but cannot be compared: say why; otherwise nothing to show
    if (!d.prior_filing_id || !d.msg) return null
    return (
      <div className="flex items-center gap-2 flex-wrap px-1">
        <SectionHead icon={GitCompareArrows}>Change against the prior filing</SectionHead>
        <MessageLine m={d.msg} className="text-[12.5px] text-[var(--color-mute)]" />
      </div>)
  }
  const h = d.headline!
  // a filing's amounts are in its own (frozen) presentation currency — both filings share it, or there is no variance
  const ccy = d.currency ?? 'EUR'
  const cash = (n?: number | null) => money(n, ccy)
  const prior = d.basis?.prior.period ?? 'the prior filing'
  const moved = d.by_hazard!.filter(x => x.delta != null && x.delta !== 0)
  const material = h.total_value.delta !== 0 || h.value_at_risk.delta !== 0 || (d.drivers?.movers.length ?? 0) > 0 || (d.counts?.added ?? 0) > 0 || (d.counts?.removed ?? 0) > 0

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap px-1">
        <SectionHead icon={GitCompareArrows}>Change since {prior}</SectionHead>
        <InfoButton compact details={{ title: `Change since ${prior}`, sections: ABOUT }} />
        <Lens kind="insight" className="ml-auto" />
      </div>
      <Card className="p-4 space-y-4">
        {!material
          ? <div className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)]">No material change since {prior}
              <InfoButton compact details={{ title: 'No material change', sections: [{ heading: HEADING.shows, body: 'Same book, same scores. A restatement with unchanged data reconciles exactly.' }] }} /></div>
          : <>
              {d.at_risk_level?.msg && <div className="text-[12.5px]"><Said m={d.at_risk_level.msg} tone="warn" /></div>}
              <div className="grid grid-cols-3 gap-3">
                <Tile label="Book value" delta={h.total_value.delta} text={h.total_value.delta == null ? null : signed(h.total_value.delta, cash)} tone={h.total_value.delta ? 'var(--color-ink)' : 'var(--color-slate)'} />
                <Tile label="Value at risk" delta={h.value_at_risk.delta} text={h.value_at_risk.delta == null ? null : signed(h.value_at_risk.delta, cash)} tone={riskTone(h.value_at_risk.delta)} />
                <Tile label="Share at risk" delta={h.pct_at_risk.delta} text={h.pct_at_risk.delta == null ? null : signed(h.pct_at_risk.delta, n => `${n} points`)} tone={riskTone(h.pct_at_risk.delta)} />
              </div>
              {(d.counts!.added > 0 || d.counts!.removed > 0) && (
                <div className="flex gap-1.5 flex-wrap">
                  {d.counts!.added > 0 && <StatusChip tone="neutral" label={`${plural(d.counts!.added, 'asset')} added`} />}
                  {d.counts!.removed > 0 && <StatusChip tone="neutral" label={`${plural(d.counts!.removed, 'asset')} removed`} />}
                </div>)}
              {h.value_at_risk.prior != null && h.value_at_risk.now != null && (
                <div>
                  <div className="text-[12px] text-[var(--color-mute)] mb-1.5">Value at risk</div>
                  <PairBars prior={h.value_at_risk.prior} now={h.value_at_risk.now} format={cash} labels={[prior, d.basis?.current.period ?? 'now']} />
                </div>)}
              {moved.length > 0 && (
                <div>
                  <div className="text-[12px] text-[var(--color-mute)] mb-1.5">Exposure moved, by hazard</div>
                  <DivergingBars data={moved.slice(0, 6).map(x => ({ label: hazardLabel(x.hazard), value: x.delta as number }))} format={cash} />
                </div>)}
              <div className="grid sm:grid-cols-2 gap-4">
                {d.drivers!.new_at_risk.length > 0 && (
                  <Drivers title="Newly at risk" tone="var(--color-bad)" rows={d.drivers!.new_at_risk.slice(0, 5).map(e => ({ name: e.asset, right: cash(e.value_eur), chip: bucketLabel(e.bucket) }))} />)}
                {d.drivers!.movers.length > 0 && (
                  <Drivers title="Biggest score moves" tone="var(--color-warn)" rows={d.drivers!.movers.slice(0, 5).map(m => ({ name: m.asset, right: `${m.from_score} → ${m.to_score}`, chip: m.delta > 0 ? `+${m.delta}` : `${m.delta}` }))} />)}
              </div>
            </>}
      </Card>
    </div>
  )
}

const signed = (n: number, f: (n: number) => string) => n === 0 ? 'No change' : `${n > 0 ? '+' : '−'}${f(Math.abs(n))}`

function Tile({ label, delta, text, tone }: { label: string; delta: number | null; text: string | null; tone: string }) {
  const Icon = delta == null || delta === 0 ? Minus : delta > 0 ? TrendingUp : TrendingDown
  return (
    <div className="rounded-lg border border-[var(--color-line-2)] px-3 py-2.5">
      <div className="text-[12px] text-[var(--color-mute)]">{label}</div>
      <div className="mt-1 flex items-center gap-1.5 display text-[18px] tabular-nums" style={{ color: tone }}>
        <Icon size={14} />{text ?? 'Not comparable'}
      </div>
    </div>
  )
}

function Drivers({ title, tone, rows }: { title: string; tone: string; rows: { name: string; right: string; chip: string }[] }) {
  return (
    <div>
      <div className="text-[12px] mb-1.5 inline-flex items-center gap-1.5" style={{ color: tone }}><span className="w-2 h-2 rounded-full" style={{ background: tone }} />{title}</div>
      <div className="space-y-1">
        {rows.map((r, i) => (
          <div key={i} className="flex items-center gap-2 text-[12.5px]">
            <span className="min-w-0 flex-1 truncate text-[var(--color-ink)]">{r.name}</span>
            <StatusChip tone="neutral" label={r.chip} />
            <span className="tabular-nums text-[var(--color-mute)] w-24 text-right">{r.right}</span>
          </div>))}
      </div>
    </div>
  )
}
