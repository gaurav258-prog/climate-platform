import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CreditCard } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { minorAmount } from '../lib/money'
import { Button, Card, PageHeader, SectionHead } from '../components/ui'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import SectionTabs, { ADMIN_TABS } from '../components/SectionTabs'
import { Share, refused } from './admin/parts'

// Plan and billing, to the UI standard (2026-10-16): the plan, its seats, the plans to move to and the invoices. The
// server names the plan and statuses and words how invoices are settled (services/governance/billing.py); a plan
// change it refuses is a catalogue error.

interface Plan { key: string; seats: number; price_cents: number; label: string; self_serve: boolean }
interface Invoice { number: string; amount_cents: number; currency: string; status: string; status_label: string; created_at: string }
interface Billing {
  subscription: { plan: string; plan_label: string | null; seats: number; status: string; status_label: string | null } | null
  seats_used: number; plans: Plan[]; price_currency: string; invoices: Invoice[]; billing_note: Message; plan_note: Message | null
}
const ABOUT = [
  { heading: HEADING.shows, body: 'Your plan, how many of its seats are taken, the plans you can move to and your invoices.' },
  { heading: HEADING.read, body: 'A seat is a person who can sign in. A plan agreed with our team is arranged through Support.' },
]

export default function Billing() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['billing'], queryFn: () => api.get<Billing>('/v1/billing') })
  const [busy, setBusy] = useState<string | null>(null)
  const nav = useNavigate()
  if (q.error) return <Center>Plan and billing are for your organisation’s administrators.</Center>
  const d = q.data
  if (!d) return <Center>Loading…</Center>
  const sub = d.subscription
  const change = async (p: Plan) => {
    setBusy(p.key)
    try { await api.put('/v1/billing/plan', { plan: p.key }); qc.invalidateQueries({ queryKey: ['billing'] }); toast.success(`You are now on the ${p.label} plan.`) }
    catch (e) { refused(e, 'The plan could not be changed.') } finally { setBusy(null) }
  }

  return (
    <div className="fadeup space-y-6 max-w-[900px]">
      <SectionTabs tabs={ADMIN_TABS} />
      <PageHeader eyebrow="Set up · billing" title="Plan and billing" lead="Your plan, seats and invoices." about={ABOUT} />
      <Card className="p-5">
        <div className="grid gap-5 sm:grid-cols-[1fr_1.2fr] items-center">
          <div>
            <SectionHead icon={CreditCard} className="gap-1.5">{sub?.plan_label ?? d.plan_note?.label}
              {!sub && d.plan_note && <InfoButton compact details={messageDetails(d.plan_note)} />}</SectionHead>
            {sub?.status_label && <div className="mt-2"><StatusChip value={sub.status} tone={sub.status === 'active' ? 'good' : 'neutral'} label={sub.status_label} /></div>}
            <div className="mt-2"><MessageLine m={d.billing_note} className="text-[12.5px] text-[var(--color-mute)]" /></div>
          </div>
          {sub ? <Share n={d.seats_used} of={sub.seats} label="Seats taken" tone={d.seats_used >= sub.seats ? 'var(--color-warn)' : 'var(--color-good)'} />
            : <div className="text-[13px] text-[var(--color-mute)] tabular-nums">{d.seats_used} people can sign in</div>}
        </div>
      </Card>

      <section>
        <SectionHead className="mb-2">Plans</SectionHead>
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))' }}>
          {d.plans.map(p => {
            const current = p.key === sub?.plan
            const fits = d.seats_used <= p.seats
            return (
              <Card key={p.key} className={clsx('p-4', current && 'border-[var(--color-sky)]')}>
                <div className="text-[14px] font-semibold text-[var(--color-ink)]">{p.label}</div>
                <div className="text-[22px] display font-semibold mt-1 tabular-nums">{p.price_cents ? minorAmount(p.price_cents, d.price_currency) : p.self_serve ? 'Free' : 'Agreed with us'}
                  {p.price_cents > 0 && <span className="text-[11.5px] text-[var(--color-faint)] font-normal"> a month</span>}</div>
                <div className="text-[12.5px] text-[var(--color-mute)] mt-1 tabular-nums">{p.seats} seats</div>
                {current ? <div className="mt-3 inline-flex items-center gap-1 text-[12.5px] text-[var(--color-good)]"><Check size={13} /> Your plan</div>
                  : p.self_serve ? <Button variant="ghost" className="mt-3 w-full justify-center" onClick={() => change(p)} disabled={!!busy || !fits}>{busy === p.key ? 'Switching…' : fits ? 'Switch' : 'Too few seats'}</Button>
                  : <Button variant="ghost" className="mt-3 w-full justify-center" onClick={() => nav(`/support?subject=${encodeURIComponent(`${p.label} plan enquiry`)}`)}>Contact us</Button>}
              </Card>
            )
          })}
        </div>
      </section>

      {d.invoices.length > 0 && (
        <section>
          <SectionHead className="mb-2">Invoices</SectionHead>
          <Card className="p-0 overflow-x-auto">
            <table className="data-table w-full text-[13px]">
              <thead><tr><th>Invoice</th><th>Date</th><th className="text-right">Amount</th><th>Status</th></tr></thead>
              <tbody>{d.invoices.map(i => (
                <tr key={i.number}>
                  <td className="tabular-nums text-[var(--color-mute)]">{i.number}</td>
                  <td className="text-[var(--color-faint)]">{new Date(i.created_at).toLocaleDateString('en-GB')}</td>
                  <td className="text-right tabular-nums text-[var(--color-ink)]">{minorAmount(i.amount_cents, i.currency)}</td>
                  <td><StatusChip value={i.status} tone={i.status === 'paid' ? 'good' : 'warn'} label={i.status_label} /></td>
                </tr>
              ))}</tbody>
            </table>
          </Card>
        </section>
      )}
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[55vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
