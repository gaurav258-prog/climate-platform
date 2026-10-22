import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, Coins, ShieldAlert } from 'lucide-react'
import { api } from '../lib/api'
import { Button, Card, HeroBanner, SectionHead } from './ui'
import { HBar } from './Charts'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import MethodGap from './MethodGap'
import { placeLine } from '../lib/codeWords'
import { flow } from '../lib/money'
import { DecideForm, DecisionChip, type Decision, type Meta, type Policy } from './DecideForm'

// The tested-loss signal of the decision spine (losses into decisions, 2026-10-22): the assets whose tested yearly loss
// reaches the share of their value the institution states. Only figures from curves that passed their test come here;
// a decision goes through the same verb-pack, 4-eyes rule and playbook as a forward crossing.

type Basis = 'defended' | 'undefended' | 'protection_unknown' | null
interface Figure { peril: string; peril_name: string; basis: Basis; loss_eur: number; loss_low_eur: number | null; loss_high_eur: number | null; share: number; exposed_value_eur: number }
interface Signal { entity_id: string; entity_name: string | null; country: string | null; region: string | null; value_eur: number | null; loss_eur: number; share: number; figures: Figure[]; decision: Decision | null }
interface Resp { level: number | null; gap: string | null; as_of: string | null; carried: number; withheld: Record<string, number>; notice: Message | null; policy: Policy; n: number; signals: Signal[] }

const BASIS: Record<string, string> = { defended: 'with defences', undefended: 'without defences', protection_unknown: 'protection unknown' }
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
export const sharePct = (x: number | null | undefined) => x == null ? '—' : `${Number((100 * x).toPrecision(2))}%`
const perilLine = (f: Figure) => cap(f.peril_name) + (f.basis ? ` (${BASIS[f.basis]})` : '')

export default function LossSignals({ canAct, actions, noun, nounP }: { canAct: boolean; actions: (Meta & { key: string })[]; noun: string; nounP: string }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['decision-loss-signals'], queryFn: () => api.get<Resp>('/v1/decisions/loss-signals') })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['decision-loss-signals'] }); qc.invalidateQueries({ queryKey: ['decision-log'] }) }
  const d = q.data
  const sigs = d?.signals ?? []
  const approved = sigs.filter(s => s.decision?.status === 'approved').length
  const pending = sigs.filter(s => s.decision?.status === 'proposed').length
  const total = sigs.reduce((t, s) => t + s.loss_eur, 0)
  const notCarried = (d?.withheld.held ?? 0) + (d?.withheld.untested ?? 0)
  const title = q.isLoading ? 'Reading tested losses…'
    : d?.gap ? 'Your loss signal level is not stated.'
    : d?.notice && d.carried === 0 ? `${d.notice.label}.`
    : sigs.length === 0 ? `No ${noun} reaches your loss signal level.`
    : `${sigs.length} ${sigs.length === 1 ? `${noun} reaches` : `${nounP} reach`} your loss signal level.`
  return (
    <>
      {d?.gap && <MethodGap gap={d.gap} what="Loss signals" />}
      {d?.notice && (
        <div className="rounded-xl border border-[var(--color-warn)]/40 bg-[var(--color-panel)] px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
          <MessageLine m={d.notice} className="flex-1 min-w-0 text-[var(--color-ink)]" />
          <Link to={d.notice.code === 'loss.signal.flood_lead_not_stated' ? '/admin?tab=Methodology' : '/loss'} className="text-[var(--color-sky)] hover:underline whitespace-nowrap">
            {d.notice.code === 'loss.signal.flood_lead_not_stated' ? 'State it →' : 'Open Loss →'}</Link>
        </div>
      )}

      <HeroBanner eyebrow="Tested-loss decisions" title={title}
        lead={d?.level != null ? `Tested yearly loss at or above ${sharePct(d.level)} of the value, today's climate.` : 'Tested yearly loss as a share of the value, today’s climate.'}
        stat={[
          { label: `${cap(nounP)} signalled`, value: q.isLoading ? '—' : sigs.length, icon: ShieldAlert, tone: 'var(--color-sky)' },
          { label: 'Tested loss per year', value: q.isLoading ? '—' : flow(total), icon: Coins, tone: '#D23B3B', pulse: !q.isLoading && total > 0 },
          { label: 'Decided', value: q.isLoading ? '—' : `${approved} / ${sigs.length}`, icon: Check, tone: approved === sigs.length && sigs.length > 0 ? '#4FA46E' : pending > 0 ? '#E8853C' : undefined },
        ]} />

      {sigs.length > 1 && (
        <Card className="p-5">
          <div className="text-[13px] font-medium text-[var(--color-ink)] mb-3">Tested loss per year</div>
          <HBar data={sigs.slice(0, 8).map(s => ({ label: s.entity_name ?? '—', value: s.loss_eur, sub: sharePct(s.share), color: '#D23B3B' }))} format={(n) => flow(n)} height={16} />
        </Card>
      )}

      <Card className="p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
          <Coins size={15} className="text-[var(--color-bad)]" />
          <SectionHead hint={`share of value lost per year · tested loss per year${d?.level != null ? ` · your level ${sharePct(d.level)}` : ''}`}>{cap(nounP)} at your loss signal level</SectionHead>
        </div>
        {q.isLoading ? <div className="px-5 py-8 text-[13px] text-[var(--color-faint)]">reading tested losses…</div>
          : sigs.length === 0 ? <div className="px-5 py-8 text-[13px] text-[var(--color-faint)]">{d?.gap ? 'Not computed — state your loss signal level first.' : 'Nothing to act on.'}</div>
          : <div className="divide-y divide-[var(--color-line)]">
              {sigs.map(s => <SignalRow key={s.entity_id} s={s} policy={d?.policy} canAct={canAct} actions={actions} onDone={refresh} />)}
            </div>}
      </Card>

      {d && d.as_of && (
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--color-faint)]">
          <span>{d.carried} tested figures read · {notCarried} not carried</span>
          <InfoButton compact details={{ title: 'Which loss figures come here', sections: [
            { heading: HEADING.shows, body: `The losses worked out on ${d.as_of} for today's climate. Only figures from damage curves that passed their test against observed losses are carried; figures from held or untested curves stay on the Loss page.` },
          ] }} />
        </div>
      )}
    </>
  )
}

