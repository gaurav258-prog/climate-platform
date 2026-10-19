import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck, ShieldAlert } from 'lucide-react'
import { api } from '../lib/api'
import { balance } from '../lib/money'
import { pressable } from '../lib/pressable'
import { Card, PageHeader, SectionHead, StatGrid } from '../components/ui'
import { HEADING, InfoButton, MessageLine } from '../components/Details'
import ReviewTabs from '../components/ReviewTabs'
import MethodGap from '../components/MethodGap'
import AssetDrawer, { type DrawerCfg } from '../components/AssetDrawer'
import { Chip, EventDialog, KindIcon, MessageInfo, eventTitle, sourcesBody } from '../components/observed/Observed'
import type { Message, ObservedEvent, Source } from '../components/observed/types'

// Underwriting review, to the UI standard (2026-10-16): the observed record at each policy, and — for every peril a
// policy is priced on that has an observed catalogue — the crossings beside the number its priced return period
// expects. Figures and bars on the main screen; the definitions, the rule and every reason in the server's catalogue
// words (codes realized.review.*). A flag is a prompt to check a price, never a finding.

// the policy record is the same drawer Portfolio opens (/v1/insurance/policy/{id})
const INSURER_CFG: DrawerCfg = {
  prefix: 'insurance', itemKey: 'policy', nameKey: 'policy_name', valueKey: 'sum_insured_eur',
  typeKey: 'policy_type', auditKey: 'audit', overrideMode: 'trigger',
}

type Verdict = 'more_often' | 'in_line' | 'less_often'
interface Check {
  peril: string; peril_name: string; catalogue: string; observed_events: number; window_years: number
  priced_return_period_years: number; expected_events: number; ratio: number
  verdict: Verdict | null; verdict_name: string | null; no_verdict: Message | null
}
interface Flag extends Check { policy_id: string; policy_name: string; region: string; sum_insured_eur: number | null }
interface Policy {
  policy_id: string; policy_name: string; region: string; sum_insured_eur: number | null
  n_observed_events: number; events: ObservedEvent[]; checks: Check[]
}
interface PerilRow { peril: string; peril_name: string; n_checks: number; n_more_often: number; n_in_line: number; n_less_often: number; n_no_verdict: number }
interface Review {
  available: boolean; message?: Message
  n_policies: number; n_policies_hit: number; n_events_observed: number; sum_insured_hit_eur: number
  frequency: {
    n_checks: number; n_policies_checked: number; n_more_often: number; n_in_line: number; n_less_often: number; n_no_verdict: number
    n_unpriced: number; n_no_return_period: number; n_uncatalogued: number; by_peril: PerilRow[]; flagged: Flag[]
  }
  most_exposed: Policy[]; sources: Source[]; verdict_names: Record<Verdict | 'none', string>
  definition: { storm_radius_km: number; quake_radius_km: number; min_magnitude: number; verdict_tolerance: number | null; gap: string | null }
  messages: { crossed: Message; check: Message; rule: Message | null; uncatalogued: Message; unpriced: Message; no_return_period: Message }
}

const VERDICT_COLOR: Record<Verdict | 'none', string> = {
  more_often: 'var(--color-warn)', in_line: 'var(--color-good)', less_often: 'var(--color-sky)', none: 'var(--color-line-2)',
}
const ABOUT = [
  { heading: HEADING.shows, body: 'The storms and earthquakes the observed catalogues recorded at each policy’s location, and, for each peril a policy is priced on that has such a catalogue, the crossings beside the number the priced return period expects over the same years.' },
  { heading: HEADING.read, body: 'Crossings are fact. The priced return period is your stated method. A crossing is broader than a damaging event, so a flag is a prompt to check the priced frequency, not a finding that a policy is mispriced.' },
  { heading: HEADING.limits, body: 'Only tropical cyclones and earthquakes have an observed catalogue here; a policy priced only on other perils shows its crossings without a check. The earthquake record is short, so one event moves a check a long way.' },
]

