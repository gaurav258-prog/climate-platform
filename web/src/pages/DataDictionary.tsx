import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Database, CheckCircle2 } from 'lucide-react'
import { api } from '../lib/api'
import { Card, SectionHead, PageHeader, HeroBanner } from '../components/ui'
import { hazardLabel } from '../lib/hazards'

// The single golden model, browsable — each field, the source feed(s) it derives from, how current the
// golden source is, and which reports consume it. "Source once, reuse everywhere" made visible.

interface Feed { name: string; maturity: string | null; status: string | null }
interface Field { field: string; category: string; type: string; source_feeds: Feed[]; data_vintage: string | null; mapped: boolean; consumed_by: string[] }
interface Datapoint { label: string; source_category: string; lane: string; provider: string | null; note: string | null; coverage: string }
interface Fw { framework: string; label: string; datapoints: Datapoint[] }
interface Resp { fields: Field[]; summary: { hazard_fields: number; mapped_to_source: number; note: string }; frameworks?: Fw[] }

const feedDot = (m: string | null, s: string | null) => s === 'overdue' || s === 'failed' ? '#fb7185' : m === 'live' || s === 'fresh' ? '#34d399' : m === 'estimated' || m === 'proxy' ? '#f0a860' : '#94a3b8'
// how a reporting datapoint is sourced + how it enters Tellumen
const SRCC: Record<string, { l: string; c: string }> = {
  tellumen: { l: 'Tellumen', c: 'var(--color-good)' }, egov: { l: 'Free-gov', c: 'var(--color-sky)' },
  evendor: { l: 'Vendor', c: '#f0a860' }, customer: { l: 'You', c: '#a78bfa' }, none: { l: 'Gap', c: 'var(--color-faint)' },
}
const LANE: Record<string, string> = { compute: 'we compute', granular: 'you upload → we process', provided: 'you provide → we reconcile', report: 'final input on form', none: '—' }

