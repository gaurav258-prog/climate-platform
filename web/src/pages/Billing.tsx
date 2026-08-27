import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, PageHeader } from '../components/ui'
import SectionTabs, { ADMIN_TABS } from '../components/SectionTabs'

interface Plan { key: string; seats: number; price_cents: number; label: string }
interface Invoice { number: string; amount_cents: number; currency: string; status: string; created_at: string }
interface Billing {
  subscription: { plan: string; seats: number; status: string; billing_mode: string; current_period_end: string | null } | null
  seats_used: number; plans: Plan[]; invoices: Invoice[]; billing_provider: string
}
function msg(e: unknown, f: string) { return e instanceof ApiError ? (e.body as { error?: { message?: string } })?.error?.message ?? f : f }
const eur = (c: number) => c === 0 ? '—' : `€${(c / 100).toLocaleString()}`

export default function Billing() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['billing'], queryFn: () => api.get<Billing>('/v1/billing') })
  const [busy, setBusy] = useState<string | null>(null)
  if (q.error) return <Center>Billing is available to your organization's admins.</Center>
  const d = q.data
  if (!d) return <Center>loading…</Center>
  const current = d.subscription?.plan

  async function change(plan: string) {
    setBusy(plan)
    try { await api.put('/v1/billing/plan', { plan }); qc.invalidateQueries({ queryKey: ['billing'] }); toast.success(`Switched to ${plan}.`) }
    catch (e) { toast.error(msg(e, 'Could not change plan.')) } finally { setBusy(null) }
  }

  return (
    <div className="fadeup space-y-6 max-w-[860px]">
      <SectionTabs tabs={ADMIN_TABS} />
      <PageHeader eyebrow="Set up · billing" title="Plan & billing"
        lead={`You're on the ${d.plans.find(p => p.key === d.subscription?.plan)?.label ?? d.subscription?.plan ?? 'trial'} plan${d.billing_provider === 'manual' ? ' · invoiced manually' : ' · billed via Stripe'}.`} />

      <Card className="p-5">
        <div className="flex items-center gap-6 flex-wrap">
          <Metric label="Plan" value={d.subscription?.plan ?? 'trial'} />
          <Metric label="Seats used" value={`${d.seats_used} / ${d.subscription?.seats ?? '—'}`} />
          <Metric label="Status" value={d.subscription?.status ?? '—'} />
        </div>
      </Card>

      <div>
        <div className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)] mb-2 px-1">Plans</div>
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))' }}>
          {d.plans.map(p => {
            const isCurrent = p.key === current
            return (
              <Card key={p.key} className={`p-4 ${isCurrent ? 'border-[var(--color-sky)]' : ''}`}>
                <div className="text-[14px] font-semibold text-[var(--color-ink)]">{p.label}</div>
                <div className="text-[22px] display font-semibold mt-1">{p.price_cents === 0 ? (p.key === 'enterprise' ? 'Custom' : 'Free') : eur(p.price_cents)}<span className="text-[11px] text-[var(--color-faint)] font-normal"> {p.price_cents ? '/mo' : ''}</span></div>
                <div className="text-[12px] text-[var(--color-mute)] mt-1">{p.seats} seats</div>
                {isCurrent
                  ? <div className="mt-3 inline-flex items-center gap-1 text-[12px] text-[var(--color-good)]"><Check size={13} /> Current plan</div>
                  : <Button variant="ghost" className="mt-3 w-full justify-center" onClick={() => change(p.key)} disabled={!!busy}>{busy === p.key ? '…' : p.key === 'enterprise' ? 'Contact sales' : 'Switch'}</Button>}
              </Card>
            )
          })}
        </div>
      </div>

      {d.invoices.length > 0 && (
        <div>
          <div className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)] mb-2 px-1">Invoices</div>
          <Card className="p-0">
            {d.invoices.map((i, n) => (
              <div key={i.number} className={`flex items-center gap-4 px-4 py-3 text-[13px] ${n > 0 ? 'border-t border-[var(--color-line)]' : ''}`}>
                <span className="mono text-[var(--color-mute)]">{i.number}</span>
                <span className="flex-1 text-[var(--color-faint)]">{new Date(i.created_at).toLocaleDateString()}</span>
                <span className="text-[var(--color-ink)]">{eur(i.amount_cents)}</span>
                <span className={`mono text-[10px] uppercase px-1.5 py-0.5 rounded border ${i.status === 'paid' ? 'text-[var(--color-good)] border-[var(--color-good)]' : 'text-[var(--color-warn)] border-[var(--color-warn)]'}`}>{i.status}</span>
              </div>
            ))}
          </Card>
        </div>
      )}
      {d.billing_provider === 'manual' && <p className="mono text-[10px] text-[var(--color-faint)] px-1">Card payment activates once Stripe is connected; today invoices are issued for manual settlement.</p>}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">{label}</div><div className="text-[18px] font-semibold text-[var(--color-ink)] mt-0.5 capitalize">{value}</div></div>
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[55vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