export default function UnderwritingReview() {
  const q = useQuery({ queryKey: ['underwriting-review'], queryFn: () => api.get<Review>('/v1/realized-exposure/underwriting-review') })
  const d = q.data
  const [drawerId, setDrawerId] = useState<string | null>(null)
  return (
    <div className="fadeup space-y-6 max-w-5xl">
      <ReviewTabs />
      <PageHeader eyebrow="Review · underwriting" title="Underwriting review" lead="The observed record at each policy, beside its price."
        about={d?.sources?.length ? [...ABOUT, { heading: HEADING.sources, body: sourcesBody(d.sources) }] : ABOUT} />
      {q.isLoading && <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div>}
      {q.isError && <div className="text-[12.5px] text-[var(--color-warn)]">The review could not be loaded. Try again shortly.</div>}
      {d && !d.available && d.message && <Card className="p-5"><MessageLine m={d.message} className="text-[13px] text-[var(--color-mute)]" /></Card>}
      {d?.available && (
        <>
          <StatGrid cols={4} items={[
            { label: 'Policies crossed', value: `${d.n_policies_hit} of ${d.n_policies}`, accent: d.n_policies_hit ? 'var(--color-sky)' : undefined },
            { label: 'Crossings', value: d.n_events_observed, sub: 'storms and earthquakes' },
            { label: 'Sum insured at crossed sites', value: balance(d.sum_insured_hit_eur) },
            { label: 'Checks flagged', value: `${d.frequency.n_more_often} of ${d.frequency.n_checks}`, accent: d.frequency.n_more_often ? 'var(--color-warn)' : undefined, sub: d.verdict_names.more_often },
          ]} />
          <Frequency d={d} onPolicy={setDrawerId} />
          <MostCrossed d={d} onPolicy={setDrawerId} />
        </>
      )}
      {drawerId && <AssetDrawer cfg={INSURER_CFG} id={drawerId} onClose={() => setDrawerId(null)} onChanged={() => q.refetch()} />}
    </div>
  )
}

// a stacked bar of how a set of checks reads
function Split({ parts }: { parts: { key: Verdict | 'none'; n: number; label: string }[] }) {
  const total = parts.reduce((a, p) => a + p.n, 0)
  if (!total) return null
  return (
    <div className="flex h-3 w-full rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img"
      aria-label={parts.filter(p => p.n).map(p => `${p.label}: ${p.n}`).join(', ')}>
      {parts.filter(p => p.n).map(p => <div key={p.key} title={`${p.label}: ${p.n}`} style={{ width: `${100 * p.n / total}%`, background: VERDICT_COLOR[p.key] }} />)}
    </div>
  )
}

const times = (r: number) => r >= 10 ? Math.round(r).toString() : r.toFixed(1)
const count = (n: number) => n < 0.1 ? n.toFixed(2) : n.toFixed(1)

