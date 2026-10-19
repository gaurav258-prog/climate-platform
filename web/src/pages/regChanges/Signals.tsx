import { ExternalLink, Rss } from 'lucide-react'
import { Card, SectionHead, StatGrid } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton, messageDetails } from '../../components/Details'
import { day, type Signals } from './shared'

// The Early signals tab: news from regulators' own feeds and the press about the regulations you report under, before
// the official register records a change. Each is unconfirmed until the register records it; its summary is one click
// away.

export function SignalsTab({ d }: { d: Signals }) {
  const confirmed = d.signals.filter(s => s.status === 'register_confirmed').length
  return (
    <div className="space-y-5">
      <StatGrid cols={3} items={[
        { label: 'Signals', value: d.signals.length },
        { label: 'Unconfirmed', value: d.signals.length - confirmed, accent: d.signals.length - confirmed ? 'var(--color-warn)' : undefined },
        { label: 'Confirmed by the register', value: confirmed },
      ]} />
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-3">
          <SectionHead icon={Rss}>Early signals</SectionHead>
          <span className="inline-flex items-center gap-1 text-[12.5px] text-[var(--color-mute)]">· {d.message.label}<InfoButton compact details={messageDetails(d.message)} /></span>
        </div>
        {d.signals.length === 0
          ? <div className="py-6 text-center text-[13px] text-[var(--color-faint)]">No early signals for your regulations at the moment.</div>
          : <div className="divide-y divide-[var(--color-line)]">
              {d.signals.map(s => (
                <div key={s.signal_id} className="py-3 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1.5 items-start">
                  <span className="min-w-0">
                    <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-[13px] text-[var(--color-ink)] hover:text-[var(--color-sky)] inline-flex items-start gap-1.5 leading-snug">
                      {s.title} <ExternalLink size={12} className="mt-1 shrink-0 text-[var(--color-faint)]" /></a>
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-[11.5px] text-[var(--color-faint)]">
                      <span>{s.authority}</span><span>·</span><span>{s.jurisdiction_name}</span><span>·</span><span>{s.published_at ? day(s.published_at) : 'Date not given'}</span>
                      {s.summary && <InfoButton compact details={{ title: s.title, sections: [
                        { heading: 'Summary', body: s.summary }, { heading: HEADING.sources, body: `${s.authority}, ${s.jurisdiction_name}` }] }} />}
                    </span>
                  </span>
                  <span className="inline-flex items-center gap-1 justify-self-end">
                    <StatusChip label={s.standing.label} tone={s.status === 'register_confirmed' ? 'good' : 'warn'} />
                    <InfoButton compact details={messageDetails(s.standing)} />
                  </span>
                  {s.topics.length > 0 && <span className="col-span-2 flex flex-wrap gap-1.5">
                    {s.topics.map(t => <span key={t} className="text-[11px] px-2 py-0.5 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)]">{t}</span>)}
                  </span>}
                </div>
              ))}
            </div>}
      </Card>
    </div>
  )
}