function SignalRow({ s, policy, canAct, actions, onDone }: { s: Signal; policy?: Policy; canAct: boolean; actions: (Meta & { key: string })[]; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const details = {
    title: s.entity_name ?? 'Asset',
    sections: s.figures.map(f => ({
      heading: perilLine(f),
      body: `${flow(f.loss_eur)} a year${f.loss_low_eur != null && f.loss_high_eur != null ? ` (range ${flow(f.loss_low_eur)} – ${flow(f.loss_high_eur)})` : ''} — ${sharePct(f.share)} of the ${flow(f.exposed_value_eur)} its curve applies to.`,
    })),
  }
  return (
    <div className="px-5 py-3">
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] text-[var(--color-ink)] truncate">{s.entity_name ?? '—'}</div>
          <div className="text-[11px] text-[var(--color-faint)] truncate">{placeLine(s.region, s.country)} · {s.figures.map(perilLine).join(' · ')}</div>
        </div>
        <div className="hidden sm:block mono text-[11.5px] text-[var(--color-bad)] font-medium w-16 text-right shrink-0">{sharePct(s.share)}</div>
        <div className="mono text-[12.5px] tabular-nums text-[var(--color-ink)] w-24 text-right shrink-0 inline-flex items-center justify-end gap-1">{flow(s.loss_eur)}<InfoButton compact details={details} /></div>
        <div className="w-32 flex justify-end shrink-0">
          {s.decision ? <DecisionChip decision={s.decision} canAct={canAct} onClick={() => setOpen(o => !o)} />
            : canAct ? <Button variant="ghost" onClick={() => setOpen(o => !o)}>Decide</Button>
            : <span className="mono text-[10px] text-[var(--color-faint)]">awaiting a decision</span>}
        </div>
      </div>
      {s.decision && (
        <div className="mt-1.5 flex items-center gap-3 mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">
          <span>next</span>
          <Link to="/tasks" className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">Board task <ArrowRight size={11} /></Link>
        </div>
      )}
      {open && canAct && <DecideForm body={{ entity_id: s.entity_id, entity_name: s.entity_name, signal: 'loss' }} decision={s.decision} policy={policy}
        value={s.value_eur} actions={actions} onDone={() => { setOpen(false); onDone() }} onCancel={() => setOpen(false)} />}
    </div>
  )
}
