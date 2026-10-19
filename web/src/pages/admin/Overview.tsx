import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertCircle, Check, CheckSquare, ScrollText, Users as UsersIcon, ArrowRight } from 'lucide-react'
import { api } from '../../lib/api'
import { balance } from '../../lib/money'
import { Card, SectionHead, StatGrid } from '../../components/ui'
import { HEADING, InfoButton, MessageLine, type Message } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import ClientRates from '../../components/ClientRates'
import { Identity } from './Identity'
import { Basis } from './Basis'
import { Feeds } from './Feeds'
import { Share } from './parts'

// Overview: is the organisation ready to file, and where does it stand — readiness first, then its book (agriculture),
// its identity and basis, its own exchange rates, its data sources, and its approvals, audit and people.

interface Check { key: string; label: string; ok: boolean; message: Message; fix_href: string | null; fix_label: string | null }
export interface Org { name: string | null; legal_name: string | null; type: string | null; type_label: string | null; country: string | null
  lei: string | null; eori: string | null; filing_contact_email: string | null; operator_address: string | null }
interface CC {
  organization: Org
  readiness: { passed: number; total: number; checks: Check[] }
  data: { sites: { total: number; scored: number; elevated: number; value_eur: number }; plots: { total: number; eudr_covered: number; eudr_read: number; needs_polygon: number } }
  governance: { pending_approvals: number; audit_events_30d: number; audit_window_days: number; second_approver: boolean }
  access: { users: number; active: number; ever_logged_in: number }
  offerings: { key: string; label: string }[]
}

const READINESS = {
  title: 'Reporting readiness', sections: [
    { heading: HEADING.shows, body: 'The checks your organisation must pass before its figures can be filed with confidence: who files, a second person to approve, current data and, for agriculture, a complete book of sites and plots.' },
    { heading: HEADING.read, body: 'Each check reads the live state of your workspace; nothing is estimated. A check that is not passing has a button to the page that fixes it, and its ⓘ says what is missing.' },
  ],
}
const BOOK = {
  title: 'Your book', sections: [
    { heading: HEADING.shows, body: 'How much of your book of operating sites and sourcing plots is scored, what it is worth, and how many plots are read for deforestation or still need a boundary.' },
    { heading: HEADING.read, body: 'A plot larger than four hectares needs its boundary, not only a point, for a deforestation reading.' },
  ],
}

