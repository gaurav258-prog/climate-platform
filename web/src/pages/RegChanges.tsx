import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, ExternalLink, CalendarClock, Database, Plug, CheckCircle2, ArrowRight, Radar, ChevronDown, ChevronRight, ListChecks, Clock } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, HeroBanner } from '../components/ui'

// Regulatory outlook — the CUSTOMER's view of the regulation: what applies to you today, what's changing and
// when, and whether YOU will need to provide new data or an integration. Nothing about Tellumen's own build
// process (that internal pipeline lives on the platform-operator page).

interface InForce { framework: string; name: string; authority: string; frequency: string; requires: string; citation: string; url: string | null }
interface DataField { field: string; note: string; status?: string; detail?: string | null }
interface DataSummary { have: number; partial: number; needed: number; total: number }
interface Coming { framework: string | null; title: string; date: string | null; date_fixed: boolean; when: string; whats_changing: string; prepare: string | null; citation: string; url: string | null; source: string; status?: string; verified_date?: string; verified_at?: string; date_moved?: boolean; detected_at?: string; data_fields?: DataField[]; data_tbc?: string | null; data_summary?: DataSummary }
interface Outlook { in_force: InForce[]; coming: Coming[]; checked_at: string | null; summary: { n_in_force: number; n_coming: number; n_prepare: number; n_dated: number; n_detected: number; n_verified: number } }

const needsIntegration = (p: string) => /integration|credential|traces|api|connect/i.test(p)

