import { useState } from 'react'
import { Download, History, Gauge, Search } from 'lucide-react'
import { api, apiMessage, download } from '../lib/api'
import { toast } from '../lib/toast'
import { bucketLabel } from '../lib/labels'
import { Button, Card, PageHeader, SectionHead, StatGrid } from '../components/ui'
import { HBar } from '../components/Charts'
import { HEADING, InfoButton, MessageLine } from '../components/Details'
import ReviewTabs from '../components/ReviewTabs'
import { Chip, EventDialog, EventList, MessageInfo, Timeline } from '../components/observed/Observed'
import type { Definition, Message, ObservedEvent, Source } from '../components/observed/types'

// Climate track record, to the UI standard (2026-10-16): for any coordinates, what the observed catalogues recorded
// there — a timeline and a list, each event's facts one click away — and, kept apart and labelled as modelled, how the
// place scores today. Every explanation is the server's catalogue words (codes realized.place.*).

interface Hazard {
  hazard: string; label: string; score: number; bucket: string; scale: string; scale_name: string; headline: boolean; as_of: string | null
}
interface Dossier {
  location: { name: string | null; lat: number; lon: number }
  realized: { n_events: number; n_storms: number; n_earthquakes: number; events: ObservedEvent[]; sources: Source[]; definition: Definition; message: Message }
  current_risk: Hazard[]; headline_current: Hazard | null
  modelled: { message: Message; context: Message | null }
}

const ABOUT = [
  { heading: HEADING.shows, body: 'For any coordinates: the storms and earthquakes the observed catalogues recorded within reach of the place, and, kept apart, how the place scores on our hazard models today.' },
  { heading: HEADING.read, body: 'The observed record is fact: each event’s class, wind, magnitude and distance are the catalogue’s own. The scores are modelled: a ranking of places from 0 to 100, not a probability. A crossing is not a loss.' },
  { heading: HEADING.limits, body: 'The catalogues hold tropical cyclones and earthquakes of magnitude 5 or more, over the years they cover; floods, wildfires, hail and European windstorms have no observed catalogue here. A diligence dossier, not a regulatory filing.' },
]
// example places to try (inputs, not figures the page reports)
const EXAMPLES: [string, number, number][] = [
  ['Warehouse · south-west Portugal', 37.95, -8.87],
  ['Vineyard · Valencia', 39.47, -0.38],
  ['Plant · Sicily', 37.5, 15.09],
  ['Port · Rotterdam', 51.95, 4.14],
]
const BAND: Record<string, string> = { VH: 'var(--color-bad)', H: 'var(--scn-disorderly)', M: 'var(--scn-orderly)', L: 'var(--color-faint)' }
const input = 'rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] text-[var(--color-ink)]'
const qs = (lat: string, lon: string, name: string) => `lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}${name ? `&name=${encodeURIComponent(name)}` : ''}`

export default function TrackRecord() {
  const [lat, setLat] = useState(String(EXAMPLES[0][1]))
  const [lon, setLon] = useState(String(EXAMPLES[0][2]))
  const [name, setName] = useState(EXAMPLES[0][0])
  const [d, setD] = useState<Dossier | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async (la = lat, lo = lon, nm = name) => {
    setBusy(true)
    try { setD(await api.get<Dossier>(`/v1/realized-exposure/track-record?${qs(la, lo, nm)}`)) }
    catch (e) { toast.error(apiMessage(e, 'The track record could not be built. Check the coordinates.')) }
    finally { setBusy(false) }
  }
  const pdf = () => download(`/v1/realized-exposure/track-record.pdf?${qs(lat, lon, name)}`, 'climate-track-record.pdf')
    .catch(e => toast.error(apiMessage(e, 'The dossier could not be downloaded.')))

  return (
    <div className="fadeup space-y-6 max-w-5xl">
      <ReviewTabs />
      <PageHeader eyebrow="Review · diligence" title="Climate track record" lead="What has crossed a place, and how it scores today." about={ABOUT}
        actions={d && <Button variant="ghost" onClick={pdf}><Download size={14} />Dossier (PDF)</Button>} />

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[12px] text-[var(--color-mute)]">Latitude
            <input value={lat} onChange={e => setLat(e.target.value)} inputMode="decimal" className={`${input} w-28 tabular-nums`} /></label>
          <label className="flex flex-col gap-1 text-[12px] text-[var(--color-mute)]">Longitude
            <input value={lon} onChange={e => setLon(e.target.value)} inputMode="decimal" className={`${input} w-28 tabular-nums`} /></label>
          <label className="flex flex-col gap-1 flex-1 min-w-[180px] text-[12px] text-[var(--color-mute)]">Name (optional)
            <input value={name} onChange={e => setName(e.target.value)} className={`${input} w-full`} /></label>
          <Button onClick={() => run()} disabled={busy}><Search size={14} />{busy ? 'Building…' : 'Get track record'}</Button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 mt-3">
          <span className="text-[12px] text-[var(--color-faint)] mr-1">Try</span>
          {EXAMPLES.map(([nm, la, lo]) => (
            <button key={nm} type="button" onClick={() => { setLat(String(la)); setLon(String(lo)); setName(nm); run(String(la), String(lo), nm) }}
              className="text-[12px] px-2.5 py-1 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">{nm}</button>
          ))}
        </div>
      </Card>

      {d && <Result d={d} />}
    </div>
  )
}