export default function Overview({ onTab }: { onTab: (key: string) => void }) {
  const q = useQuery({ queryKey: ['control-center'], queryFn: () => api.get<CC>('/v1/admin/control-center') })
  if (q.isLoading) return <div className="py-16 text-center text-[var(--color-faint)] text-sm">Loading…</div>
  if (q.error || !q.data) return <div className="py-16 text-center text-[var(--color-faint)] text-sm">The overview could not be loaded. Try again shortly.</div>
  const d = q.data
  const r = d.readiness
  const pct = r.total ? Math.round((r.passed / r.total) * 100) : 0
  const tone = pct === 100 ? 'var(--color-good)' : pct >= 60 ? 'var(--color-warn)' : 'var(--color-bad)'
  const hasBook = d.organization.type === 'manufacturer' || d.data.sites.total > 0 || d.data.plots.total > 0

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="grid gap-6 md:grid-cols-[180px_1fr] items-start">
          <div className="flex md:flex-col items-center gap-4 md:gap-2 md:text-center">
            <Ring pct={pct} tone={tone} />
            <div>
              <div className="text-[15px] font-semibold text-[var(--color-ink)] inline-flex items-center gap-1.5">Reporting readiness <InfoButton compact details={READINESS} /></div>
              <div className="text-[12.5px] text-[var(--color-mute)] tabular-nums">{r.passed} of {r.total} checks passing</div>
            </div>
          </div>
          <ul className="divide-y divide-[var(--color-line)] m-0 p-0 list-none">
            {r.checks.map(c => (
              <li key={c.key} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2.5">
                {c.ok ? <Check size={16} className="text-[var(--color-good)] shrink-0" /> : <AlertCircle size={16} className="text-[var(--color-warn)] shrink-0" />}
                {c.ok ? <span className="text-[13px] text-[var(--color-mute)]">{c.label}</span>
                  : <MessageLine m={c.message} className="text-[13px] text-[var(--color-ink)]" />}
                {!c.ok && c.fix_href && c.fix_label && (
                  <Link to={c.fix_href} className="ml-auto inline-flex items-center gap-1 text-[12.5px] text-[var(--color-sky)] hover:underline">{c.fix_label} <ArrowRight size={13} /></Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <Tile icon={CheckSquare} title="Approvals" onClick={() => onTab('approvals')}>
          <div className="display text-[26px] leading-none tabular-nums" style={{ color: d.governance.pending_approvals ? 'var(--color-warn)' : 'var(--color-ink)' }}>{d.governance.pending_approvals}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-[var(--color-mute)]">
            waiting <StatusChip tone={d.governance.second_approver ? 'good' : 'warn'} label={d.governance.second_approver ? 'Second approver in place' : 'No second approver'} />
          </div>
        </Tile>
        <Tile icon={ScrollText} title="Audit trail" onClick={() => onTab('audit')}>
          <div className="display text-[26px] leading-none tabular-nums">{d.governance.audit_events_30d}</div>
          <div className="mt-2 text-[12px] text-[var(--color-mute)]">changes recorded in the last {d.governance.audit_window_days} days</div>
        </Tile>
        <Tile icon={UsersIcon} title="People" onClick={() => onTab('team')}>
          <Share n={d.access.active} of={d.access.users} label="Active" tone="var(--color-good)" />
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {d.offerings.map(o => <span key={o.key} className="text-[11.5px] px-2 py-0.5 rounded-full bg-[var(--color-panel-2)] text-[var(--color-mute)]">{o.label}</span>)}
          </div>
        </Tile>
      </div>

      {hasBook && (
        <div className="space-y-3">
          <SectionHead className="gap-1.5">Your book <InfoButton compact details={BOOK} /></SectionHead>
          <StatGrid cols={4} items={[
            { label: 'Sites scored', value: `${d.data.sites.scored} of ${d.data.sites.total}`, accent: d.data.sites.scored === d.data.sites.total ? 'var(--color-good)' : 'var(--color-warn)' },
            { label: 'Value of the book', value: balance(d.data.sites.value_eur) },
            { label: 'Plots read for deforestation', value: `${d.data.plots.eudr_read} of ${d.data.plots.eudr_covered}`, accent: d.data.plots.eudr_read === d.data.plots.eudr_covered ? 'var(--color-good)' : 'var(--color-warn)' },
            { label: 'Plots needing a boundary', value: d.data.plots.needs_polygon, accent: d.data.plots.needs_polygon ? 'var(--color-warn)' : 'var(--color-good)' },
          ]} />
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <Identity org={d.organization} onSaved={() => q.refetch()} />
        <Basis />
      </div>
      <ClientRates />
      <Feeds />
    </div>
  )
}

function Ring({ pct, tone }: { pct: number; tone: string }) {
  return (
    <div className="relative h-24 w-24 shrink-0" role="img" aria-label={`${pct} per cent of checks passing`}>
      <svg viewBox="0 0 36 36" className="h-24 w-24 -rotate-90">
        <circle cx="18" cy="18" r="15.5" fill="none" stroke="var(--color-line-2)" strokeWidth="3" />
        <circle cx="18" cy="18" r="15.5" fill="none" stroke={tone} strokeWidth="3" strokeLinecap="round" strokeDasharray={`${(pct / 100) * 97.4} 97.4`} />
      </svg>
      <div className="absolute inset-0 grid place-items-center display text-[20px] font-semibold tabular-nums" style={{ color: tone }}>{pct}%</div>
    </div>
  )
}

function Tile({ icon: Icon, title, onClick, children }: { icon: React.ComponentType<{ size?: number; className?: string }>; title: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <Card lift onClick={onClick} className="p-4 cursor-pointer hover:border-[var(--color-sky)] transition">
      <div className="flex items-center gap-2 mb-3"><Icon size={15} className="text-[var(--color-sky)]" /><span className="text-[13px] font-semibold text-[var(--color-ink)]">{title}</span>
        <ArrowRight size={13} className="ml-auto text-[var(--color-faint)]" /></div>
      {children}
    </Card>
  )
}