export default function DataDictionary() {
  const q = useQuery({ queryKey: ['data-dictionary'], queryFn: () => api.get<Resp>('/v1/meta/data-dictionary') })
  const [open, setOpen] = useState<string | null>(null)
  const d = q.data

  return (
    <div className="fadeup space-y-5">
      <PageHeader eyebrow="Foundation · golden model" title="Data dictionary"
        lead="The single canonical model behind every report — each field, the authoritative source it comes from, how current it is, and which filings consume it. Sourced once on the H3 cell, reused everywhere." />

      {d && (
        <HeroBanner
          eyebrow="Foundation · golden model"
          title={d.summary.mapped_to_source >= d.summary.hazard_fields ? `All ${d.summary.hazard_fields} hazard fields trace to a source.` : `${d.summary.mapped_to_source} of ${d.summary.hazard_fields} fields mapped to a source.`}
          lead={d.summary.note}
          stat={[
            { label: 'Hazard fields', value: d.summary.hazard_fields, icon: Database, tone: 'var(--color-sky)' },
            { label: 'Mapped to a source', value: d.summary.mapped_to_source, icon: CheckCircle2, tone: '#4FA46E' },
          ]} />
      )}

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
        : !d ? <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the dictionary.</div>
        : (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]">
            <SectionHead icon={Database} hint="field · source feed · vintage · consumers">Golden model fields</SectionHead>
          </div>
          <div className="grid grid-cols-[1.4fr_0.9fr_1.8fr_0.9fr_1.1fr] gap-2 px-5 py-2.5 border-b border-[var(--color-line)] mono text-[11px] uppercase tracking-wide text-[var(--color-faint)]">
            <span>Field</span><span>Type</span><span>Source feed</span><span>Vintage</span><span>Consumed by</span>
          </div>
          <div className="divide-y divide-[var(--color-line)]">
            {d.fields.map(f => (
              <div key={f.field}>
              <div className="grid grid-cols-[1.4fr_0.9fr_1.8fr_0.9fr_1.1fr] gap-2 px-5 py-3 items-center text-[12px]">
                <button onClick={() => setOpen(open === f.field ? null : f.field)} className="text-left flex items-start gap-1.5 group">
                  {open === f.field ? <ChevronDown size={13} className="mt-0.5 text-[var(--color-faint)]" /> : <ChevronRight size={13} className="mt-0.5 text-[var(--color-faint)]" />}
                  <div>
                    <div className="text-[var(--color-ink)] group-hover:text-[var(--color-sky)] transition">{f.category === 'hazard' ? hazardLabel(f.field) : f.field.replace(/_/g, ' ')}</div>
                    <div className="mono text-[9.5px] text-[var(--color-faint)]">{f.category}</div>
                  </div>
                </button>
                <div className="mono text-[10.5px] text-[var(--color-mute)]">{f.type}</div>
                <div className="space-y-0.5">
                  {f.source_feeds.length === 0 ? <span className="text-[var(--color-faint)]">not mapped</span>
                    : f.source_feeds.map((s, i) => (
                      <div key={i} className="inline-flex items-center gap-1.5 mr-2">
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: feedDot(s.maturity, s.status) }} />
                        <span className="text-[11px] text-[var(--color-mute)]">{s.name}</span>
                      </div>
                    ))}
                </div>
                <div className="mono text-[10.5px] text-[var(--color-faint)]">{f.data_vintage ? f.data_vintage.slice(0, 10) : '—'}</div>
                <div className="flex flex-wrap gap-1">
                  {f.consumed_by.map(c => <span key={c} className="mono text-[9px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-sky)]">{c}</span>)}
                </div>
              </div>
              {open === f.field && (
                <div className="px-5 pb-4 pt-1 bg-[var(--color-panel)] text-[12px] space-y-2">
                  <div>
                    <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Source feeds</div>
                    {f.source_feeds.length === 0 ? <span className="text-[var(--color-faint)]">not mapped to a source</span>
                      : <div className="space-y-1">{f.source_feeds.map((s, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full" style={{ background: feedDot(s.maturity, s.status) }} />
                            <span className="text-[var(--color-ink)]">{s.name}</span>
                            <span className="mono text-[10px] text-[var(--color-faint)]">{[s.maturity, s.status].filter(Boolean).join(' · ')}</span>
                          </div>))}</div>}
                  </div>
                  <div className="flex gap-8">
                    <div><span className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">Golden-source vintage</span><div className="mono text-[11px] text-[var(--color-mute)]">{f.data_vintage ? f.data_vintage.slice(0, 10) : '—'}</div></div>
                    <div><span className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">Consumed by</span><div className="mono text-[11px] text-[var(--color-mute)]">{f.consumed_by.join(', ')}</div></div>
                  </div>
                </div>
              )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* reporting datapoints — where each comes from (source category) and how it enters Tellumen (lane) */}
      {d?.frameworks && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]">
            <SectionHead hint="where each comes from & how it enters Tellumen">Reporting datapoints</SectionHead>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
              {Object.entries(SRCC).map(([k, v]) => <span key={k} className="inline-flex items-center gap-1.5 mono text-[9.5px] text-[var(--color-faint)]"><span className="w-1.5 h-1.5 rounded-full" style={{ background: v.c }} />{v.l}</span>)}
            </div>
          </div>
          <div className="divide-y divide-[var(--color-line)]">
            {d.frameworks.map(fw => (
              <div key={fw.framework} className="px-5 py-3">
                <div className="text-[13px] text-[var(--color-ink)] mb-2">{fw.label}</div>
                <div className="space-y-1.5">
                  {fw.datapoints.map((dp, i) => (
                    <div key={i} className="flex items-start gap-3 text-[12px]">
                      <span className="mono text-[8.5px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 w-16 text-center" style={{ color: SRCC[dp.source_category]?.c, background: `color-mix(in oklab, ${SRCC[dp.source_category]?.c} 14%, transparent)` }}>{SRCC[dp.source_category]?.l}</span>
                      <div className="min-w-0 flex-1">
                        <div className="text-[var(--color-mute)]">{dp.label}</div>
                        <div className="mono text-[9.5px] text-[var(--color-faint)]">{LANE[dp.lane]}{dp.provider ? ` · ${dp.provider}` : ''}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
