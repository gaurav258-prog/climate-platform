import { Fragment, type ReactNode, useState } from 'react'
import { Activity, ChevronRight, Wheat, Wind } from 'lucide-react'
import clsx from 'clsx'
import { DetailsBody, HEADING, InfoButton, messageDetails, type DetailSection } from '../Details'
import { Dialog } from '../Dialog'
import { pressable } from '../../lib/pressable'
import { balance } from '../../lib/money'
import type { Definition, Kind, Message, ObservedEvent, Source } from './types'

// The observed record, drawn the same way on every screen that shows it (Climate track record, Underwriting review,
// the realised-exposure card): an event is an icon, its name, its class or magnitude as a chip, its year and how close it
// came; everything else about it opens in a pop-up. Words a screen needs beyond these come from the server's catalogue.

export const KIND_COLOR: Record<Kind, string> = { storm: 'var(--color-sky)', earthquake: 'var(--scn-disorderly)', crop_shock: 'var(--color-warn)' }
export const KIND_NAME: Record<Kind, string> = { storm: 'Storm', earthquake: 'Earthquake', crop_shock: 'Production shock' }
const ICON: Record<Kind, typeof Wind> = { storm: Wind, earthquake: Activity, crop_shock: Wheat }

export function KindIcon({ kind, size = 14 }: { kind: Kind; size?: number }) {
  const I = ICON[kind]
  return <I size={size} style={{ color: KIND_COLOR[kind] }} className="shrink-0" aria-label={KIND_NAME[kind]} />
}

export function Chip({ children, color }: { children: ReactNode; color: string }) {
  return (
    <span className="inline-flex items-center text-[11px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ color, background: `color-mix(in oklab, ${color} 14%, transparent)` }}>{children}</span>
  )
}

const day = (iso?: string | null) => iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

// a country's name in the reader's language from its ISO 3166 code (the code itself if the browser has no name for it)
const REGION = typeof Intl !== 'undefined' && 'DisplayNames' in Intl ? new Intl.DisplayNames(undefined, { type: 'region' }) : null
const country = (cc?: string) => { try { return (cc && REGION?.of(cc)) || cc || '' } catch { return cc ?? '' } }

export const eventTitle = (e: ObservedEvent) => e.kind === 'crop_shock' ? `${e.commodity} · ${country(e.country)}` : (e.name ?? KIND_NAME[e.kind])
const radius = (e: ObservedEvent, d?: Definition) => d ? (e.kind === 'storm' ? d.storm_radius_km : d.quake_radius_km) : null

