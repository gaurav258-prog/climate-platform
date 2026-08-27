import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, ExternalLink, CalendarClock, Database, Plug, CheckCircle2, ArrowRight } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, HeroBanner } from '../components/ui'

// Regulatory outlook — the CUSTOMER's view of the regulation: what applies to you today, what's changing and
// when, and whether YOU will need to provide new data or an integration. Nothing about Tellumen's own build
// process (that internal pipeline lives on the platform-operator page).

interface InForce { framework: string; name: string; authority: string; frequency: string; requires: string; citation: string; url: string | null }
interface Coming { framework: string | null; title: string; when: string; whats_changing: string; prepare: string | null; citation: string; url: string | null }
interface Outlook { in_force: InForce[]; coming: Coming[]; summary: { n_in_force: number; n_coming: number; n_prepare: number } }

const needsIntegration = (p: string) => /integration|credential|traces|api|connect/i.test(p)

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
                  {d.coming.map((c, i) => (
                    <Card key={i} className="p-0 overflow-hidden">
                      <div className="px-4 py-3.5 flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="text-[14px] font-medium text-[var(--color-ink)] leading-snug">{c.title}</div>
                          <p className="text-[12.5px] text-[var(--color-mute)] mt-1.5 leading-snug">{c.whats_changing}</p>
                          <a href={c.url ?? undefined} target="_blank" rel="noopener noreferrer" className="mono text-[10px] text-[var(--color-sky)] mt-2 inline-flex items-center gap-1 hover:underline"><ExternalLink size={10} /> {c.citation}</a>
                        </div>
                        <div className="shrink-0 text-right">
                          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Takes effect</div>
                          <div className="mono text-[11.5px] text-[var(--color-ink)] mt-0.5 max-w-[180px]">{c.when}</div>
                        </div>
                      </div>
                      {/* what YOU need to prepare — the only "action" this page ever asks of a customer */}
                      <div className="px-4 py-2.5 border-t border-[var(--color-line)] flex items-start gap-2.5"
                        style={{ background: c.prepare ? 'color-mix(in oklab, var(--color-warn) 7%, transparent)' : 'var(--color-bg-2)' }}>
                        {c.prepare
                          ? (needsIntegration(c.prepare)
                              ? <Plug size={13} className="text-[var(--color-warn)] shrink-0 mt-0.5" />
                              : <Database size={13} className="text-[var(--color-warn)] shrink-0 mt-0.5" />)
                          : <CheckCircle2 size={13} className="text-[var(--color-good)] shrink-0 mt-0.5" />}
                        <div>
                          <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">{c.prepare ? 'To prepare' : 'Your side'}</div>
                          <div className="text-[12px] text-[var(--color-mute)] leading-snug">{c.prepare ?? 'No new data or integration needed — computed from the book you already provide.'}</div>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>}
            <div className="mono text-[10px] text-[var(--color-faint)] mt-3 flex items-center gap-1.5">
              <ArrowRight size={11} /> Dates are the regulator's timeline; where a change is proposed but not final, it says so.
            </div>
          </div>
        </>)}
    </div>
  )
}
