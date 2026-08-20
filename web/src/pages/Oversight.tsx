import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, AlertTriangle, CheckCircle2, Clock, ChevronRight } from 'lucide-react'
import { api } from '../lib/api'
import { Card, SectionHead, PageHeader, HeroStrip, HeroMetric } from '../components/ui'

// Supervisory view — the whole institution the way a regulator or board reviews it: every mandatory filing
// with its status, coverage and KRI breaches, plus house-in-order readiness and open exceptions. Read-only,
// composed from the same services that drive the filing cockpit and KRI dashboard.

interface Filed { period_label: string; status: string }
interface Fw { framework: string; label: string; regulator: string; due_label: string; last_filed: Filed | null; n_filings: number; coverage_pct: number | null; breaches: number | null; breach_kris: string[] }
interface Check { key: string; label: string; ok: boolean; hint: string | null }
interface Exc { rule?: string; message?: string; framework?: string; severity?: string; filings_affected?: number }
interface Resp {
  frameworks: Fw[]
  readiness: { passed: number; total: number; checks: Check[] }
  exceptions: { open: number; top: Exc[] }
  summary: { n_frameworks: number; never_filed: number; total_breaches: number; open_exceptions: number; readiness_pct: number }
}

export default function Oversight() {
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['oversight'], queryFn: () => api.get<Resp>('/v1/reg-tasks/oversight') })
  const d = q.data
  const s = d?.summary

  const verdict = s && (
    `${s.n_frameworks} mandatory filing${s.n_frameworks === 1 ? '' : 's'}${s.never_filed > 0 ? `, ${s.never_filed} never filed` : ', all filed'}. `
    + `${s.total_breaches} KRI ${s.total_breaches === 1 ? 'breach' : 'breaches'} and ${s.open_exceptions} open exception${s.open_exceptions === 1 ? '' : 's'}`
    + `${(s.total_breaches + s.open_exceptions) > 0 ? ' need attention' : ' — nothing outstanding'}. Readiness ${s.readiness_pct}%.`
  )
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Governance · supervisory view" title="Supervisory overview"
        lead="The whole institution on one screen, the way a regulator or your board reviews it — every mandatory filing's status, how much of it you produce, its KRI breaches, plus readiness and open exceptions." />

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
        : !d ? <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the supervisory view.</div>
        : (
        <>
          {/* lead with the answer: one-line posture verdict + the headline numbers */}
          <HeroStrip>
            <HeroMetric value={s!.n_frameworks} label="Mandatory filings" />
            <HeroMetric value={s!.never_filed} label="Never filed" tone={s!.never_filed > 0 ? '#E8853C' : undefined} />
            <HeroMetric value={s!.total_breaches} label="KRI breaches" tone={s!.total_breaches > 0 ? '#D23B3B' : '#4FA46E'} />
            <HeroMetric value={s!.open_exceptions} label="Open exceptions" tone={s!.open_exceptions > 0 ? '#E8853C' : '#4FA46E'} />
            <HeroMetric value={`${s!.readiness_pct}%`} label="Readiness" tone={s!.readiness_pct >= 100 ? '#4FA46E' : '#E8853C'} />
          </HeroStrip>
          <p className="text-[13.5px] text-[var(--color-mute)] -mt-2">{verdict}</p>

          {/* per-filing rollup */}
          <Card className="p-0 overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
              <ShieldCheck size={15} className="text-[var(--color-sky)]" />
              <SectionHead hint="status · coverage · breaches">Mandatory filings</SectionHead>
            </div>
            <div className="hidden sm:grid grid-cols-[2fr_1fr_0.8fr_0.9fr_0.8fr] gap-3 px-5 py-2 border-b border-[var(--color-line)] mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">
              <span>Filing · regulator</span><span>Last filed</span><span>Produced</span><span>KRI breaches</span><span>Due</span>
            </div>
            <div className="divide-y divide-[var(--color-line)]">
              {d.frameworks.map(f => (
                <button key={f.framework} onClick={() => nav('/compliance')} className="w-full text-left grid grid-cols-2 sm:grid-cols-[2fr_1fr_0.8fr_0.9fr_0.8fr] gap-3 px-5 py-3 items-center hover:bg-[var(--color-bg-2)] transition text-[12.5px]">
                  <div className="min-w-0">
                    <div className="text-[var(--color-ink)] truncate">{f.label}</div>
                    <div className="mono text-[10px] text-[var(--color-faint)] truncate">{f.regulator}</div>
                  </div>
                  <div className="mono text-[11px]">
                    {f.last_filed
                      ? <span className="inline-flex items-center gap-1 text-[var(--color-good)]"><CheckCircle2 size={11} /> {f.last_filed.period_label}</span>
                      : <span className="inline-flex items-center gap-1 text-[var(--color-warn)]"><Clock size={11} /> never</span>}
                  </div>
                  <div className="mono text-[11.5px] tabular-nums" style={{ color: (f.coverage_pct ?? 0) >= 50 ? 'var(--color-good)' : 'var(--color-mute)' }}>{f.coverage_pct != null ? `${f.coverage_pct}%` : '—'}</div>
                  <div className="mono text-[11.5px] tabular-nums" title={f.breach_kris.join(' · ')} style={{ color: (f.breaches ?? 0) > 0 ? '#fb7185' : 'var(--color-faint)' }}>
                    {f.breaches == null ? '—' : f.breaches > 0 ? <span className="inline-flex items-center gap-1"><AlertTriangle size={11} /> {f.breaches}</span> : '0'}
                  </div>
                  <div className="mono text-[10px] text-[var(--color-faint)] flex items-center justify-between gap-1"><span className="truncate">{f.due_label}</span><ChevronRight size={13} className="text-[var(--color-faint)] shrink-0" /></div>
                </button>
              ))}
            </div>
          </Card>

          <div className="grid lg:grid-cols-2 gap-5">
            {/* readiness */}
            <div>
              <SectionHead icon={CheckCircle2} hint="is the house in order?" className="mb-2.5">Readiness controls</SectionHead>
              <Card className="p-0 overflow-hidden">
                <div className="divide-y divide-[var(--color-line)]">
                  {d.readiness.checks.map(c => (
                    <div key={c.key} className="flex items-start gap-2.5 px-5 py-2.5 text-[12.5px]">
                      {c.ok ? <CheckCircle2 size={14} className="text-[var(--color-good)] shrink-0 mt-0.5" /> : <AlertTriangle size={14} className="text-[var(--color-warn)] shrink-0 mt-0.5" />}
                      <div><div className="text-[var(--color-mute)]">{c.label}</div>{!c.ok && c.hint && <div className="mono text-[10px] text-[var(--color-faint)]">{c.hint}</div>}</div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
            {/* exceptions */}
            <div>
              <SectionHead icon={AlertTriangle} hint="from live filings" className="mb-2.5">Open exceptions</SectionHead>
              <Card className="p-0 overflow-hidden">
                {d.exceptions.open === 0
                  ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">No open exceptions.</div>
                  : <div className="divide-y divide-[var(--color-line)]">
                      {d.exceptions.top.map((e, i) => (
                        <button key={i} onClick={() => nav('/exceptions')} className="w-full text-left flex items-start gap-2.5 px-5 py-2.5 text-[12.5px] hover:bg-[var(--color-bg-2)] transition">
                          <AlertTriangle size={13} className="text-[var(--color-warn)] shrink-0 mt-0.5" />
                          <span className="text-[var(--color-mute)]">
                            {e.message || e.rule || 'exception'}
                            {(e.filings_affected ?? 1) > 1 && <span className="mono text-[10.5px] text-[var(--color-faint)] ml-1.5">· affects {e.filings_affected} filings</span>}
                          </span>
                        </button>
                      ))}
                      {d.exceptions.open > d.exceptions.top.length && <button onClick={() => nav('/exceptions')} className="w-full text-left px-5 py-2 mono text-[10.5px] text-[var(--color-sky)] hover:underline">View all {d.exceptions.open} in the Control Tower →</button>}
                    </div>}
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