// How close an event came, as a bar: full when it passed over the place, empty at the edge of reach.
export function Proximity({ km, reach }: { km?: number; reach: number | null }) {
  if (km == null) return null
  const share = reach ? Math.max(0.04, 1 - km / reach) : 0
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)] tabular-nums whitespace-nowrap">
      {reach != null && <span className="relative h-1.5 w-12 rounded-full bg-[var(--color-panel-2)] overflow-hidden">
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${100 * share}%`, background: 'var(--color-mute)' }} />
      </span>}
      {km} km
    </span>
  )
}

// The facts of one event, for its pop-up.
export function eventSections(e: ObservedEvent, d?: Definition): DetailSection[] {
  const rows: [string, ReactNode][] = e.kind === 'crop_shock' ? [
    ['Crop and country', `${e.commodity}, ${country(e.country)}`], ['Season', e.year ?? '—'],
    ['National production', `${e.yoy_change_pct} % on the year before`], ['Your annual spend there', balance(e.spend_eur)],
  ] : [
    ['Kind', KIND_NAME[e.kind]],
    [e.kind === 'storm' ? 'Closest approach' : 'Date', day(e.date)],
    ...(e.kind === 'storm' ? [['Class within reach', e.strength], ['Strongest wind within reach', e.max_wind_kt != null ? `${e.max_wind_kt} knots` : '—']] as [string, ReactNode][]
      : [['Magnitude', e.magnitude?.toFixed(1) ?? '—'], ['Depth', e.depth_km != null ? `${e.depth_km} km` : '—']] as [string, ReactNode][]),
    [e.kind === 'storm' ? 'Closest distance of its centre' : 'Distance of its epicentre', e.closest_km != null ? `${e.closest_km} km${radius(e, d) ? ` (reach ${radius(e, d)} km)` : ''}` : '—'],
    ...(e.n_assets != null ? [['Your assets within reach', `${e.n_assets} · ${balance(e.value_exposed_eur)}`]] as [string, ReactNode][] : []),
  ]
  return [
    { heading: HEADING.shows, body: (
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 m-0 text-[13px]">
        {rows.map(([k, v]) => <Fragment key={k}><dt className="text-[var(--color-mute)]">{k}</dt><dd className="m-0 tabular-nums">{v}</dd></Fragment>)}
      </dl>) },
    { heading: HEADING.read, body: e.kind === 'storm'
      ? 'The class and wind are the storm’s own, from its best track, at its strongest while its centre was within reach. They are not the wind at the place.'
      : e.kind === 'earthquake' ? 'The magnitude is the earthquake’s own, at its epicentre. Shaking at the place depends on the distance, the depth and the ground.'
      : 'A fall in national production can have causes other than weather.' },
  ]
}

export function EventDialog({ e, d, onClose }: { e: ObservedEvent; d?: Definition; onClose: () => void }) {
  return (
    <Dialog title={eventTitle(e)} onClose={onClose} className="max-w-lg"><DetailsBody sections={eventSections(e, d)} /></Dialog>
  )
}

// One event in a list: what it was, how strong, when, how close. `children` (a book's assets) opens below it.
export function EventRow({ e, d, onOpen, trailing, expanded, onToggle, children }: {
  e: ObservedEvent; d?: Definition; onOpen?: () => void; trailing?: ReactNode
  expanded?: boolean; onToggle?: () => void; children?: ReactNode
}) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-[13px]">
        {onToggle
          ? <button type="button" onClick={onToggle} aria-expanded={expanded} aria-label={expanded ? 'Hide the assets' : 'Show the assets'}
              className="text-[var(--color-sky)]"><ChevronRight size={14} className={clsx('transition-transform', expanded && 'rotate-90')} /></button>
          : <span className="w-[14px]" />}
        <KindIcon kind={e.kind} />
        <span {...pressable(onOpen)} className={clsx('font-medium text-[var(--color-ink)] min-w-0', onOpen && 'cursor-pointer hover:text-[var(--color-sky)] underline decoration-dotted decoration-[var(--color-line-2)] underline-offset-2')}>
          {eventTitle(e)}
        </span>
        <Chip color={KIND_COLOR[e.kind]}>{e.strength}</Chip>
        <span className="text-[12px] text-[var(--color-faint)] tabular-nums">{e.year ?? '—'}</span>
        <span className="flex-1 min-w-0" />
        {trailing ?? <Proximity km={e.closest_km} reach={radius(e, d)} />}
      </div>
      {expanded && children}
    </div>
  )
}

// A list of events with their pop-ups; `limit` shown, the rest one click away. `total` is how many the record holds when
// the server sent only the most recent of them.
export function EventList({ events, d, limit = 8, total, row }: {
  events: ObservedEvent[]; d?: Definition; limit?: number; total?: number
  row?: (e: ObservedEvent, open: () => void) => ReactNode
}) {
  const [open, setOpen] = useState<ObservedEvent | null>(null)
  const [all, setAll] = useState(false)
  const shown = all ? events : events.slice(0, limit)
  return (
    <>
      <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
        {shown.map((e, i) => <div key={e.id ?? i}>{row ? row(e, () => setOpen(e)) : <EventRow e={e} d={d} onOpen={() => setOpen(e)} />}</div>)}
      </div>
      {events.length > limit && (
        <button type="button" onClick={() => setAll(!all)} className="mt-2 text-[12px] text-[var(--color-sky)] hover:underline">
          {all ? 'Show fewer' : (total ?? 0) > events.length ? `Show the ${events.length} most recent` : `Show all ${events.length}`}
        </button>
      )}
      {open && <EventDialog e={open} d={d} onClose={() => setOpen(null)} />}
    </>
  )
}

// The observed events along the years the catalogues cover: one dot per event, at its date.
export function Timeline({ events, sources, onPick }: { events: ObservedEvent[]; sources: Source[]; onPick?: (e: ObservedEvent) => void }) {
  const dated = events.filter(e => e.date || e.year)
  const t = (e: ObservedEvent) => new Date(e.date ?? `${e.year}-07-01`).getTime()
  const starts = sources.map(s => new Date(s.first).getTime()), ends = sources.map(s => new Date(s.last).getTime())
  const lo = Math.min(...starts, ...dated.map(t)), hi = Math.max(...ends, ...dated.map(t))
  if (!isFinite(lo) || !isFinite(hi) || hi <= lo) return null
  const x = (ms: number) => 2 + 96 * (ms - lo) / (hi - lo)
  const y0 = new Date(lo).getFullYear(), y1 = new Date(hi).getFullYear()
  const step = Math.max(1, Math.ceil((y1 - y0) / 6 / 5) * 5)
  const ticks = Array.from({ length: Math.floor((y1 - y0) / step) + 1 }, (_, i) => y0 + i * step)
  return (
    <div className="relative h-14 select-none" role="img" aria-label="Observed events by date">
      {sources.map(s => (
        <div key={s.kind} className="absolute h-1 rounded-full" title={`${s.name}: ${day(s.first)} to ${day(s.last)}`}
          style={{ left: `${x(new Date(s.first).getTime())}%`, right: `${100 - x(new Date(s.last).getTime())}%`, top: s.kind === 'storm' ? 20 : 30,
            background: `color-mix(in oklab, ${KIND_COLOR[s.kind]} 22%, transparent)` }} />
      ))}
      {dated.map((e, i) => (
        <button key={e.id ?? i} type="button" onClick={() => onPick?.(e)} title={`${eventTitle(e)} · ${e.year ?? ''}`}
          className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--color-panel)] hover:scale-125 transition"
          style={{ left: `${x(t(e))}%`, top: e.kind === 'storm' ? 21 : 31, width: 12, height: 12, background: KIND_COLOR[e.kind] }} />
      ))}
      {ticks.map(y => (
        <span key={y} className="absolute bottom-0 -translate-x-1/2 text-[10.5px] text-[var(--color-faint)] tabular-nums"
          style={{ left: `${x(new Date(`${y}-01-01`).getTime())}%` }}>{y}</span>
      ))}
    </div>
  )
}

// The "Data sources" body: each catalogue by name, with the dates it covers — read from the data.
export function sourcesBody(sources: Source[]): ReactNode {
  return (
    <ul className="m-0 pl-4 space-y-1">
      {sources.map(s => <li key={s.kind}>{s.name}: {day(s.first)} to {day(s.last)} ({s.years} years).</li>)}
    </ul>
  )
}

// A server message's pop-up sections followed by the data sources.
export function withSources(m: Message, sources?: Source[]): DetailSection[] {
  return [...messageDetails(m).sections, ...(sources?.length ? [{ heading: HEADING.sources, body: sourcesBody(sources) }] : [])]
}

export function MessageInfo({ m, sources }: { m: Message; sources?: Source[] }) {
  return <InfoButton compact details={{ title: m.label, sections: withSources(m, sources) }} />
}
