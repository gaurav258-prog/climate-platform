import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Database, CheckCircle2, FileStack, Satellite, ListTree } from 'lucide-react'
import { api } from '../lib/api'
import { Card, SectionHead, PageHeader, HeroBanner } from '../components/ui'
import SectionTabs, { DATA_TABS } from '../components/SectionTabs'
import { HEADING, InfoButton, messageDetails, type Message } from '../components/Details'
import { Dialog } from '../components/Dialog'
import { StatusChip } from '../components/StatusChip'
import { Segments, TONE, plural, type Tone } from '../components/intake/parts'
import { pressable } from '../lib/pressable'

// The data dictionary: each hazard field behind every report — the feeds it is computed from and how current they are,
// how current the scores are, and which of your filings froze it — then each live report's datapoints by where the data
// comes from. Every word is the server's (services/governance/data_dictionary.py: names and catalogue messages).

interface Feed { name: string; maturity: string | null; status: string | null; state_label: string; maturity_label: string | null }
interface Field { field: string; label: string; category: string; source_feeds: Feed[]; data_vintage: string | null; mapped: boolean; consumed_by: { framework: string; label: string }[] }
interface Datapoint { label: string; source_category: string; lane: string; provider: string | null; note: string | null }
interface Fw { framework: string; label: string; datapoints: Datapoint[] }
interface Resp {
  fields: Field[]; summary: { hazard_fields: number; mapped_to_source: number; msg: Message }; frameworks: Fw[]
  legend: { source_category: Record<string, Message>; lane: Record<string, Message> }
}

const SOURCE_TONE: Record<string, Tone> = { tellumen: 'good', egov: 'neutral', evendor: 'warn', customer: 'info', none: 'bad' }
const chipTone = (k: string) => { const t = SOURCE_TONE[k] ?? 'neutral'; return t === 'faint' || t === 'info' ? 'neutral' : t }
const SOURCES = ['tellumen', 'egov', 'evendor', 'customer', 'none'] as const
const feedTone = (f: Feed) => f.status === 'overdue' || f.status === 'failed' ? 'var(--color-bad)' : f.status === 'due_soon' ? 'var(--color-warn)'
  : f.status === 'fresh' ? 'var(--color-good)' : 'var(--color-slate)'

