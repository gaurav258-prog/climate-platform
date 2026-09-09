import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, PageHeader } from '../components/ui'
import { RegulatoryAttributes, SupervisorRequestsInbox, SupervisoryAccess, TemplateSubmission } from './Admin'
import { SharedOnward } from '../components/Remittance'
import { WhatApplies } from '../components/GrcFollowups'

// The supervisory portal: everything a supervised entity that does not use Tellumen as a workspace needs to answer its
// supervisor — and nothing else. The same panels a full tenant sees under Settings → Entities.
interface Cal { events: { date: string; kind: string; title: string; sub: string; status: string | null; overdue: boolean }[] }
export default function RespondentPortal() {
  const { profile } = useAuth()
  const cal = useQuery({ queryKey: ['portal-calendar'], queryFn: () => api.get<Cal>('/v1/reg-tasks/calendar') })
  const obligations = (cal.data?.events ?? []).filter(e => e.kind === 'obligation')
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Supervisory portal" title={profile?.org?.name ?? 'Your organisation'}
        lead="What your supervisor needs from you: acknowledge the supervision, state your regulatory attributes, submit the required template, and answer requests. Every action is recorded on both sides." />
      <SupervisoryAccess />
      <SharedOnward />
      <WhatApplies />
      {obligations.length > 0 && (
        <Card className="p-5">
          <div className="text-[13px] font-medium text-[var(--color-ink)] mb-2">Deadlines</div>
          <div className="divide-y divide-[var(--color-line)]">{obligations.map((o, i) => (
            <div key={i} className="py-1.5 flex items-center justify-between gap-3 text-[12.5px]"><span className="text-[var(--color-ink)]">{o.title}<span className="mono text-[10.5px] text-[var(--color-faint)] ml-2">{o.sub}</span></span>
              <span className="mono text-[11px]" style={{ color: o.overdue ? 'var(--color-bad)' : 'var(--color-mute)' }}>{o.date}{o.overdue ? ' · overdue' : ''}</span></div>))}</div>
        </Card>)}
      <TemplateSubmission />
      <RegulatoryAttributes />
      <SupervisorRequestsInbox />
    </div>
  )
}
