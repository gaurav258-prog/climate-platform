import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CheckCircle2, Circle, ArrowRight, Rocket } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader } from '../components/ui'
import { HEADING, InfoButton, messageDetails, type Message } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import SectionTabs, { ADMIN_TABS } from '../components/SectionTabs'

// The go-live checklist: how far the organisation is from being live and filing — a progress ring and the steps by
// phase, each step's state in a short line from the server (platform.golive.* messages) with what it means one click
// away. Nothing here is ticked by hand: every step is read from the live state of the workspace.

interface Step { key: string; phase: string; title: string; about: Message; done: boolean; optional: boolean; message: Message; route: string }
interface Status {
  available: boolean; message?: Message; org_name: string; phases: { key: string; label: string }[]; steps: Step[]
  required_total: number; required_done: number; pct: number; live: boolean; next: Step | null
}

const ABOUT = [
  { heading: HEADING.shows, body: 'Everything your organisation needs to be live and filing, read from the live state of your workspace.' },
  { heading: HEADING.read, body: 'A step is done when your workspace shows it: the reporting identity set, people active, the book loaded and scored, the basis and approval rules set, a first filing created. Optional steps do not hold back going live. Each open step links to the page where it is done.' },
]

const stepDetails = (s: Step) => ({
  title: s.title,
  sections: [{ heading: HEADING.shows, body: s.about.detail?.what ?? '' }, ...messageDetails(s.message).sections],
})

export default function Onboarding() {
  const q = useQuery({ queryKey: ['onboarding'], queryFn: () => api.get<Status>('/v1/admin/onboarding') })
  if (q.isLoading) return <Center>Loading…</Center>
  if (q.error || !q.data?.available) return <Center>{q.data?.message?.label ?? 'The checklist is open to your organisation’s administrators.'}</Center>
  const d = q.data
  const tone = d.live ? 'var(--color-good)' : 'var(--color-sky)'

  return (
    <div className="fadeup space-y-6">
      <SectionTabs tabs={ADMIN_TABS} />
      <PageHeader eyebrow="Set up" title={d.live ? 'Go-live checklist' : 'Get started'}
        lead={d.live ? 'Every required step is done.' : 'Work down the steps; each opens where it is done.'} about={ABOUT} />

      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-6">
          <Ring pct={d.pct} tone={tone} />
          <div className="min-w-0 flex-1 space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              {d.live
                ? <span className="inline-flex items-center gap-1.5 text-[var(--color-good)] text-[15px] font-medium"><Rocket size={18} /> Live</span>
                : <span className="text-[15px] font-medium text-[var(--color-ink)] tabular-nums">{d.required_done} of {d.required_total} required steps done</span>}
              {!d.live && d.next && (
                <Link to={d.next.route} className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-3.5 py-2 text-[13px] font-medium hover:bg-[var(--color-blue)] transition">
                  Next: {d.next.title} <ArrowRight size={15} />
                </Link>
              )}
            </div>
            <Stepper phases={d.phases} steps={d.steps} next={d.next?.key} />
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        {d.phases.map(p => {
          const steps = d.steps.filter(s => s.phase === p.key)
          if (!steps.length) return null
          return (
            <Card key={p.key} className="p-0">
              <div className="flex items-center justify-between px-4 pt-3.5 pb-2">
                <span className="text-[13px] font-semibold text-[var(--color-ink)]">{p.label}</span>
                <span className="text-[12px] text-[var(--color-faint)] tabular-nums">{steps.filter(s => s.done).length} of {steps.length}</span>
              </div>
              {steps.map(s => (
                <div key={s.key} className={`flex items-start gap-3 px-4 py-3 border-t border-[var(--color-line)] ${d.next?.key === s.key ? 'bg-[color-mix(in_oklab,var(--color-sky)_7%,transparent)]' : ''}`}>
                  {s.done
                    ? <CheckCircle2 size={18} className="shrink-0 mt-0.5 text-[var(--color-good)]" />
                    : <Circle size={18} className="shrink-0 mt-0.5 text-[var(--color-faint)]" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13.5px] text-[var(--color-ink)]">
                      {s.title}
                      {s.optional && <StatusChip label="Optional" tone="neutral" />}
                      <InfoButton compact details={stepDetails(s)} />
                    </div>
                    <div className="text-[12.5px] text-[var(--color-mute)] mt-0.5">{s.message.label}</div>
                  </div>
                  {!s.done && (
                    <Link to={s.route} className="shrink-0 inline-flex items-center gap-1 text-[12.5px] text-[var(--color-sky)] hover:text-[var(--color-blue)]">
                      {d.next?.key === s.key ? 'Start' : 'Go'} <ArrowRight size={13} />
                    </Link>
                  )}
                </div>
              ))}
            </Card>
          )
        })}
      </div>
    </div>
  )
}

// Required steps done, as a ring.
function Ring({ pct, tone }: { pct: number; tone: string }) {
  return (
    <div className="relative h-24 w-24 shrink-0" role="img" aria-label={`${pct} per cent of required steps done`}>
      <svg viewBox="0 0 36 36" className="h-24 w-24 -rotate-90">
        <circle cx="18" cy="18" r="15.5" fill="none" stroke="var(--color-line-2)" strokeWidth="3" />
        <circle cx="18" cy="18" r="15.5" fill="none" stroke={tone} strokeWidth="3" strokeLinecap="round" strokeDasharray={`${(pct / 100) * 97.4} 97.4`} />
      </svg>
      <div className="absolute inset-0 grid place-items-center display text-[20px] font-semibold tabular-nums" style={{ color: tone }}>{pct}%</div>
    </div>
  )
}

// Every step in order, one segment each, grouped by phase: green when done, outlined when optional, ringed when next.
function Stepper({ phases, steps, next }: { phases: Status['phases']; steps: Step[]; next?: string }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-2" aria-hidden>
      {phases.map(p => (
        <div key={p.key} className="min-w-[140px] flex-1">
          <div className="flex gap-1">
            {steps.filter(s => s.phase === p.key).map(s => (
              <span key={s.key} title={s.title}
                className="h-2 flex-1 rounded-full"
                style={{
                  background: s.done ? 'var(--color-good)' : s.optional ? 'transparent' : 'var(--color-line-2)',
                  border: s.optional && !s.done ? '1px dashed var(--color-line-2)' : undefined,
                  boxShadow: s.key === next ? '0 0 0 2px var(--color-sky)' : undefined,
                }} />
            ))}
          </div>
          <div className="text-[11.5px] text-[var(--color-faint)] mt-1.5">{p.label}</div>
        </div>
      ))}
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[55vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
