import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CheckCircle2, Circle, ArrowRight, Rocket } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader } from '../components/ui'

interface Step { key: string; phase: string; title: string; done: boolean; optional: boolean; detail: string; route: string }
interface Status {
  available: boolean; org_name: string; org_type: string; steps: Step[]
  required_total: number; required_done: number; pct: number; live: boolean; next: Step | null
}
const PHASES = ['Provision', 'Load & configure', 'Govern & go live']

export default function Onboarding() {
  const q = useQuery({ queryKey: ['onboarding'], queryFn: () => api.get<Status>('/v1/admin/onboarding') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data?.available) return <Center>Onboarding status is available to your organization's admins.</Center>
  const d = q.data

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Set up · onboarding" title="Go-live checklist"
        lead={`Everything ${d.org_name} needs to be live and filing — tracked from the real state of your account, not a checklist someone ticks by hand.`} />

      {/* progress + live gate */}
      <Card className="p-5">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            {d.live
              ? <span className="inline-flex items-center gap-1.5 text-[var(--color-good)] text-[15px] font-medium"><Rocket size={18} /> Live</span>
              : <span className="text-[15px] font-medium text-[var(--color-ink)]">{d.required_done} of {d.required_total} required steps done</span>}
            <span className="mono text-[12px] text-[var(--color-faint)]">{d.pct}%</span>
          </div>
          {!d.live && d.next && (
            <Link to={d.next.route} className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-3.5 py-2 text-[13px] font-medium hover:bg-[var(--color-blue)] transition">
              Next: {d.next.title} <ArrowRight size={15} />
            </Link>
          )}
        </div>
        <div className="mt-3 h-2 rounded-full bg-[var(--color-panel-2)] overflow-hidden">
          <div className="h-full rounded-full transition-all" style={{ width: `${d.pct}%`, background: d.live ? 'var(--color-good)' : 'var(--color-sky)' }} />
        </div>
      </Card>

      {PHASES.map(phase => {
        const steps = d.steps.filter(s => s.phase === phase)
        if (!steps.length) return null
        return (
          <div key={phase}>
            <div className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)] mb-2 px-1">{phase}</div>
            <Card className="p-0">
              {steps.map((s, i) => (
                <div key={s.key} className={`flex items-center gap-3.5 px-4 py-3 ${i > 0 ? 'border-t border-[var(--color-line)]' : ''} ${d.next?.key === s.key ? 'bg-[color-mix(in_oklab,var(--color-sky)_7%,transparent)]' : ''}`}>
                  {s.done
                    ? <CheckCircle2 size={19} className="shrink-0 text-[var(--color-good)]" />
                    : <Circle size={19} className="shrink-0 text-[var(--color-faint)]" />}
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] text-[var(--color-ink)]">{s.title}
                      {s.optional && <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] ml-2 border border-[var(--color-line-2)] rounded px-1.5 py-0.5">optional</span>}
                    </div>
                    <div className="text-[12px] text-[var(--color-mute)]">{s.detail}</div>
                  </div>
                  {!s.done && (
                    <Link to={s.route} className="shrink-0 inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:text-[var(--color-blue)]">
                      {d.next?.key === s.key ? 'Start' : 'Go'} <ArrowRight size={13} />
                    </Link>
                  )}
                </div>
              ))}
            </Card>
          </div>
        )
      })}

      <p className="mono text-[10px] text-[var(--color-faint)] px-1">Each step's state is derived live from your account — identity stamped, users invited, book loaded &amp; scored, basis &amp; governance set, first filing created. It can't drift from reality.</p>
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[55vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
