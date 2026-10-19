import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BellRing, ChevronRight, GitBranch, Rss, Telescope } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { Card, PageHeader } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, messageDetails } from '../components/Details'
import { ChangeImpact } from '../components/GrcFollowups'
import { OutlookTab } from './regChanges/Outlook'
import { VersionsTab } from './regChanges/Versions'
import { SignalsTab } from './regChanges/Signals'
import { plural, type Outlook, type RegAlert, type Signals, type Versions } from './regChanges/shared'

// Regulatory outlook, to the UI standard (2026-10-16) — the customer's view of the regulation: what applies to you
// today, what is changing and when, and the data you will need. The main screen is figures, a time line and one line
// per change; every explanation is a catalogue message one click away, and a change opens in a side drawer.

const ABOUT = [
  { heading: HEADING.shows, body: 'The regulations you report under, every change coming to them with its date, and the data each change asks of you — with how much of it your records already hold.' },
  { heading: HEADING.read, body: <ul className="list-disc pl-5 space-y-1">
    <li><b>Outlook</b> — what is in force for you and the changes ahead, on a time line.</li>
    <li><b>Versions</b> — each regulation’s legal versions: the act in force and the acts that amend or replace it.</li>
    <li><b>Early signals</b> — news from regulators and the press before the official register records a change.</li>
  </ul> },
  { heading: HEADING.sources, body: 'The official EU register (EUR-Lex), regulators’ own news feeds, our regulatory team’s register of announced changes, and your own records.' },
  { heading: HEADING.limits, body: 'We track the regulation so nothing catches your filing off guard; a change reaches your filings only once it takes effect. We never estimate a date the regulator has not set.' },
]

type Tab = 'outlook' | 'versions' | 'signals'
const TABS: [Tab, string, typeof Telescope][] = [['outlook', 'Outlook', Telescope], ['versions', 'Versions', GitBranch], ['signals', 'Early signals', Rss]]

export default function RegChanges() {
  const [tab, setTab] = useState<Tab>('outlook')
  const aq = useQuery({ queryKey: ['reg-alerts'], queryFn: () => api.get<{ alerts: RegAlert[] }>('/v1/reg-changes/alerts') })
  const q = useQuery({ queryKey: ['reg-outlook'], queryFn: () => api.get<Outlook>('/v1/reg-changes/outlook') })
  const vq = useQuery({ queryKey: ['reg-versions'], enabled: tab === 'versions', queryFn: () => api.get<Versions>('/v1/reg-changes/versions') })
  const sq = useQuery({ queryKey: ['reg-signals'], enabled: tab === 'signals', queryFn: () => api.get<Signals>('/v1/reg-changes/signals') })
  const shown = tab === 'outlook' ? q : tab === 'versions' ? vq : sq
  const alerts = aq.data?.alerts ?? []

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Regulatory maintenance" title="Regulatory outlook" lead="What applies to you, what is changing, and when." about={ABOUT} />

      {alerts.length > 0 && <Alerts alerts={alerts} />}

      <div className="flex gap-1 p-1 rounded-xl border border-[var(--color-line)] bg-[var(--color-bg-2)] w-fit max-w-full overflow-x-auto" role="tablist">
        {TABS.map(([k, l, Icon]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-[12.5px] whitespace-nowrap transition ${tab === k ? 'bg-[var(--color-panel)] text-[var(--color-ink)] shadow-[0_0_0_1px_var(--color-line)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            <Icon size={14} /> {l}
          </button>
        ))}
      </div>

      {shown.isLoading ? <Card className="p-10 text-center text-[13px] text-[var(--color-faint)]">Loading…</Card>
        : !shown.data ? <Card className="p-8 text-[13px] text-[var(--color-bad)]">{apiMessage(shown.error, 'Could not load this view.')}</Card>
        : tab === 'outlook' ? <><OutlookTab d={q.data!} /><ChangeImpact /></>
        : tab === 'versions' ? <VersionsTab d={vq.data!} />
        : <SignalsTab d={sq.data!} />}
    </div>
  )
}

// Alerts raised for you: a change spotted in the register, or a date coming within the alert window. Each one's
// explanation is a catalogue message; its task, when one was raised, is on the Tasks board.
function Alerts({ alerts }: { alerts: RegAlert[] }) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <BellRing size={16} className="text-[var(--color-warn)]" />
        <span className="text-[13.5px] font-medium text-[var(--color-ink)]">{plural(alerts.length, 'alert')} raised for you</span>
        <Link to="/tasks" className="ml-auto text-[12px] text-[var(--color-sky)] hover:underline inline-flex items-center gap-0.5">Tasks <ChevronRight size={13} /></Link>
      </div>
      <div className="divide-y divide-[var(--color-line)]">
        {alerts.slice(0, 5).map(a => (
          <div key={a.alert_key} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="inline-flex items-center gap-1">
              <StatusChip label={a.kind === 'deadline' && a.days != null && a.days >= 0 ? plural(a.days, 'day') : a.message.label}
                tone={a.kind === 'detected' ? 'warn' : a.days != null && a.days < 0 ? 'good' : a.days != null && a.days <= 90 ? 'bad' : 'warn'} />
              <InfoButton compact details={messageDetails(a.message)} />
            </span>
            <span className="text-[13px] text-[var(--color-ink)] min-w-0 flex-1">{a.name}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}
