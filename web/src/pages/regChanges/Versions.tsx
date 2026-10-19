import { useState } from 'react'
import { ChevronRight, ExternalLink, GitBranch } from 'lucide-react'
import { Card, SectionHead, StatGrid } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { HEADING, InfoButton, MessageLine, messageDetails } from '../../components/Details'
import { Block, Swatches, day, num, plural, type Act, type FwVersion, type Versions } from './shared'

// The Version register tab: for each regulation you report under, the act your filings are prepared under, the acts
// that amend or replace it and when — drawn on one time line. A regulation opens in a side drawer with every act.

const MARK = {
  act: { label: 'In force', color: 'var(--color-sky)' },
  amended: { label: 'Amended', color: 'var(--color-warn)' },
  replaced: { label: 'Replaced', color: 'var(--color-bad)' },
  ahead: { label: 'Date ahead', color: 'var(--color-slate)' },
}

const ABOUT = [
  { heading: HEADING.shows, body: 'Each regulation you report under, as a line of its legal versions: the act in force, the acts that amend it, and any act that replaces it.' },
  { heading: HEADING.read, body: 'The bar is the act in force, from the date it applied. Amber ticks are amending acts, a red mark is an act that replaces it in whole or in part, and a grey mark is a date still ahead. Every filing records the version it was prepared under.' },
  { heading: HEADING.sources, body: 'The official EU register (EUR-Lex), read for every act we track.' },
]

type Mark = { x: string; kind: keyof typeof MARK; title: string }
const ms = (s: string) => new Date(`${s.slice(0, 10)}T00:00:00`).getTime()

function marks(f: FwVersion): { bars: { from: string; to: string | null; title: string }[]; ticks: Mark[] } {
  const bars: { from: string; to: string | null; title: string }[] = [], ticks: Mark[] = []
  for (const a of f.acts.filter(a => a.live)) {
    if (a.in_force_since) bars.push({ from: a.in_force_since, to: a.ends, title: a.title })
    a.amendments.forEach(m => m.since && ticks.push({ x: m.since, kind: 'amended', title: `${MARK.amended.label} · ${day(m.since)}` }))
    a.replaced_by.forEach(r => r.since && ticks.push({ x: r.since, kind: 'replaced', title: `${r.relation_label ?? MARK.replaced.label} · ${day(r.since)}` }))
    a.future.forEach(d => ticks.push({ x: d, kind: 'ahead', title: `${MARK.ahead.label} · ${day(d)}` }))
  }
  return { bars, ticks }
}