function ComingCard({ c }: { c: Coming }) {
  const [showData, setShowData] = useState(false)
  const fields = c.data_fields ?? []
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-4 py-3.5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {c.source === 'detected' && <span className="mono text-[8.5px] uppercase tracking-wide px-1.5 py-0.5 rounded inline-flex items-center gap-1" style={{ color: '#a78bfa', background: 'color-mix(in oklab, #a78bfa 16%, transparent)' }}><Radar size={9} /> newly detected · pending review</span>}
            <div className="text-[14px] font-medium text-[var(--color-ink)] leading-snug">{c.title}</div>
          </div>
          <p className="text-[12.5px] text-[var(--color-mute)] mt-1.5 leading-snug">{c.whats_changing}</p>
          <a href={c.url ?? undefined} target="_blank" rel="noopener noreferrer" className="mono text-[10px] text-[var(--color-sky)] mt-2 inline-flex items-center gap-1 hover:underline"><ExternalLink size={10} /> {c.citation}</a>
        </div>
        <div className="shrink-0 text-right">
          <div className="mono text-[9px] uppercase tracking-wide inline-flex items-center gap-1 justify-end" style={{ color: c.date_fixed ? 'var(--color-good)' : 'var(--color-faint)' }}>
            {c.date_fixed ? <><CheckCircle2 size={10} /> Confirmed date</> : 'Not yet fixed'}
          </div>
          <div className="mono text-[11.5px] text-[var(--color-ink)] mt-0.5 max-w-[190px]" style={c.date_fixed ? { fontWeight: 600 } : undefined}>{c.when}</div>
          {c.verified_date && <div className="mono text-[9px] text-[var(--color-good)] mt-1 inline-flex items-center gap-1 justify-end"><CheckCircle2 size={9} /> verified vs EUR-Lex{c.verified_at ? ` · ${c.verified_at}` : ''}</div>}
          {c.date_moved && <div className="mono text-[9px] text-[var(--color-warn)] mt-0.5">↑ updated from an earlier date</div>}
        </div>
      </div>

      {/* what YOU need to prepare — the only "action" this page ever asks of a customer */}
      <div className="px-4 py-2.5 border-t border-[var(--color-line)] flex items-start gap-2.5"
        style={{ background: (c.prepare || c.data_tbc) ? 'color-mix(in oklab, var(--color-warn) 7%, transparent)' : 'var(--color-bg-2)' }}>
        {c.prepare
          ? (needsIntegration(c.prepare)
              ? <Plug size={13} className="text-[var(--color-warn)] shrink-0 mt-0.5" />
              : <Database size={13} className="text-[var(--color-warn)] shrink-0 mt-0.5" />)
          : c.data_tbc ? <Clock size={13} className="text-[var(--color-warn)] shrink-0 mt-0.5" />
          : <CheckCircle2 size={13} className="text-[var(--color-good)] shrink-0 mt-0.5" />}
        <div className="min-w-0 flex-1">
          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">{c.prepare ? 'To prepare' : c.data_tbc ? 'Data — to be confirmed' : 'Your side'}</div>
          <div className="text-[12px] text-[var(--color-mute)] leading-snug">{c.prepare ?? c.data_tbc ?? 'No new data or integration needed — computed from the book you already provide.'}</div>
          {/* the exact fields the client should stand up in their systems — with what we already hold */}
          {fields.length > 0 && (
            <>
              <button onClick={() => setShowData(v => !v)} className="mt-2 inline-flex items-center gap-1.5 mono text-[10px] text-[var(--color-sky)] hover:underline">
                {showData ? <ChevronDown size={12} /> : <ChevronRight size={12} />}<ListChecks size={12} /> Data to provide · {fields.length} field{fields.length === 1 ? '' : 's'}
                {c.data_summary && <span className="text-[var(--color-faint)]">· you already hold {c.data_summary.have}/{c.data_summary.total}</span>}
              </button>
              {showData && (
                <ul className="mt-2 flex flex-col gap-1.5">
                  {fields.map((f, i) => {
                    const st = f.status
                    const tone = st === 'have' ? 'var(--color-good)' : st === 'partial' ? 'var(--color-warn)' : 'var(--color-faint)'
                    const Icon = st === 'have' ? CheckCircle2 : st === 'partial' ? Clock : Database
                    return (
                      <li key={i} className="flex items-start gap-2 text-[12px]">
                        <Icon size={12} className="mt-0.5 shrink-0" style={{ color: tone }} />
                        <span className="min-w-0">
                          <span className="text-[var(--color-ink)]">{f.field}</span>
                          {f.note && <span className="mono text-[10px] text-[var(--color-faint)]"> — {f.note}</span>}
                          {st && <span className="mono text-[9px] uppercase tracking-wide ml-1.5 px-1.5 py-0.5 rounded" style={{ color: tone, background: `color-mix(in oklab, ${tone} 14%, transparent)` }}>{st === 'have' ? 'you hold this' : st === 'partial' ? `partial ${f.detail ?? ''}` : 'you’ll provide'}</span>}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
    </Card>
  )
}

export default function RegChanges() {
  const q = useQuery({ queryKey: ['reg-outlook'], queryFn: () => api.get<Outlook>('/v1/reg-changes/outlook') })
  const d = q.data

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Regulatory maintenance" title="Regulatory outlook"
        lead="What applies to you today, what's changing and when — and any new data you'll need to provide. We track the regulation so nothing catches your filing off guard." />

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
        : !d ? <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the regulatory outlook.</div>
        : (<>
          <HeroBanner eyebrow="Regulatory outlook"
            title={`${d.summary.n_in_force} in force today · ${d.summary.n_coming} change${d.summary.n_coming === 1 ? '' : 's'} on the horizon`}
            lead={d.summary.n_prepare > 0
              ? `${d.summary.n_prepare} upcoming change${d.summary.n_prepare === 1 ? '' : 's'} will ask you for new data or an integration — flagged below so you can prepare.`
              : 'Nothing upcoming needs new data from you — the changes are computed from the book you already provide.'}
            stat={[
              { label: 'In force today', value: d.summary.n_in_force, icon: ShieldCheck, tone: '#4FA46E' },
              { label: 'Changes on the horizon', value: d.summary.n_coming, icon: CalendarClock, tone: 'var(--color-sky)' },
              { label: 'Need data from you', value: d.summary.n_prepare, icon: Database, tone: d.summary.n_prepare > 0 ? '#E8B24C' : '#4FA46E' },
            ]} />

          {/* IN FORCE TODAY */}
          <div>
            <div className="flex items-center gap-2 mb-2.5">
              <CheckCircle2 size={15} className="text-[var(--color-good)]" />
              <span className="text-[13px] font-semibold text-[var(--color-good)]">In force today</span>
              <span className="mono text-[10px] text-[var(--color-faint)]">· what you report now</span>
            </div>
            <div className="grid md:grid-cols-2 gap-3">
              {d.in_force.map(f => (
                <Card key={f.framework} className="p-4">
                  <div className="text-[14px] font-medium text-[var(--color-ink)] leading-snug">{f.name}</div>
                  <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1">{f.authority} · {f.frequency}</div>
                  <p className="text-[12.5px] text-[var(--color-mute)] mt-2 leading-snug">{f.requires}</p>
                  <a href={f.url ?? undefined} target="_blank" rel="noopener noreferrer" className="mono text-[10px] text-[var(--color-sky)] mt-2.5 inline-flex items-center gap-1 hover:underline"><ExternalLink size={10} /> {f.citation}</a>
                </Card>
              ))}
            </div>
          </div>

          {/* COMING CHANGES */}
          <div>
            <div className="flex items-center gap-2 mb-2.5 mt-1">
              <CalendarClock size={15} className="text-[var(--color-sky)]" />
              <span className="text-[13px] font-semibold text-[var(--color-sky)]">Coming changes</span>
              <span className="mono text-[10px] text-[var(--color-faint)]">· what's changing, when, and what you'll need</span>
            </div>
            {d.coming.length === 0
              ? <Card className="p-6 text-[13px] text-[var(--color-mute)]">No changes on the horizon for your sector right now.</Card>
              : <div className="space-y-3">
                  {d.coming.map((c, i) => <ComingCard key={i} c={c} />)}
                </div>}
            <div className="mono text-[10px] text-[var(--color-faint)] mt-3 space-y-1">
              <div className="flex items-start gap-1.5"><ArrowRight size={11} className="mt-0.5 shrink-0" /> A <b className="text-[var(--color-good)]">confirmed date</b> is fixed in the cited regulation; <b>not yet fixed</b> means the regulator hasn't set one — we don't guess.</div>
              {d.checked_at && <div className="flex items-start gap-1.5"><Radar size={11} className="mt-0.5 shrink-0 text-[var(--color-good)]" /> Dates are checked live against the official EU register (EUR-Lex / Cellar) — last checked <b className="text-[var(--color-mute)]">{d.checked_at}</b>. A <span style={{ color: '#a78bfa' }}>newly-detected</span> change is a machine-spotted move awaiting our confirmation.</div>}
            </div>
          </div>
        </>)}
    </div>
  )
}
