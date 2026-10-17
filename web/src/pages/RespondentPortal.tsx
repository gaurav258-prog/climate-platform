import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { PageHeader, StatGrid } from '../components/ui'
import { HEADING } from '../components/Details'
import { SharedOnward } from '../components/Remittance'
import { SupervisoryAccess } from './respondent/Supervisors'
import { Deadlines } from './respondent/Deadlines'
import { SupervisorRequestsInbox } from './respondent/Requests'
import { TemplateSubmission } from './respondent/Submission'
import { WhatApplies } from './respondent/Mandates'
import { RegulatoryAttributes } from './respondent/Attributes'
import { day, daysBetween } from './respondent/common'
import { useCalendar, useMandates, useRequests } from './respondent/data'

// The supervisory portal, to the UI standard (2026-10-16): everything a supervised entity that does not use Tellumen as
// a workspace needs to answer its supervisor — and nothing else. Figures and a timeline first; every explanation one
// click away. The same panels a full tenant sees under Settings & team → Entities.
const ABOUT = [
  { heading: HEADING.shows, body: 'What your supervisor needs from you: acknowledge the supervision, state your regulatory attributes, submit the required template, and answer requests.' },
  { heading: HEADING.read, body: 'The figures at the top answer what is open and what is due next. The timeline places every report and request on its due date. Each panel below is one task.' },
  { heading: HEADING.limits, body: 'Every action here is recorded in your audit trail and in your supervisor’s.' },
]
const inDays = (n: number) => n === 0 ? 'today' : n === 1 ? 'tomorrow' : `in ${n} days`

export default function RespondentPortal() {
  const { profile } = useAuth()
  const [request, setRequest] = useState<string | null>(null)
  const reqs = useRequests()
  const cal = useCalendar()
  const mandates = useMandates()
  const today = cal.data?.today
  const reports = (cal.data?.events ?? []).filter(e => e.kind === 'obligation')
  const next = today ? reports.filter(e => e.date >= today && !e.overdue && !['submitted', 'accepted'].includes(e.status ?? '')).sort((a, b) => a.date.localeCompare(b.date))[0] : undefined
  const late = reports.filter(e => e.overdue).length
  const m = mandates.data?.summary
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Supervisory portal" title={profile?.org?.name ?? 'Your organisation'} lead="What your supervisor needs from you, in one place." about={ABOUT} />
      <StatGrid cols={4} items={[
        { label: 'Open requests', value: reqs.data ? reqs.data.summary.open : '—',
          sub: reqs.data ? (reqs.data.summary.overdue ? `${reqs.data.summary.overdue} overdue` : 'none overdue') : undefined,
          accent: reqs.data?.summary.overdue ? 'var(--color-bad)' : undefined },
        { label: 'Next report due', value: next ? day(next.date) : '—', sub: next && today ? inDays(daysBetween(today, next.date)) : 'nothing upcoming' },
        { label: 'Reports overdue', value: cal.data ? late : '—', accent: late ? 'var(--color-bad)' : undefined },
        { label: 'Requirements that apply', value: m ? m.applies : '—',
          sub: m ? (m.cannot_determine ? `${m.cannot_determine} cannot be determined` : `of ${m.applies + m.not_applicable}`) : undefined,
          accent: m?.cannot_determine ? 'var(--color-warn)' : undefined },
      ]} />
      <SupervisoryAccess />
      <Deadlines requests={reqs.data?.requests ?? []} onRequest={setRequest} />
      <SupervisorRequestsInbox open={request} onOpen={setRequest} />
      <TemplateSubmission />
      <div className="grid gap-6 lg:grid-cols-2 items-start">
        <WhatApplies />
        <RegulatoryAttributes />
      </div>
      <SharedOnward />
    </div>
  )
}