export function VersionsTab({ d }: { d: Versions }) {
  const [open, setOpen] = useState<FwVersion | null>(null)
  if (d.frameworks.length === 0) return <Card className="p-8 text-center text-[13px] text-[var(--color-mute)]">No regulation tracked for your reports yet.</Card>
  const acts = d.frameworks.flatMap(f => f.acts)
  const today = new Date().toISOString().slice(0, 10)
  const all = d.frameworks.flatMap(f => { const m = marks(f); return [...m.bars.flatMap(b => [b.from, ...(b.to ? [b.to] : [])]), ...m.ticks.map(t => t.x)] })
  const lo = ms(`${Math.min(...all.map(s => Number(s.slice(0, 4))), Number(today.slice(0, 4)))}-01-01`)
  const hi = ms(`${Math.max(...all.map(s => Number(s.slice(0, 4))), Number(today.slice(0, 4))) + 1}-01-01`)
  const pos = (s: string) => `${Math.min(100, Math.max(0, ((ms(s) - lo) / (hi - lo)) * 100))}%`
  const years: number[] = []
  for (let y = new Date(lo).getFullYear(); y <= new Date(hi).getFullYear(); y++) years.push(y)
  return (
    <div className="space-y-5">
      <StatGrid cols={4} items={[
        { label: 'Regulations tracked', value: d.summary.n },
        { label: 'New version ahead', value: d.summary.n_upcoming, accent: d.summary.n_upcoming ? 'var(--color-warn)' : undefined },
        { label: 'Amending acts', value: acts.reduce((n, a) => n + a.amendments.length, 0) },
        { label: 'Acts replaced', value: acts.filter(a => a.replaced_by.length > 0).length, accent: acts.some(a => a.replaced_by.length) ? 'var(--color-bad)' : undefined },
      ]} />
      <Card className="p-5 space-y-3">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          <SectionHead icon={GitBranch}>Versions</SectionHead>
          <InfoButton compact details={{ title: 'Versions', sections: ABOUT }} />
          <span className="ml-auto"><Swatches parts={Object.values(MARK)} /></span>
        </div>
        <div className="hidden md:grid grid-cols-[minmax(0,16rem)_minmax(0,1fr)_1rem] gap-4 text-[10.5px] text-[var(--color-faint)]">
          <span />
          <span className="relative h-3">{years.map(y => <span key={y} className="absolute -translate-x-1/2" style={{ left: pos(`${y}-01-01`) }}>{y}</span>)}</span>
          <span />
        </div>
        <div className="divide-y divide-[var(--color-line)]">
          {d.frameworks.map(f => {
            const m = marks(f)
            return (
              <button key={f.framework} type="button" onClick={() => setOpen(f)}
                className="w-full text-left py-3 grid md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_1rem] items-center gap-x-4 gap-y-2 hover:bg-[var(--color-bg-2)] -mx-2 px-2 rounded-lg">
                <span className="min-w-0">
                  <span className="block text-[13px] text-[var(--color-ink)] leading-snug">{f.name}</span>
                  <span className="block text-[11.5px] text-[var(--color-faint)] mt-0.5">{f.current_since ? `In force since ${day(f.current_since)}` : 'Dates not read yet'}</span>
                </span>
                <span className="relative block" style={{ height: Math.max(28, 18 + m.bars.length * 7) }} role="img" aria-label={`${f.name}: ${plural(m.bars.length, 'act')}, ${plural(m.ticks.length, 'dated event')}`}>
                  {years.map(y => <span key={y} className="absolute top-0 bottom-0 w-px bg-[var(--color-line)]" style={{ left: pos(`${y}-01-01`) }} />)}
                  <span className="absolute top-0 bottom-0 w-0.5 bg-[var(--color-faint)]" style={{ left: pos(today) }} title={`Today · ${day(today)}`} />
                  {m.bars.map((b, i) => <span key={i} title={`${b.title} · ${day(b.from)} – ${b.to ? day(b.to) : 'open'}`} className="absolute h-1.5 rounded-full"
                    style={{ top: 9 + i * 7, left: pos(b.from), width: `calc(${pos(b.to ?? new Date(hi).toISOString())} - ${pos(b.from)})`, background: MARK.act.color }} />)}
                  {m.ticks.map((t, i) => <span key={i} title={t.title} className="absolute top-1 bottom-1 w-2 -translate-x-1/2 rounded-sm border border-[var(--color-panel)]"
                    style={{ left: pos(t.x), background: MARK[t.kind].color }} />)}
                </span>
                <ChevronRight size={15} className="hidden md:block text-[var(--color-faint)]" />
              </button>
            )
          })}
        </div>
        {d.checked && <div className="text-[11.5px] text-[var(--color-faint)]"><MessageLine m={d.checked} /></div>}
      </Card>
      {open && <RegulationDrawer f={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

const eurlex = (celex: string) => `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:${celex}`

function ActCard({ a }: { a: Act }) {
  return (
    <div className="rounded-lg border border-[var(--color-line-2)] p-3 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-[13px] text-[var(--color-ink)] hover:text-[var(--color-sky)] inline-flex items-start gap-1.5 min-w-0">
          {a.title} <ExternalLink size={12} className="mt-1 shrink-0 text-[var(--color-faint)]" /></a>
        <StatusChip label={a.role_label} tone="neutral" />
      </div>
      {a.not_read
        ? <div className="text-[12px] text-[var(--color-faint)] inline-flex items-center gap-1">{a.not_read.label}<InfoButton compact details={messageDetails(a.not_read)} /></div>
        : <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[var(--color-mute)]">
            <span>In force since <b className="text-[var(--color-ink)] font-medium">{day(a.in_force_since)}</b></span>
            {a.next_effective && <span>Next date <b className="text-[var(--color-ink)] font-medium">{day(a.next_effective)}</b></span>}
            {a.ends && <span>Ends <b className="text-[var(--color-ink)] font-medium">{day(a.ends)}</b></span>}
          </div>}
      {a.replaced_by.map(r => (
        <div key={r.celex} className="text-[12px] text-[var(--color-bad)]">
          {r.relation_label}{' '}<a href={eurlex(r.celex)} target="_blank" rel="noopener noreferrer" className="underline">{r.title}</a>{r.since ? ` · ${day(r.since)}` : ''}
        </div>))}
      {a.amendments.length > 0 && (
        <ul className="space-y-1">
          {a.amendments.map(m => (
            <li key={m.celex} className="flex flex-wrap items-center gap-x-2 text-[12px]">
              <span className="w-2 h-2 rounded-sm" style={{ background: MARK.amended.color }} />
              <a href={eurlex(m.celex)} target="_blank" rel="noopener noreferrer" className="text-[var(--color-mute)] hover:text-[var(--color-sky)] underline">{m.title}</a>
              {m.since && <span className="text-[var(--color-faint)] tabular-nums">{day(m.since)}</span>}
            </li>))}
        </ul>)}
    </div>
  )
}

function RegulationDrawer({ f, onClose }: { f: FwVersion; onClose: () => void }) {
  const amended = f.acts.reduce((n, a) => n + a.amendments.length, 0)
  return (
    <Drawer label={f.name} onClose={onClose} className="w-full max-w-2xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5 space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[17px] font-semibold text-[var(--color-ink)] leading-snug">{f.name}</div>
          {f.authority && <div className="text-[12px] text-[var(--color-mute)] mt-1">{f.authority}</div>}
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[['In force since', day(f.current_since)], ['Amending acts', num(amended)], ['Next version', f.upcoming_effective ? day(f.upcoming_effective) : 'None set']].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-[var(--color-line-2)] px-3 py-2.5">
            <div className="text-[11.5px] text-[var(--color-faint)]">{k}</div>
            <div className="text-[14px] font-medium text-[var(--color-ink)] mt-0.5">{v}</div>
          </div>))}
      </div>
      <Block title="Acts" info={ABOUT.slice(1)}>
        <div className="space-y-2.5">{f.acts.map(a => <ActCard key={a.celex} a={a} />)}</div>
      </Block>
    </Drawer>
  )
}