export default function DataDictionary() {
  const q = useQuery({ queryKey: ['data-dictionary'], queryFn: () => api.get<Resp>('/v1/meta/data-dictionary') })
  const [field, setField] = useState<Field | null>(null)
  const [report, setReport] = useState<Fw | null>(null)
  const d = q.data
  const used = d ? d.fields.filter(f => f.consumed_by.length > 0).length : 0
  const late = d ? new Set(d.fields.flatMap(f => f.source_feeds).filter(f => f.status === 'overdue' || f.status === 'failed').map(f => f.name)).size : 0

  return (
    <div className="fadeup space-y-5">
      <SectionTabs tabs={DATA_TABS} />
      <PageHeader eyebrow="Your data" title="Data dictionary" lead="Each field behind your reports, its source and its users."
        about={[
          { heading: HEADING.read, body: 'Each hazard score is computed once for each place and reused by every report that needs it. A field lists the data feeds it is computed from, how current the scores are, and which of your filings froze it. Below, each report’s datapoints by where the data comes from.' },
          { heading: HEADING.sources, body: 'The feed registry and its update record; the hazard scores; your frozen filings; the datapoint catalogue of each report.' }]} />

      {d && (
        <HeroBanner eyebrow="Your data" title={d.summary.msg.label} lead={d.summary.msg.detail?.what}
          stat={[
            { label: 'Hazard fields', value: d.summary.hazard_fields, icon: Database, tone: 'var(--color-sky)' },
            { label: 'Traced to a source', value: d.summary.mapped_to_source, icon: CheckCircle2, tone: 'var(--color-good)' },
            { label: 'Used by your filings', value: used, icon: FileStack, tone: 'var(--color-blue)' },
            { label: 'Feeds overdue', value: late, icon: Satellite, tone: late ? 'var(--color-warn)' : 'var(--color-slate)' },
          ]} />)}

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Loading…</Card>
        : !d ? <div className="text-[12.5px] text-[var(--color-bad)]">The dictionary could not be loaded.</div>
        : (<>
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-1">
              <SectionHead icon={Database}>Hazard fields</SectionHead>
              <InfoButton compact details={{ title: 'Hazard fields', sections: [
                { heading: HEADING.shows, body: 'Each hazard score: the feeds it is computed from, with a dot for how current each is, the date of the latest scores, and the reports among your filings that froze it.' },
                { heading: HEADING.read, body: 'Green: up to date. Amber: an update is due. Red: an update is overdue or failed. Grey: a pinned release or no update on record. Select a field for its feeds.' }] }} />
            </div>
            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {d.fields.map(f => (
                <Card key={f.field} lift onClick={() => setField(f)} className="p-3.5 space-y-2 cursor-pointer">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-[var(--color-ink)] truncate">{f.label}</span>
                    <span className="ml-auto inline-flex gap-1">{f.source_feeds.map(s => <span key={s.name} title={`${s.name} · ${s.state_label}`} className="w-2 h-2 rounded-full" style={{ background: feedTone(s) }} />)}</span>
                  </div>
                  <div className="text-[11.5px] text-[var(--color-mute)]">{f.source_feeds.length ? plural(f.source_feeds.length, 'feed') : 'No feed named'} · scores as of {f.data_vintage ? f.data_vintage.slice(0, 10) : '—'}</div>
                  <div className="flex items-center gap-1">
                    {f.consumed_by.length ? <StatusChip tone="good" label={`Used by ${plural(f.consumed_by.length, 'report')}`} />
                      : <span className="text-[11.5px] text-[var(--color-faint)]">Not in your filings yet</span>}
                  </div>
                </Card>))}
            </div>
          </div>

          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-3 border-b border-[var(--color-line)] space-y-2">
              <div className="flex items-center gap-2">
                <SectionHead icon={ListTree}>Reporting datapoints</SectionHead>
                <InfoButton compact details={{ title: 'Reporting datapoints', sections: [
                  { heading: HEADING.shows, body: 'For each live report, its datapoints by where the data comes from. Select a report for each datapoint, how it enters the platform and who provides it.' },
                  ...SOURCES.map(k => ({ heading: d.legend.source_category[k].label, body: d.legend.source_category[k].detail?.what ?? '' }))] }} />
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {SOURCES.map(k => <span key={k} className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]">
                  <span className="w-2 h-2 rounded-full" style={{ background: TONE[SOURCE_TONE[k]] }} />{d.legend.source_category[k].label}</span>)}
              </div>
            </div>
            <div className="divide-y divide-[var(--color-line)]">
              {d.frameworks.map(fw => (
                <div key={fw.framework} {...pressable(() => setReport(fw), { row: true })} className="px-5 py-3 grid sm:grid-cols-[minmax(0,20rem)_1fr] gap-x-4 gap-y-1.5 items-center cursor-pointer hover:bg-[var(--color-bg-2)] transition">
                  <div className="text-[13px] text-[var(--color-ink)] truncate">{fw.label} <span className="text-[11.5px] text-[var(--color-faint)]">· {plural(fw.datapoints.length, 'datapoint')}</span></div>
                  <Segments legend={false} parts={SOURCES.map(k => ({ n: fw.datapoints.filter(x => x.source_category === k).length, tone: SOURCE_TONE[k], label: d.legend.source_category[k].label }))} />
                </div>))}
            </div>
          </Card>
        </>)}

      {field && (
        <Dialog title={field.label} onClose={() => setField(null)} className="sm:max-w-xl">
          <div className="space-y-3 text-[12.5px]">
            {field.source_feeds.length === 0 ? <div className="text-[var(--color-faint)]">No source feed is named for this field.</div>
              : field.source_feeds.map(s => (
                <div key={s.name} className="flex items-start gap-2">
                  <span className="mt-1.5 w-2 h-2 rounded-full shrink-0" style={{ background: feedTone(s) }} />
                  <div className="min-w-0">
                    <div className="text-[var(--color-ink)]">{s.name}</div>
                    <div className="text-[var(--color-mute)]">{[s.state_label, s.maturity_label].filter(Boolean).join(' · ')}</div>
                  </div>
                </div>))}
            <div className="text-[var(--color-mute)]">Scores as of {field.data_vintage ? field.data_vintage.slice(0, 10) : '—'}</div>
            {field.consumed_by.length > 0 && (
              <div className="space-y-1">
                <div className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)]">Your filings that froze it</div>
                <div className="flex flex-wrap gap-1.5">{field.consumed_by.map(c => <StatusChip key={c.framework} tone="neutral" label={c.label} />)}</div>
              </div>)}
          </div>
        </Dialog>)}
      {report && d && (
        <Dialog title={report.label} onClose={() => setReport(null)} className="sm:max-w-2xl">
          <div className="divide-y divide-[var(--color-line)] text-[12.5px] max-h-[65vh] overflow-y-auto">
            {report.datapoints.map((dp, i) => {
              const src = d.legend.source_category[dp.source_category], lane = d.legend.lane[dp.lane]
              return (
                <div key={i} className="py-2.5 space-y-1">
                  <div className="flex items-start gap-2">
                    <span className="flex-1 text-[var(--color-ink)]">{dp.label}</span>
                    {dp.note && <InfoButton compact details={{ title: dp.label, sections: [{ heading: HEADING.shows, body: dp.note }] }} />}
                  </div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {src && <StatusChip tone={chipTone(dp.source_category)} label={src.label} />}
                    {lane && <span className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)]">{lane.label}<InfoButton compact details={messageDetails(lane)} /></span>}
                    {dp.provider && <span className="text-[11.5px] text-[var(--color-faint)]">· {dp.provider}</span>}
                  </div>
                </div>)
            })}
          </div>
        </Dialog>)}
    </div>
  )
}
