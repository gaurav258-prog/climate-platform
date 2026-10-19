import { useState } from 'react'
import { CalendarClock, ChevronDown, ChevronRight, ExternalLink, ShieldCheck } from 'lucide-react'
import { Card, SectionHead, StatGrid } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { DetailsBody, HEADING, InfoButton, MessageLine, messageDetails } from '../../components/Details'
import { Block, HELD, PartsBar, Swatches, UrgencyChip, day, num, plural, urgency, type Coming, type Field, type InForce, type Outlook } from './shared'

// The Outlook tab: the regulations in force for you, and every change coming — on a timeline by date, then one line
// each with its urgency and how much of the data it asks for you already hold. A change opens in a side drawer.

const ABOUT_COMING = [
  { heading: HEADING.shows, body: 'Each change to the regulations you report under: when it takes effect, what it asks of you, and how much of that data your records already hold.' },
  { heading: HEADING.read, body: <ul className="list-disc pl-5 space-y-1">
    <li><b>Days</b> count to the date the change takes effect. Red is within three months, amber within a year.</li>
    <li><b>Date not set</b> means the regulator has not fixed a date. We do not estimate one.</li>
    <li><b>Newly detected</b> changes were spotted automatically in the official EU register and are being reviewed.</li>
    <li><b>Draft</b> changes are final drafts of new templates, not adopted yet.</li>
  </ul> },
  { heading: HEADING.sources, body: 'The official EU register (EUR-Lex) for dates and for the acts that amend or replace one another; our regulatory team’s register of announced changes; your own records for the data you already hold.' },
  { heading: HEADING.limits, body: 'A change listed here changes nothing in your filings until it takes effect. A detected change waits for our review.' },
]