function Result({ d }: { d: Dossier }) {
  const r = d.realized, top = d.headline_current
  return (
    <>
      <div>
        <div className="text-[15px] font-semibold text-[var(--color-ink)]">{d.location.name || 'This place'}</div>
        <div className="text-[12px] text-[var(--color-faint)] tabular-nums">{d.location.lat.toFixed(4)}, {d.location.lon.toFixed(4)}</div>
      </div>
      <StatGrid cols={4} items={[
        { label: 'Observed events', value: r.n_events, accent: r.n_events ? 'var(--color-sky)' : undefined, sub: 'from the catalogues' },
        { label: 'Storms', value: r.n_storms },
        { label: 'Earthquakes', value: r.n_earthquakes },
        { label: 'Highest modelled score', value: top ? top.score.toFixed(0) : '—', sub: top ? top.label : 'not scored', accent: top ? BAND[top.bucket] : undefined },
      ]} />
      <Observed r={r} />
      <Modelled d={d} />
    </>
  )
}

function Observed({ r }: { r: Dossier['realized'] }) {
  const [pick, setPick] = useState<ObservedEvent | null>(null)
  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center gap-2">
        <SectionHead icon={History}>Observed record</SectionHead>
        <MessageInfo m={r.message} sources={r.sources} />
      </div>
      <Timeline events={r.events} sources={r.sources} onPick={setPick} />
      {r.events.length === 0
        ? <MessageLine m={r.message} className="text-[13px] text-[var(--color-mute)]" />
        : <EventList events={r.events} d={r.definition} />}
      {pick && <EventDialog e={pick} d={r.definition} onClose={() => setPick(null)} />}
    </Card>
  )
}

function Modelled({ d }: { d: Dossier }) {
  const [context, setContext] = useState(false)
  const likely = d.current_risk.filter(h => h.headline)
  const other = d.current_risk.filter(h => !h.headline)
  const m = d.modelled
  const dates = [...new Set(d.current_risk.map(h => h.as_of).filter((x): x is string => !!x))].sort()
  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SectionHead icon={Gauge}>Modelled today</SectionHead>
          <InfoButton compact details={{ title: m.message.label, sections: [
            ...(m.message.detail?.what ? [{ heading: HEADING.shows, body: m.message.detail.what }] : []),
            ...(m.message.detail?.why ? [{ heading: HEADING.read, body: m.message.detail.why }] : []),
            ...(dates.length ? [{ heading: 'As of', body: dates[0] === dates[dates.length - 1] ? dates[0] : `${dates[0]} to ${dates[dates.length - 1]}` }] : []),
            ...(m.message.detail?.next ? [{ heading: 'More', body: m.message.detail.next }] : []),
          ] }} />
        </div>
        <Chip color="var(--color-slate)">Modelled</Chip>
      </div>
      {d.current_risk.length === 0 ? <MessageLine m={m.message} className="text-[13px] text-[var(--color-mute)]" /> : (
        <>
          <HBar data={likely.map(h => ({ label: h.label, value: h.score, color: BAND[h.bucket], sub: bucketLabel(h.bucket) }))}
            format={v => v.toFixed(0)} labelWidth="w-36 sm:w-60" />
          {other.length > 0 && m.context && (
            <div>
              <button type="button" onClick={() => setContext(!context)} aria-expanded={context}
                className="text-[12px] text-[var(--color-sky)] hover:underline">{context ? 'Hide' : 'Show'} context scales ({other.length})</button>
              {context && (
                <div className="mt-2 space-y-1.5">
                  <MessageLine m={m.context} className="text-[12px] text-[var(--color-mute)]" />
                  {other.map(h => (
                    <div key={h.hazard} className="flex items-center gap-2 text-[12.5px]">
                      <span className="text-[var(--color-ink)] min-w-0 truncate">{h.label}</span>
                      <Chip color="var(--color-slate)">{h.scale_name}</Chip>
                      <span className="flex-1" />
                      <span className="tabular-nums text-[var(--color-mute)]">{h.score.toFixed(0)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  )
}

