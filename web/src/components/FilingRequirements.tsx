import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ExternalLink, FileText, CalendarClock, Building2, CheckCircle2, Clock, Download, Upload } from 'lucide-react'
import { api, download } from '../lib/api'
import { Card } from './ui'

// What must this org report, to whom, how often, with links to the actual regulation + official form, the
// data it needs, when it was last filed, and access to every prior submission. The entry point to the
// reporting workflow — it sits above the filing calendar/register in the cockpit.

interface Filing { filing_id: string; period_label: string; status: string; submission_ref: string | null; snapshot_version: number | null; entity_name: string | null; filed_at: string | null }
interface Req {
  framework: string; label: string; official_name?: string; authority?: string; legal_basis?: string
  regulator: string; due_label: string; url?: string; summary?: string; official_form?: string; form_url?: string; inputs?: string
  entity_scoped: boolean; n_filings: number; last_filed: Filing | null; filings: Filing[]
}

const ST: Record<string, string> = { draft: '#94a3b8', in_review: '#e8b24c', returned: '#e8b24c', approved: '#5cc8ff', attested: '#a78bfa', submitted: '#2dd4bf', accepted: '#34d399', rejected: '#fb7185', superseded: '#64748b' }
const fmtDate = (s?: string | null) => s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

export default function FilingRequirements({ onOpen }: { onOpen: (id: string) => void }) {
  const q = useQuery({ queryKey: ['requirements'], queryFn: () => api.get<{ requirements: Req[] }>('/v1/filings/requirements') })
  const [open, setOpen] = useState<string | null>(null)
  const reqs = q.data?.requirements ?? []
  if (!q.isLoading && reqs.length === 0) return null

  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
        <FileText size={15} className="text-[var(--color-sky)]" />
        <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Reporting requirements · what you must file</span>
      </div>
      {q.isLoading ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">loading…</div>
        : <div className="divide-y divide-[var(--color-line)]">
            {reqs.map(r => {
              const isOpen = open === r.framework
              return (
                <div key={r.framework}>
                  <button onClick={() => setOpen(isOpen ? null : r.framework)} className="w-full text-left px-5 py-3.5 flex items-center gap-4 hover:bg-[var(--color-bg-2)] transition">
                    <ChevronRight size={15} className={`shrink-0 text-[var(--color-faint)] transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[14px] text-[var(--color-ink)] truncate">{r.official_name || r.label} <span className="mono text-[10px] text-[var(--color-bad)] uppercase tracking-wide ml-1">mandatory</span></div>
                      <div className="mono text-[11px] text-[var(--color-faint)] truncate flex items-center gap-1"><Building2 size={11} /> {r.regulator} · <CalendarClock size={11} /> {r.due_label}</div>
                    </div>
                    <div className="text-right shrink-0 w-40">
                      {r.last_filed
                        ? <div className="mono text-[11px]" style={{ color: ST[r.last_filed.status] ?? 'var(--color-mute)' }}><span className="inline-flex items-center gap-1"><CheckCircle2 size={11} /> last filed {r.last_filed.period_label}</span></div>
                        : <div className="mono text-[11px] text-[var(--color-warn)]">never filed</div>}
                      <div className="mono text-[9.5px] text-[var(--color-faint)]">{r.n_filings} prior report{r.n_filings === 1 ? '' : 's'}</div>
                    </div>
                  </button>
                  {isOpen && (
                    <div className="px-5 pb-5 pt-1 bg-[var(--color-bg-2)] space-y-4">
                      {r.summary && <p className="text-[12.5px] text-[var(--color-mute)] leading-relaxed max-w-3xl">{r.summary}</p>}
                      <div className="grid sm:grid-cols-2 gap-x-8 gap-y-2 text-[12px]">
                        <Kv k="Legal basis" v={r.legal_basis} />
                        <Kv k="Regulator" v={r.regulator} />
                        <Kv k="Frequency & deadline" v={r.due_label} />
                        <Kv k="Filing scope" v={r.entity_scoped ? 'Whole org · per entity · consolidated' : 'Whole organisation'} />
                      </div>
                      {r.inputs && (
                        <div className="rounded-lg border border-[var(--color-line)] px-3.5 py-2.5">
                          <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1 flex items-center gap-1.5"><Upload size={11} /> Data required</div>
                          <div className="text-[12px] text-[var(--color-mute)]">{r.inputs}</div>
                        </div>
                      )}
                      <div className="flex flex-wrap gap-2">
                        {r.url && <a href={r.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><ExternalLink size={12} /> Official regulation</a>}
                        {r.form_url && <a href={r.form_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition" title={r.official_form}><ExternalLink size={12} /> Official form / template</a>}
                      </div>

                      {/* prior submissions — access previously filed reports */}
                      <div>
                        <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Previously filed reports</div>
                        {r.filings.length === 0
                          ? <div className="text-[12px] text-[var(--color-faint)]">Nothing filed yet — prepare one from the calendar below.</div>
                          : <div className="rounded-lg border border-[var(--color-line)] divide-y divide-[var(--color-line)] overflow-hidden">
                              {r.filings.map(f => (
                                <div key={f.filing_id} className="flex items-center gap-3 px-3 py-2 text-[12px]">
                                  <Clock size={12} className="text-[var(--color-faint)] shrink-0" />
                                  <button onClick={() => onOpen(f.filing_id)} className="text-[var(--color-ink)] hover:text-[var(--color-sky)] hover:underline">{f.period_label}{f.entity_name ? ` · ${f.entity_name}` : ''}{f.snapshot_version ? ` · v${f.snapshot_version}` : ''}</button>
                                  <span className="mono text-[10px]" style={{ color: ST[f.status] ?? 'var(--color-faint)' }}>{f.status.replace(/_/g, ' ')}</span>
                                  <span className="mono text-[10px] text-[var(--color-faint)]">{fmtDate(f.filed_at)}{f.submission_ref ? ` · ${f.submission_ref}` : ''}</span>
                                  <button onClick={() => onOpen(f.filing_id)} title="Open filing" className="ml-auto text-[var(--color-faint)] hover:text-[var(--color-sky)]"><Download size={13} /></button>
                                </div>
                              ))}
                            </div>}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>}
    </Card>
  )
}

function Kv({ k, v }: { k: string; v?: string | null }) {
  if (!v) return null
  return <div className="flex flex-col"><span className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{k}</span><span className="text-[var(--color-mute)]">{v}</span></div>
}
