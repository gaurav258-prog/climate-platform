import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, XCircle, CheckCircle2, ListPlus, ChevronRight } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, Lens, PageHeader, HeroStrip, HeroMetric } from '../components/ui'
import { frameworkLabel, prettify } from '../lib/hazards'
import { filingLink, taskLink } from '../lib/links'

// Control Tower — every open validation/reconciliation exception across all filings, in one prioritised
// worklist (the control surface a filing must clear before attest). Each row can be spun into a task with
// one click (de-duped), so the team acts instead of hunting. (Route/API keep the "exceptions" identifier.)

interface Exc {
  filing_id: string; filing_label: string; period: string; filing_status: string
  rule: string; category: string; severity: string; criticality: string; message: string
  source_ref: string; tracked: boolean; task_id: string | null
}
interface Resp {
  exceptions: Exc[]
  summary: { total: number; blocking: number; warnings: number; tracked: number; by_category: Record<string, number>; filings_scanned: number; filings_skipped: number }
}

const sevColor = (s: string) => s === 'blocking' ? '#fb7185' : '#f0a860'

export default function Exceptions() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const { profile } = useAuth()
  const q = useQuery({ queryKey: ['exceptions'], queryFn: () => api.get<Resp>('/v1/reg-tasks/exceptions') })
  const d = q.data

  const spin = async (e: Exc) => {
    try {
      await api.post('/v1/reg-tasks/exceptions/spin-task', {
        filing_id: e.filing_id, rule: e.rule, message: e.message, severity: e.severity,
      })
      qc.invalidateQueries({ queryKey: ['exceptions'] })
      qc.invalidateQueries({ queryKey: ['reg-tasks-board'] })
    } catch (err) { toast.error(err instanceof ApiError ? err.message : 'Could not create the task.') }
  }

  return (
    <div className="fadeup space-y-5">
      <PageHeader eyebrow="Workflow · control tower" title="Control Tower"
        lead="Every open validation & reconciliation exception across your live filings, worst first — the checks a filing must clear before it can be attested. Turn any of them into a task the team can pick up."
        actions={<Lens kind="control" />} />

      {d && d.summary.filings_skipped > 0 && (
        <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-bad)]">
          <AlertTriangle size={14} /> {d.summary.filings_skipped} filing{d.summary.filings_skipped === 1 ? '' : 's'} could not be validated and were skipped — the list below may be incomplete.
        </div>
      )}
      {d && (
        <HeroStrip>
          <HeroMetric value={d.summary.total} label="Open exceptions" sub={`${d.summary.filings_scanned} filings scanned`} />
          <HeroMetric value={d.summary.blocking} label="Blocking" tone={d.summary.blocking > 0 ? '#D23B3B' : undefined} />
          <HeroMetric value={d.summary.warnings} label="To review" tone={d.summary.warnings > 0 ? '#E8853C' : undefined} />
          <HeroMetric value={d.summary.tracked} label="Already tracked" tone={d.summary.tracked > 0 ? '#4FA46E' : undefined} />
        </HeroStrip>
      )}

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">scanning filings…</Card>
        : !d ? <div className="text-[12.5px] text-[var(--color-bad)]">Could not load exceptions.</div>
        : d.exceptions.length === 0
          ? <Card className="p-10 text-center"><CheckCircle2 size={22} className="mx-auto mb-2" style={{ color: '#34d399' }} /><div className="text-[13px] text-[var(--color-mute)]">No open exceptions — every live filing is clean.</div></Card>
          : (
          <Card className="p-0 overflow-hidden">
            <div className="divide-y divide-[var(--color-line)]">
              {d.exceptions.map((e, i) => {
                const Icon = e.severity === 'blocking' ? XCircle : AlertTriangle
                return (
                  <div key={i} className="px-5 py-3 flex items-center gap-3">
                    <Icon size={15} style={{ color: sevColor(e.severity) }} className="shrink-0" />
                    <button onClick={() => nav(filingLink(profile?.org?.type, e.filing_id))}
                      className="min-w-0 flex-1 text-left group" title="Open the filing behind this exception">
                      <div className="text-[13px] text-[var(--color-ink)] group-hover:text-[var(--color-sky)] transition inline-flex items-center gap-1">{e.message}<ChevronRight size={12} className="opacity-0 group-hover:opacity-100" /></div>
                      <div className="mono text-[10.5px] text-[var(--color-faint)] mt-0.5">
                        {frameworkLabel(e.filing_label)} · {e.period} · {prettify(e.category)}
                      </div>
                    </button>
                    {e.tracked
                      ? e.task_id
                        ? <button onClick={() => nav(taskLink(e.task_id!))} title="Open the task tracking this exception"
                            className="inline-flex items-center gap-1.5 mono text-[11px] shrink-0 hover:underline" style={{ color: '#34d399' }}>
                            <CheckCircle2 size={13} /> tracked <span className="text-[var(--color-sky)]">· open task →</span>
                          </button>
                        : <span className="inline-flex items-center gap-1 mono text-[11px]" style={{ color: '#34d399' }}><CheckCircle2 size={13} /> tracked</span>
                      : <button onClick={() => spin(e)} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition shrink-0">
                          <ListPlus size={13} /> Create task
                        </button>}
                  </div>
                )
              })}
            </div>
          </Card>
        )}
    </div>
  )
}