export function OutlookTab({ d }: { d: Outlook }) {
  const [open, setOpen] = useState<Coming | null>(null)
  const [past, setPast] = useState(false)
  const ahead = d.coming.filter(c => c.phase !== 'in_force')
  const tookEffect = d.coming.filter(c => c.phase === 'in_force')
  return (
    <div className="space-y-5">
      <StatGrid cols={4} items={[
        { label: 'In force for you', value: d.summary.n_in_force },
        { label: 'Changes ahead', value: d.summary.n_ahead, accent: d.summary.n_ahead ? 'var(--color-sky)' : undefined },
        { label: 'Took effect', value: d.summary.n_took_effect },
        { label: 'Need data from you', value: d.summary.n_prepare, accent: d.summary.n_prepare ? 'var(--color-warn)' : undefined },
      ]} />

      <Card className="p-5 space-y-4">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <SectionHead icon={CalendarClock}>Coming changes</SectionHead>
          <InfoButton compact details={{ title: 'Coming changes', sections: ABOUT_COMING }} />
          {d.checked_at && <span className="ml-auto text-[11.5px] text-[var(--color-faint)]">Dates checked {day(d.checked_at)}</span>}
        </div>
        {d.coming.length === 0 ? <div className="text-[13px] text-[var(--color-mute)] py-4 text-center">No changes coming for your reports.</div> : <>
          <Timeline items={ahead} onOpen={setOpen} />
          <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
            {ahead.map((c, i) => <ChangeRow key={`a${i}`} c={c} onOpen={() => setOpen(c)} />)}
            {ahead.length === 0 && <div className="py-4 text-center text-[13px] text-[var(--color-faint)]">Nothing ahead: every listed change has taken effect.</div>}
          </div>
          {tookEffect.length > 0 && (
            <div>
              <button type="button" onClick={() => setPast(v => !v)} className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">
                {past ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Took effect · {tookEffect.length}
              </button>
              {past && <div className="divide-y divide-[var(--color-line)] mt-1">{tookEffect.map((c, i) => <ChangeRow key={`p${i}`} c={c} onOpen={() => setOpen(c)} />)}</div>}
            </div>
          )}
        </>}
      </Card>

      <InForceGrid list={d.in_force} />
      {open && <ChangeDrawer c={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

// Changes ahead on one time axis from today: a dot per dated change, coloured by urgency; undated ones after it.
function Timeline({ items, onOpen }: { items: Coming[]; onOpen: (c: Coming) => void }) {
  const dated = items.filter(c => c.phase === 'dated' && c.date && c.days != null)
  const undated = items.filter(c => c.phase === 'undated')
  if (!dated.length && !undated.length) return null
  const span = Math.max(365, ...dated.map(c => c.days! + 45))
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const years: { x: number; y: number }[] = []
  for (let y = today.getFullYear() + 1; ; y++) {
    const d = Math.round((new Date(`${y}-01-01T00:00:00`).getTime() - today.getTime()) / 86400000)
    if (d > span) break
    years.push({ x: (d / span) * 100, y })
  }
  return (
    <div className="flex flex-col sm:flex-row gap-4 sm:items-stretch">
      {dated.length > 0 && <div className="relative w-full sm:w-auto sm:flex-1 min-w-0 h-[88px] shrink-0" role="img" aria-label={`${plural(dated.length, 'dated change')} ahead on a time line from today`}>
        <div className="absolute left-0 right-0 top-[38px] h-0.5 rounded bg-[var(--color-line-2)]" />
        <span className="absolute left-0 top-[48px] text-[11px] text-[var(--color-faint)]">Today</span>
        <span className="absolute left-0 top-[31px] w-0.5 h-4 bg-[var(--color-faint)]" />
        {years.map(t => (
          <span key={t.y} className="absolute top-[34px] text-[10.5px] text-[var(--color-faint)] -translate-x-1/2" style={{ left: `${t.x}%` }}>
            <span className="block mx-auto w-px h-2.5 bg-[var(--color-line-2)]" /><span className="block mt-3.5">{t.y}</span>
          </span>
        ))}
        {dated.map((c, i) => {
          const u = urgency(c), x = (c.days! / span) * 100, up = i % 2 === 0
          return (
            <button key={i} type="button" onClick={() => onOpen(c)} title={`${c.title} · ${day(c.date)}`}
              className="absolute -translate-x-1/2 flex flex-col items-center group" style={{ left: `${x}%`, top: up ? 0 : 30 }}>
              {up && <span className="text-[10.5px] font-medium whitespace-nowrap mb-1" style={{ color: u.color }}>{u.label}</span>}
              <span className="w-3.5 h-3.5 rounded-full border-2 border-[var(--color-panel)] group-hover:scale-125 transition" style={{ background: u.color, marginTop: up ? 0 : 1 }} />
              {!up && <span className="text-[10.5px] font-medium whitespace-nowrap mt-1" style={{ color: u.color }}>{u.label}</span>}
            </button>
          )
        })}
      </div>}
      {undated.length > 0 && (
        <div className={`${dated.length ? 'sm:w-48' : 'w-full'} shrink-0 rounded-lg border border-dashed border-[var(--color-line-2)] px-3 py-2`}>
          <div className="text-[11.5px] text-[var(--color-faint)] mb-1.5">Date not set</div>
          <div className="flex flex-wrap gap-1.5">
            {undated.map((c, i) => <button key={i} type="button" onClick={() => onOpen(c)} title={c.title}
              className="w-3.5 h-3.5 rounded-full bg-[var(--color-slate)] hover:scale-125 transition" aria-label={c.title} />)}
          </div>
        </div>
      )}
    </div>
  )
}

// What a change asks of your data, as one bar: held, partly held, to provide.
function Readiness({ c }: { c: Coming }) {
  if (c.data_summary) {
    const s = c.data_summary
    return (
      <span className="flex items-center gap-2 min-w-0">
        <span className="flex-1 min-w-[4rem]"><PartsBar parts={(['have', 'partial', 'needed'] as const).map(k => ({ label: HELD[k].label, n: s[k], color: HELD[k].color }))} /></span>
        <span className="text-[11.5px] text-[var(--color-mute)] tabular-nums whitespace-nowrap">{num(s.have)} of {num(s.total)} held</span>
      </span>
    )
  }
  if (c.data_message) return <StatusChip label={c.data_message.label} tone="good" />
  if (c.prepare) return <StatusChip label="Data to prepare" tone="warn" />
  return <StatusChip label="Data to be confirmed" tone="neutral" />
}

function ChangeRow({ c, onOpen }: { c: Coming; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen}
      className="w-full text-left py-3 grid grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[6.5rem_minmax(0,1.5fr)_minmax(0,1fr)_6.5rem_1rem] items-center gap-x-4 gap-y-2 hover:bg-[var(--color-bg-2)] -mx-2 px-2 rounded-lg">
      <span className="order-2 md:order-none justify-self-end md:justify-self-start"><UrgencyChip c={c} /></span>
      <span className="min-w-0 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[13px] text-[var(--color-ink)] leading-snug">{c.title}</span>
        {c.source === 'detected' && <StatusChip label="Newly detected" tone="warn" />}
        {c.source === 'draft' && <StatusChip label="Draft" tone="neutral" />}
      </span>
      <span className="col-span-2 md:col-span-1 order-3 md:order-none min-w-0"><Readiness c={c} /></span>
      <span className="hidden md:block text-[12px] text-[var(--color-mute)] tabular-nums">{c.date ? day(c.date) : '—'}</span>
      <ChevronRight size={15} className="hidden md:block text-[var(--color-faint)]" />
    </button>
  )
}

function InForceGrid({ list }: { list: InForce[] }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-1.5 mb-3">
        <SectionHead icon={ShieldCheck}>In force for you</SectionHead>
        <InfoButton compact details={{ title: 'In force for you', sections: [
          { heading: HEADING.shows, body: 'The regulations you report under today, with how often you report. Open one for what it requires and who supervises it.' },
        ] }} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {list.map(f => (
          <div key={f.framework} className="rounded-lg border border-[var(--color-line-2)] p-3 flex flex-col gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="text-[13px] font-medium text-[var(--color-ink)] leading-snug">{f.name}</span>
              <InfoButton compact details={{ title: f.name, sections: [
                { heading: 'What it requires', body: f.requires },
                ...(f.authority ? [{ heading: 'Supervised by', body: f.authority }] : []),
                ...(f.citation ? [{ heading: 'Legal basis', body: f.citation }] : []),
                ...(f.url ? [{ heading: 'Official text', body: <a href={f.url} target="_blank" rel="noopener noreferrer" className="text-[var(--color-sky)] hover:underline inline-flex items-center gap-1">Open in the EU register <ExternalLink size={12} /></a> }] : []),
              ] }} />
            </div>
            {f.frequency && <span className="mt-auto inline-flex items-start gap-1.5 text-[11.5px] text-[var(--color-mute)] leading-snug"><CalendarClock size={12} className="mt-0.5 shrink-0" />{f.frequency.charAt(0).toUpperCase() + f.frequency.slice(1)}</span>}
          </div>
        ))}
      </div>
    </Card>
  )
}

function FieldRow({ f }: { f: Field }) {
  const h = HELD[f.status]
  return (
    <div className="py-2 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 border-b border-[var(--color-line)] last:border-0">
      <span className="block min-w-0 text-[12.5px] text-[var(--color-ink)] leading-snug">{f.field}</span>
      <span className="inline-flex items-center gap-1">
        <StatusChip label={f.message.label} tone={f.status === 'have' ? 'good' : f.status === 'partial' ? 'warn' : 'neutral'} />
        <InfoButton compact details={{ title: f.field, sections: [...messageDetails(f.message).sections, ...(f.guidance ? [{ heading: 'What to give', body: f.guidance }] : [])] }} />
      </span>
      {f.total != null && f.total > 0 && f.held != null && (
        <span className="col-span-2 flex items-center gap-2">
          <span className="flex-1"><PartsBar height={5} parts={[{ label: h.label, n: f.held, color: h.color }, { label: 'Still to provide', n: f.total - f.held, color: 'var(--color-line-2)' }]} /></span>
          <span className="text-[11px] text-[var(--color-faint)] tabular-nums">{num(f.held)} / {num(f.total)}</span>
        </span>
      )}
    </div>
  )
}

function ChangeDrawer({ c, onClose }: { c: Coming; onClose: () => void }) {
  return (
    <Drawer label={c.title} onClose={onClose} className="w-full max-w-2xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5 space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[17px] font-semibold text-[var(--color-ink)] leading-snug">{c.title}</div>
          <div className="flex flex-wrap items-center gap-2 mt-1.5">
            <UrgencyChip c={c} />
            {c.source === 'detected' && <StatusChip label="Newly detected" tone="warn" />}
            {c.source === 'draft' && <StatusChip label="Draft" tone="neutral" />}
          </div>
        </div>
        <CloseButton onClick={onClose} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-[var(--color-line-2)] px-3 py-2.5">
          <div className="text-[11.5px] text-[var(--color-faint)]">Takes effect</div>
          <div className="text-[15px] font-medium text-[var(--color-ink)] mt-0.5">{c.date ? day(c.date) : c.would_apply_from ? `${day(c.would_apply_from)}, if adopted` : 'Not set'}</div>
          <div className="text-[11.5px] text-[var(--color-mute)] mt-1"><MessageLine m={c.phase_message} /></div>
          {c.verified && <div className={`text-[11.5px] mt-1 ${c.date_moved ? 'text-[var(--color-warn)]' : 'text-[var(--color-good)]'}`}><MessageLine m={c.verified} /></div>}
        </div>
        <div className="rounded-lg border border-[var(--color-line-2)] px-3 py-2.5">
          <div className="text-[11.5px] text-[var(--color-faint)]">Your records it reaches</div>
          <div className="text-[15px] font-medium text-[var(--color-ink)] mt-0.5">{c.impact?.scope ? num(c.impact.scope.n) : '—'}</div>
          <div className="text-[11.5px] text-[var(--color-mute)] mt-1">{c.impact?.scope?.label ?? 'Not counted for this change'}</div>
        </div>
      </div>

      {c.message && <Block title={c.message.label}><DetailsBody sections={messageDetails(c.message).sections} /></Block>}
      {c.source === 'curated' && c.whats_changing && <Block title="What changes"><p className="text-[13.5px] leading-relaxed text-[var(--color-ink)] m-0">{c.whats_changing}</p></Block>}

      {c.draft && (
        <Block title="Templates against the version in force">
          <PartsBar height={12} parts={[
            { label: 'Added', n: c.draft.added, color: 'var(--color-sky)' }, { label: 'Changed', n: c.draft.changed, color: 'var(--color-warn)' },
            { label: 'Removed', n: c.draft.removed, color: 'var(--color-bad)' }, { label: 'Unchanged', n: c.draft.unchanged, color: 'var(--color-line-2)' }]} />
          <div className="flex flex-wrap items-center justify-between gap-2 mt-2">
            <Swatches parts={[{ label: `Added ${c.draft.added}`, color: 'var(--color-sky)' }, { label: `Changed ${c.draft.changed}`, color: 'var(--color-warn)' }, { label: `Removed ${c.draft.removed}`, color: 'var(--color-bad)' }, { label: `Unchanged ${c.draft.unchanged}`, color: 'var(--color-line-2)' }]} />
          </div>
        </Block>
      )}

      {c.data_fields.length > 0 && (
        <Block title="The data it asks for" aside={c.data_summary && <span className="text-[11.5px] text-[var(--color-mute)]">{num(c.data_summary.have)} of {num(c.data_summary.total)} held</span>}
          info={[{ heading: HEADING.read, body: 'Each field the change asks for, and how many of your records already hold it. A field we cannot confirm from your records is listed for you to provide.' }]}>
          <div>{c.data_fields.map((f, i) => <FieldRow key={i} f={f} />)}</div>
        </Block>
      )}
      {(c.prepare || c.data_tbc || c.data_message) && (
        <Block title="Your side">
          <p className="text-[13.5px] leading-relaxed text-[var(--color-ink)] m-0">{c.prepare ?? c.data_tbc ?? c.data_message?.detail?.what}</p>
        </Block>
      )}
      {c.source === 'curated' && c.when && <Block title="Timing"><p className="text-[13px] text-[var(--color-mute)] m-0">{c.when}</p></Block>}
      {c.citation && (
        <DetailsBody sections={[{ heading: 'The act', body: c.citation },
          ...(c.url ? [{ heading: 'Official text', body: <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-[var(--color-sky)] hover:underline inline-flex items-center gap-1.5">Open the official text <ExternalLink size={13} /></a> }] : [])]} />
      )}
    </Drawer>
  )
}
