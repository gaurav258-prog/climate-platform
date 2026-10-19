import { useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { useAuth } from '../lib/auth'
import { PageHeader } from '../components/ui'
import { HEADING } from '../components/Details'
import { SharedOnward } from '../components/Remittance'
import { SupervisoryAccess } from './respondent/Supervisors'
import { SupervisorRequestsInbox } from './respondent/Requests'
import { TemplateSubmission } from './respondent/Submission'
import { WhatApplies } from './respondent/Mandates'
import { RegulatoryAttributes } from './respondent/Attributes'
import Approvals from './Approvals'
import Audit from './Audit'
import AdminEntities from '../components/AdminEntities'
import MethodParameters from '../components/MethodParameters'
import SectionTabs, { ADMIN_TABS } from '../components/SectionTabs'
import { resolveTab, visibleGroups } from './admin/tabs'
import Overview from './admin/Overview'
import { Roles, Users } from './admin/People'
import { DecisionPlaybook, Matrix, RiskAppetite } from './admin/Governance'
import Methodology from './admin/Methodology'
import Integrations from './admin/Integrations'
import { SupervisionAssignments, SupervisionProfile, SupervisionScope } from './admin/Supervision'

// The control center, to the UI standard (2026-10-16): one page per purpose behind tabs, each opening on what matters
// and keeping its explanations one click away. The server names every code it sends (services/governance/admin_view.py)
// and words every explanation as a catalogue message.

const ABOUT = [
  { heading: HEADING.shows, body: 'Your organisation’s set-up in one place: whether it is ready to file, its reporting identity and basis, its people and what they may do, the changes that need a second person, the risk appetite on each indicator, the choices the rules leave to you, and the connections to your own systems.' },
  { heading: HEADING.read, body: 'Each tab opens on its answer. An ⓘ next to a title explains it; a check that is not passing has a button to the page that fixes it.' },
]

export default function Admin() {
  const { profile } = useAuth()
  const groups = visibleGroups(profile?.permissions ?? [])
  const keys = groups.flat().map(t => t.key)
  const [params, setParams] = useSearchParams()
  const asked = resolveTab(params.get('tab'))
  const tab = asked && keys.includes(asked) ? asked : keys[0] ?? 'overview'
  const open = (key: string) => {
    const next = new URLSearchParams(params)
    next.set('tab', key); next.delete('setup')
    setParams(next, { replace: true })
  }

  return (
    <div className="fadeup space-y-6">
      <SectionTabs tabs={ADMIN_TABS} />
      <PageHeader eyebrow="Set up · control center" title="Control center" lead="Your set-up, people and controls." about={ABOUT} />
      <div className="flex gap-2 flex-wrap items-center" role="tablist" aria-label="Control center">
        {groups.map((g, gi) => (
          <div key={gi} className="flex gap-2 items-center">
            {gi > 0 && <span className="hidden sm:block w-px h-5 bg-[var(--color-line-2)] mx-1 shrink-0" aria-hidden />}
            {g.map(t => (
              <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => open(t.key)}
                className={clsx('px-3 py-1.5 rounded-lg text-[13px] border transition', tab === t.key
                  ? 'border-[var(--color-sky)] text-[var(--color-sky)]'
                  : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>{t.label}</button>
            ))}
          </div>
        ))}
      </div>
      {tab === 'overview' && <Overview onTab={open} />}
      {tab === 'team' && <Users />}
      {tab === 'roles' && <Roles />}
      {tab === 'matrix' && <div className="space-y-5"><Matrix /><DecisionPlaybook /></div>}
      {tab === 'approvals' && <Approvals embedded />}
      {tab === 'audit' && <Audit embedded />}
      {tab === 'entities' && (
        <div className="space-y-5">
          <AdminEntities /><SupervisoryAccess /><SharedOnward /><RegulatoryAttributes /><WhatApplies /><TemplateSubmission />
          <SupervisorRequestsInbox /><SupervisionProfile /><SupervisionScope /><SupervisionAssignments />
        </div>
      )}
      {tab === 'appetite' && <RiskAppetite />}
      {tab === 'methodology' && <div className="space-y-5"><MethodParameters /><Methodology /></div>}
      {tab === 'integrations' && <Integrations />}
    </div>
  )
}