function Frequency({ d, onPolicy }: { d: Review; onPolicy: (id: string) => void }) {
  const f = d.frequency, m = d.messages
  const [all, setAll] = useState(false)
  const flagged = all ? f.flagged : f.flagged.slice(0, 8)
  const names = d.verdict_names
  const split = (r: { n_more_often: number; n_in_line: number; n_less_often: number; n_no_verdict: number }) => ([
    { key: 'more_often' as const, n: r.n_more_often, label: names.more_often }, { key: 'in_line' as const, n: r.n_in_line, label: names.in_line },
    { key: 'less_often' as const, n: r.n_less_often, label: names.less_often }, { key: 'none' as const, n: r.n_no_verdict, label: names.none },
  ])
  const notChecked = [
    { n: f.n_uncatalogued, m: m.uncatalogued }, { n: f.n_no_return_period, m: m.no_return_period }, { n: f.n_unpriced, m: m.unpriced },
  ].filter(x => x.n > 0)
  return (
    <Card className="p-5 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SectionHead icon={ClipboardCheck}>Crossings beside the priced frequency</SectionHead>
          <MessageInfo m={m.check} sources={d.sources} />
        </div>
        {m.rule && <MessageLine m={m.rule} className="text-[12px] text-[var(--color-mute)]" />}
      </div>
      {d.definition.gap && <MethodGap gap={d.definition.gap} what="Frequency readings" />}

      {f.by_peril.length > 0 && (
        <div className="space-y-3">
          {f.by_peril.map(p => (
            <div key={p.peril} className="grid grid-cols-[8rem_1fr_auto] items-center gap-3 text-[12.5px]">
              <span className="text-[var(--color-ink)] truncate">{p.peril_name}</span>
              <Split parts={split(p)} />
              <span className="text-[var(--color-mute)] tabular-nums whitespace-nowrap">{p.n_checks} checks</span>
            </div>
          ))}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-[var(--color-mute)]">
            {split(f).filter(p => p.n).map(p => (
              <span key={p.key} className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: VERDICT_COLOR[p.key] }} />{p.label} · {p.n}</span>
            ))}
          </div>
        </div>
      )}

      {notChecked.length > 0 && (
        <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-[12.5px]">
          <span className="text-[var(--color-faint)]">Not checked</span>
          {notChecked.map(x => <span key={x.m.code} className="inline-flex items-center gap-1.5"><span className="tabular-nums font-medium text-[var(--color-ink)]">{x.n}</span><MessageLine m={x.m} className="text-[var(--color-mute)]" /></span>)}
        </div>
      )}

      {f.flagged.length > 0 && (
        <div>
          <div className="text-[12px] text-[var(--color-mute)] mb-1.5">Flagged checks, largest first</div>
          <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
            {flagged.map((c, i) => (
              <div key={`${c.policy_id}-${c.peril}-${i}`} {...pressable(() => onPolicy(c.policy_id))}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-[12.5px] cursor-pointer hover:bg-[var(--color-panel-2)] -mx-2 px-2 rounded">
                <span className="font-medium text-[var(--color-ink)] underline decoration-dotted decoration-[var(--color-line-2)] underline-offset-2">{c.policy_name}</span>
                <span className="text-[11.5px] text-[var(--color-faint)]">{c.region}</span>
                <Chip color="var(--color-slate)">{c.peril_name}</Chip>
                <span className="flex-1 min-w-0" />
                <span className="tabular-nums text-[var(--color-ink)]">{c.observed_events} crossed</span>
                <span className="tabular-nums text-[var(--color-faint)]">{count(c.expected_events)} expected</span>
                <Chip color={VERDICT_COLOR.more_often}>{times(c.ratio)}× the priced rate</Chip>
                <InfoButton compact details={{ title: `${c.policy_name} · ${c.peril_name}`, sections: [
                  { heading: HEADING.shows, body: `${c.observed_events} crossing${c.observed_events === 1 ? '' : 's'} in the ${c.window_years} years the catalogue covers. Priced at 1 in ${c.priced_return_period_years} years, the price expects ${count(c.expected_events)} in those years: crossings are ${times(c.ratio)} times that.` },
                  { heading: HEADING.read, body: m.check.detail?.next ?? '' },
                ].filter(s => s.body) }} />
              </div>
            ))}
          </div>
          {f.flagged.length > 8 && (
            <button type="button" onClick={() => setAll(!all)} className="mt-2 text-[12px] text-[var(--color-sky)] hover:underline">
              {all ? 'Show fewer' : `Show all ${f.flagged.length}`}
            </button>
          )}
        </div>
      )}
    </Card>
  )
}

function MostCrossed({ d, onPolicy }: { d: Review; onPolicy: (id: string) => void }) {
  const [open, setOpen] = useState<ObservedEvent | null>(null)
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <SectionHead icon={ShieldAlert}>Most crossed policies</SectionHead>
        <MessageInfo m={d.messages.crossed} sources={d.sources} />
      </div>
      {d.most_exposed.length === 0
        ? <div className="text-[12.5px] text-[var(--color-mute)]">No observed event has crossed a located policy.</div>
        : <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
            {d.most_exposed.map(p => (
              <div key={p.policy_id} className="py-2.5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
                  <span {...pressable(() => onPolicy(p.policy_id))}
                    className="font-medium text-[var(--color-ink)] cursor-pointer hover:text-[var(--color-sky)] underline decoration-dotted decoration-[var(--color-line-2)] underline-offset-2">{p.policy_name}</span>
                  <span className="text-[11.5px] text-[var(--color-faint)]">{p.region}</span>
                  <span className="flex-1 min-w-0" />
                  <span className="tabular-nums text-[var(--color-ink)]">{p.n_observed_events} crossed</span>
                  <span className="tabular-nums text-[var(--color-mute)]">{balance(p.sum_insured_eur)} insured</span>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {p.events.map((e, i) => (
                    <button key={e.id ?? i} type="button" onClick={() => setOpen(e)} title={`${eventTitle(e)} · ${e.year ?? ''}`}
                      className="inline-flex items-center gap-1 rounded-full border border-[var(--color-line)] px-2 py-0.5 text-[11.5px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
                      <KindIcon kind={e.kind} size={12} />{eventTitle(e)} <span className="tabular-nums text-[var(--color-faint)]">{e.year ?? ''}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>}
      {open && <EventDialog e={open} d={d.definition} onClose={() => setOpen(null)} />}
    </Card>
  )
}
