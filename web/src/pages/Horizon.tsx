import { type ReactNode, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Play, Pause, Camera, ArrowRight, Maximize2, Minimize2, Satellite } from 'lucide-react'
import LiveEarthHero from '../components/LiveEarthHero'
import HexMap from '../components/HexMap'
import MethodGap from '../components/MethodGap'
import { InfoButton, HEADING, messageDetails, type Details } from '../components/Details'
import { Dialog, CloseButton } from '../components/Dialog'
import { StatusChip } from '../components/StatusChip'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { hazardLabel } from '../lib/labels'
import { balance } from '../lib/money'
import AssetCard from '../components/horizon/AssetCard'
import { ActionsPanel, ListPanel, ReadinessPanel } from '../components/horizon/Panels'
import { D2R, bearingDeg, inclHeading, ramp, rgb, useGlobe, type Iss, type View } from '../components/horizon/globe'
import type { Asset, Ent, GlobeResp, Task } from '../components/horizon/types'

// Horizon — the front door. A globe of the organisation's book (or, for a supervisor, the regions its population sits
// in), the person's own tiles beside it, and a timeline over the modelled years. Every figure, name and explanation is
// the server's (GET /v1/me/globe, /v1/me/tasks, /v1/me/entities); the page draws, it does not compute.

function Tile({ label, value, sub, tint, onClick, children }: { label: string; value: ReactNode; sub?: ReactNode; tint?: string; onClick: () => void; children?: ReactNode }) {
  return (
    <button onClick={onClick} style={{ ['--tint' as string]: tint || 'var(--color-sky)' }}
      className="group relative w-full text-left rounded-2xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-4 py-3.5 transition hover:border-[color:var(--tint)]">
      {tint && <span aria-hidden className="absolute top-4 right-4 w-2 h-2 rounded-full" style={{ background: tint }} />}
      <div className="text-[12px] text-[var(--color-faint)]">{label}</div>
      <div className="text-[24px] leading-tight mt-0.5 tabular-nums truncate" style={{ color: tint || '#F4EFE6' }}>{value}</div>
      {sub && <div className="text-[12.5px] text-[var(--color-mute)] mt-1 truncate">{sub}</div>}
      {children}
    </button>
  )
}

const about = (supervisor: boolean): Details => ({
  title: 'Horizon',
  sections: [
    { heading: HEADING.shows, body: supervisor
      ? 'The regions where the entities you supervise hold exposures, each coloured by the highest physical-risk score in it, with the figures that need you beside the globe.'
      : 'Every located asset your organisation holds, at its real coordinates, coloured by its highest physical-risk score — with what needs you, what is at risk and how ready your filings are beside the globe.' },
    { heading: HEADING.read, body: 'Play, or pick a year, to see the scores at each modelled year under the climate scenario you choose. A flaring dot is at or above your at-risk level. Click a dot for its scores and facts, a place name to frame it, a tile for its detail.' },
    { heading: HEADING.sources, body: 'Scores: the same physical-risk scores Portfolio shows, from Earth-observation and climate-model data. Locations and values: your own book. The moving satellite is the International Space Station at its live position.' },
    { heading: HEADING.limits, body: 'Figures are shown for the modelled years only; between two of them the colours just blend. A location with no score is grey.' },
  ],
})

const ISS_ABOUT: Details = {
  title: 'Earth from the International Space Station',
  sections: [
    { heading: HEADING.shows, body: 'A live camera on the International Space Station, with the station\'s current position.' },
    { heading: HEADING.sources, body: 'Video: the station\'s live stream. Position: public station telemetry, refreshed every few seconds.' },
    { heading: HEADING.limits, body: 'Your risk scores do not come from this camera. They come from Earth-observation satellites and climate models (Copernicus Sentinel, NASA, USGS).' },
  ],
}

export default function Horizon() {
  const nav = useNavigate()
  const { profile } = useAuth()
  const [panel, setPanel] = useState<'actions' | 'atrisk' | 'readiness' | 'regions' | null>(null)
  const [issOpen, setIssOpen] = useState(false)
  const [hexOpen, setHexOpen] = useState(false)
  const [entOpen, setEntOpen] = useState(false)
  const [entityId, setEntityId] = useState<string | null>(null)       // null = the whole organisation
  const [scenario, setScenario] = useState<string | null>(null)       // null = the server's default
  const [sel, setSel] = useState<Asset | null>(null)
  const [hover, setHover] = useState<{ a: Asset; x: number; y: number } | null>(null)
  const [belt, setBelt] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [stop, setStop] = useState(0)                                  // the modelled year in view (index into stops)
  const [selW, setSelW] = useState(440)
  const [selMax, setSelMax] = useState(false)
  const cvRef = useRef<HTMLCanvasElement>(null)
  const railRef = useRef<HTMLDivElement>(null)
  const issRef = useRef<Iss | null>(null)
  const issScreenRef = useRef({ x: -1, y: -1, vis: false })
  const S = useRef<View>({ pos: 0, target: 0, lon0: -8 * D2R, lat0: 20 * D2R, tLon: -8 * D2R, tLat: 20 * D2R, drag: false, moved: false, px: 0, py: 0, play: false, stop: 0, focus: null, belt: null, snap: false })

  const q = useQuery({ queryKey: ['globe', entityId, scenario], queryFn: () => api.get<GlobeResp>('/v1/me/globe?' + new URLSearchParams({ ...(scenario ? { scenario } : {}), ...(entityId ? { entity_id: entityId } : {}) })) })
  const eq = useQuery({ queryKey: ['entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/me/entities') })
  const tq = useQuery({ queryKey: ['my-tasks'], queryFn: () => api.get<{ tasks: Task[] }>('/v1/me/tasks') })
  const g = q.data
  const assets = g?.assets ?? []
  const stops = g?.stops ?? []
  const tasks = tq.data?.tasks ?? []
  const entities = eq.data?.entities ?? []
  const supervisor = g?.audience === 'supervisor'
  const orgName = profile?.org?.name ?? ''
  const risk = g?.at_risk
  const atStop = risk?.by_stop?.[stop] ?? null
  const overdue = tasks.filter(t => t.bucket === 'overdue').length
  const opsHref = supervisor ? '/supervised' : g?.sector === 'manufacturer' ? '/home' : '/portfolio'

  // places on the globe — the book grouped by where it is
  const beltsRef = useRef<Record<string, Asset[]>>({})
  useEffect(() => {
    const b: Record<string, Asset[]> = {}
    for (const a of assets) if (a.region) (b[a.region] = b[a.region] || []).push(a)
    beltsRef.current = b
  }, [assets])
  const centre = (xs: Asset[]) => [xs.reduce((s, a) => s + a.lat, 0) / xs.length, xs.reduce((s, a) => s + a.lon, 0) / xs.length]
  const lookAt = (la: number, lo: number) => { S.current.tLon = lo * D2R; S.current.tLat = Math.max(-1.1, Math.min(1.1, la * D2R)) }

  // open the globe already looking at the book (its centroid)
  const centred = useRef(false)
  useEffect(() => {
    if (centred.current || assets.length === 0) return
    centred.current = true
    const [la, lo] = centre(assets); lookAt(la, lo); S.current.lon0 = S.current.tLon; S.current.lat0 = S.current.tLat
  }, [assets])

  const pause = () => { S.current.play = false; setPlaying(false) }
  const pick = (a: Asset) => { S.current.focus = a; pause(); setPanel(null); setSel(a) }
  const openBelt = (r: string) => { const [la, lo] = centre(beltsRef.current[r] || []); S.current.belt = r; lookAt(la, lo); pause(); setBelt(r) }
  const closeBelt = () => { S.current.belt = null; setBelt(null) }
  const closeSel = () => { S.current.focus = null; if (S.current.belt) { const [la, lo] = centre(beltsRef.current[S.current.belt] || []); lookAt(la, lo) } setSel(null) }
  const goTo = (i: number) => { S.current.target = i; if (i > S.current.pos) { S.current.play = true; setPlaying(true) } else { S.current.pos = i; pause() } }
  const togglePlay = () => {
    if (playing) { pause(); return }
    if (S.current.pos >= stops.length - 1) S.current.pos = 0
    S.current.target = stops.length - 1; S.current.play = true; setPlaying(true)
  }
  const caption = useRef(() => ({ top: '', big: '', line: '', tag: '' }))
  caption.current = () => ({
    top: `TELLUMEN · HORIZON · ${orgName}`, big: stops[S.current.stop]?.label ?? '',
    line: [g?.scenario.name, risk?.by_stop ? `${risk.by_stop[S.current.stop].n} of ${g?.n_assets} ${g?.noun} at risk` : null].filter(Boolean).join(' · '),
    tag: "See what's coming.",
  })

  useGlobe({
    cvRef, railRef, S, assets, belts: beltsRef, iss: issRef, issScreen: issScreenRef,
    onStop: setStop, onPlayEnd: () => setPlaying(false), onHover: setHover, onPick: pick, onBelt: openBelt,
    onIss: () => setIssOpen(true), caption: () => caption.current(),
  })

  // Escape closes the topmost layer, one press at a time, in the order they stack
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (issOpen) setIssOpen(false)
      else if (hexOpen) setHexOpen(false)
      else if (entOpen) setEntOpen(false)
      else if (panel) setPanel(null)
      else if (sel) closeSel()
      else if (belt) closeBelt()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [issOpen, hexOpen, entOpen, panel, sel, belt])   // eslint-disable-line react-hooks/exhaustive-deps

  // the ISS's real sub-satellite point (public telemetry); heading from two samples, estimated until then. On any
  // failure the overlay holds or hides — it never blocks the globe. (Production needs the host in the CSP connect-src.)
  useEffect(() => {
    let prev: { lat: number; lon: number } | null = null, alive = true
    const pull = async () => {
      try {
        const res = await fetch('https://api.wheretheiss.at/v1/satellites/25544')
        if (!res.ok) return
        const d = await res.json(), lat = +d.latitude, lon = +d.longitude
        if (!isFinite(lat) || !isFinite(lon)) return
        const hdg = prev ? bearingDeg(prev.lat, prev.lon, lat, lon) : inclHeading(lat)
        prev = { lat, lon }
        if (alive) issRef.current = { lat, lon, hdg, t0: performance.now() / 1000 }
      } catch { /* keep the last known point */ }
    }
    pull(); const iv = setInterval(pull, 5000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  const startResize = (e: React.PointerEvent) => {
    e.preventDefault(); setSelMax(false)
    const move = (ev: PointerEvent) => setSelW(Math.max(320, Math.min(window.innerWidth, window.innerWidth - ev.clientX)))
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
  }
  const beltAssets = belt ? (beltsRef.current[belt] || []) : []
  const atRiskAssets = assets.filter(a => a.at_risk[stop])
  const round = 'mono text-[11.5px] text-[var(--color-mute)] border border-[var(--color-line-2)] rounded-full px-3.5 py-1.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]'

  return (
    <div data-theme="dark" className="absolute inset-0 bg-[#04060b] overflow-hidden select-none [container-type:inline-size]">
      <canvas ref={cvRef} className="absolute inset-0 w-full h-full cursor-grab" />
      {hover && !sel && !panel && (() => { const s = hover.a.score[stop], c = ramp(s); return (
        <div className="pointer-events-none absolute z-40 rounded-lg border border-[var(--color-line-2)] bg-[#0b121ef2] backdrop-blur px-3 py-2 shadow-[0_8px_30px_-8px_rgba(0,0,0,0.7)]"
          style={{ left: hover.x + 16, top: hover.y + 16, maxWidth: 230, transform: hover.x > 620 ? 'translateX(-100%) translateX(-32px)' : undefined }}>
          <div className="text-[13px] text-[#F4EFE6] leading-tight truncate">{hover.a.name}</div>
          <div className="text-[11px] text-[var(--color-faint)] mt-0.5 truncate">{hover.a.region}</div>
          <div className="text-[12px] mt-1 flex items-center gap-1.5 tabular-nums" style={{ color: rgb(c) }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: rgb(c) }} />{s == null ? '—' : `${Math.round(s)} / 100`}{hover.a.hazard[stop] ? ` · ${hazardLabel(hover.a.hazard[stop])}` : ''}
          </div>
          {hover.a.at_risk[stop] && <div className="mt-1.5"><StatusChip tone="bad" label="At risk" /></div>}
        </div>) })()}

      {/* top chrome: the page's name and its explanation */}
      <div className="absolute top-6 left-8 flex items-center gap-2 transition-opacity z-10" style={{ opacity: belt || sel ? 0.1 : 1 }}>
        <span className="mono text-[10px] tracking-[0.26em] text-[var(--color-faint)] uppercase">Horizon · {orgName}</span>
        <InfoButton compact details={about(supervisor)} />
      </div>
      {belt && !sel && (
        <div className="absolute top-5 left-8 flex items-center gap-4 z-10">
          <button onClick={closeBelt} className={round}>← all places</button>
          <div>
            <div className="display text-[26px] text-[#F4EFE6] leading-none">{belt}</div>
            <div className="flex items-center gap-2 mt-1.5 text-[12px] text-[var(--color-mute)]">
              {beltAssets.length} {g?.noun}
              {risk?.by_stop && <StatusChip tone="bad" label={`${beltAssets.filter(a => a.at_risk[stop]).length} at risk · ${stops[stop]?.label}`} />}
            </div>
          </div>
        </div>
      )}
      <div className="absolute top-6 right-8 pointer-events-none hidden min-[1120px]:block display italic text-[clamp(15px,1.8vw,20px)] text-[#F4EFE6]">See what's coming.</div>

      {/* the rail: who is looking, then their tiles — each opens its detail */}
      {!sel && !belt && !panel && (
        <div ref={railRef} className="fadeup absolute left-8 top-[11%] w-[clamp(210px,24cqw,280px)] max-h-[calc(100vh-150px)] overflow-y-auto flex flex-col gap-2.5 pr-1 max-[800px]:left-0 max-[800px]:right-0 max-[800px]:top-[44px] max-[800px]:w-auto max-[800px]:max-h-none max-[800px]:flex-row max-[800px]:items-start max-[800px]:overflow-x-auto max-[800px]:overflow-y-visible max-[800px]:px-3 max-[800px]:pb-2 max-[800px]:snap-x max-[800px]:*:!w-[74%] max-[800px]:*:shrink-0 [scrollbar-width:none] max-[800px]:*:snap-start">
          {!supervisor && entities.length > 0 && (
            <div className="rounded-xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur">
              <button onClick={() => setEntOpen(o => !o)} aria-expanded={entOpen} className="w-full text-left px-3.5 py-2.5 rounded-xl hover:bg-[#0e1728]">
                <div className="flex items-center justify-between gap-2 text-[12px] text-[var(--color-faint)]"><span>Working on</span><span>{entOpen ? '▴' : '▾'}</span></div>
                <div className="text-[13.5px] text-[#F4EFE6] truncate mt-0.5">{entityId ? entities.find(e => e.entity_id === entityId)?.name : orgName}</div>
              </button>
              {entOpen && (
                <div className="border-t border-[var(--color-line)] px-2 py-2 flex flex-col gap-0.5">
                  {[{ entity_id: null as string | null, name: orgName, kind_name: '', n_assets: null as number | null }, ...entities].map(e => {
                    const on = e.entity_id === entityId
                    return (
                      <button key={e.entity_id ?? 'all'} onClick={() => { setEntityId(e.entity_id); setEntOpen(false) }}
                        className={`text-left rounded-lg px-2.5 py-2 flex items-center gap-2.5 ${on ? 'bg-[#0e1728]' : 'hover:bg-[#0e1728]'}`}>
                        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: on ? 'var(--color-sky)' : 'transparent', border: on ? 'none' : '1px solid #3a4a60' }} />
                        <span className="flex-1 min-w-0">
                          <span className={`block text-[14px] truncate ${on ? 'text-[var(--color-sky)]' : 'text-[var(--color-ink)]'}`}>{e.name}</span>
                          {e.kind_name && <span className="text-[11.5px] text-[var(--color-faint)]">{e.kind_name} · {e.n_assets} {g?.noun}</span>}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {g && (
            <Tile label="Your actions" value={tasks.length || 'All clear'} tint={overdue ? 'var(--color-bad)' : undefined} onClick={() => setPanel('actions')}
              sub={tasks.length ? <span className="inline-flex items-center gap-1.5">{overdue > 0 && <StatusChip tone="bad" label={`${overdue} overdue`} />}<span>{g.my_scope.roles.map(r => r.name).join(' · ')}</span></span> : g.my_scope.roles.map(r => r.name).join(' · ')} />
          )}

          {g && !supervisor && (<>
            <Tile label={atStop ? `At risk · ${stops[stop]?.label ?? ''}` : 'Your book'} tint={atStop ? '#E9744A' : undefined} onClick={() => setPanel('atrisk')}
              value={atStop ? `${atStop.n} / ${g.n_assets}` : <>{g.n_assets}<span className="text-[13px] ml-1.5 text-[var(--color-mute)]">{g.noun}</span></>}
              sub={atStop ? `${balance(atStop.value_eur)} of ${balance(g.book_value_eur)}` : balance(g.book_value_eur)}>
              {risk?.by_stop && (
                <div className="flex items-end gap-1.5 h-7 mt-2.5" aria-hidden>
                  {risk.by_stop.map((b, i) => <span key={i} className="flex-1 rounded-sm" style={{ height: `${Math.max(8, (b.n / Math.max(1, g.n_assets)) * 100)}%`, background: i === stop ? '#E9744A' : '#E9744A55' }} />)}
                </div>
              )}
            </Tile>
            {risk?.gap && <MethodGap gap={risk.gap} what="At risk" />}
            <Tile label="Filing readiness" value={`${g.readiness.passed} / ${g.readiness.total}`} onClick={() => setPanel('readiness')}
              tint={g.readiness.passed === g.readiness.total ? 'var(--color-good)' : 'var(--color-warn)'}>
              <div className="flex gap-1 mt-2.5" aria-hidden>{g.readiness.checks.map(c => <span key={c.key} className="h-1.5 flex-1 rounded-full" style={{ background: c.ok ? 'var(--color-good)' : 'var(--color-warn)' }} />)}</div>
            </Tile>
          </>)}

          {g && supervisor && g.supervisor && (<>
            <Tile label="Regions" value={g.n_assets} sub={balance(g.book_value_eur)} onClick={() => setPanel('regions')} />
            <Tile label="Supervised entities" value={g.supervisor.entities} onClick={() => nav('/supervised')} />
            <Tile label="Filings outstanding" value={`${g.supervisor.filings_outstanding} / ${g.supervisor.filings_expected}`} onClick={() => nav('/supervised')}
              tint={g.supervisor.filings_outstanding ? 'var(--color-warn)' : 'var(--color-good)'}>
              <div className="h-1.5 rounded-full bg-[var(--color-good)] mt-2.5 overflow-hidden" aria-hidden>
                <div className="h-full bg-[var(--color-warn)]" style={{ width: `${(g.supervisor.filings_outstanding / Math.max(1, g.supervisor.filings_expected)) * 100}%` }} />
              </div>
            </Tile>
            <Tile label="Open requests" value={g.supervisor.open_requests} onClick={() => nav('/supervisor/requests')} />
          </>)}

          {!g && (
            <div className="rounded-xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-4 py-3 text-[12.5px] text-[var(--color-mute)]">
              {q.isError ? 'Your book could not be loaded. Reload the page, or sign in again.' : 'Loading your book…'}
            </div>
          )}
          {g && g.n_assets === 0 && (
            <button onClick={() => nav(supervisor ? '/supervised' : g.sector === 'manufacturer' ? '/operations' : '/data')}
              className="rounded-xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-4 py-3 text-left text-[13px] text-[var(--color-mute)] hover:border-[var(--color-sky)]">
              {supervisor ? 'No exposures in your view yet' : 'No located assets yet — add them'} <ArrowRight size={12} className="inline" />
            </button>
          )}
        </div>
      )}

      {/* a tile's detail */}
      {panel && g && (
        <div className="absolute top-0 right-0 bottom-0 w-[min(420px,46vw)] z-20 p-8 overflow-y-auto max-[800px]:w-full max-[800px]:p-5 max-[800px]:!bg-[#070b13]"
          style={{ background: 'linear-gradient(270deg,#070b13 60%,#070b13cc 90%,transparent)' }}>
          <div className="flex items-center justify-between gap-3">
            <button onClick={() => setPanel(null)} className={round}>← back</button>
            {panel === 'atrisk' && <InfoButton compact details={messageDetails(g.at_risk.message)} />}
            {panel === 'regions' && <InfoButton compact details={messageDetails(g.at_risk.message)} />}
          </div>
          {panel === 'actions' && <ActionsPanel tasks={tasks} roles={g.my_scope.roles} raisedPending={g.my_scope.raised_pending} />}
          {panel === 'readiness' && <ReadinessPanel {...g.readiness} />}
          {panel === 'atrisk' && <ListPanel title={risk?.by_stop ? 'At risk' : g.noun} assets={risk?.by_stop ? atRiskAssets : assets} stop={stop} stops={stops} onPick={pick} />}
          {panel === 'regions' && <ListPanel title="Regions" assets={assets} stop={stop} stops={stops} onPick={pick} />}
        </div>
      )}

      {/* the picked asset */}
      {sel && g && (
        <div className="absolute top-0 right-0 bottom-0 z-10 p-8 overflow-y-auto max-[800px]:!w-full max-[800px]:p-5 max-[800px]:!bg-[#070b13]"
          style={{ width: selMax ? '100vw' : selW, maxWidth: '100vw', background: selMax ? '#070b13' : 'linear-gradient(270deg,#070b13 80%,#070b13ee 93%,transparent)' }}>
          <div onPointerDown={startResize} title="Drag to resize" className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize group flex items-center justify-center">
            <div className="w-0.5 h-10 rounded bg-[var(--color-line-2)] group-hover:bg-[var(--color-sky)]" />
          </div>
          <div className="flex items-center justify-between gap-3">
            <button onClick={closeSel} className={round}>← back</button>
            <button onClick={() => setSelMax(m => !m)} title={selMax ? 'Restore' : 'Expand'} aria-label={selMax ? 'Restore' : 'Expand'}
              className="grid place-items-center w-8 h-8 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
              {selMax ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
          </div>
          <AssetCard a={sel} stops={stops} stop={stop} level={risk?.level ?? null} onGrid={() => setHexOpen(true)} />
        </div>
      )}

      {/* the colour scale */}
      {g && !sel && (
        <div className="absolute left-8 bottom-[92px] flex items-center gap-3 text-[11.5px] text-[var(--color-faint)] max-[800px]:left-3 max-[800px]:bottom-[188px] max-[800px]:flex-wrap max-[800px]:max-w-[60%]">
          <span>Score</span>
          <span className="w-28 h-1.5 rounded-full" style={{ background: `linear-gradient(90deg, ${rgb(ramp(0))}, ${rgb(ramp(50))}, ${rgb(ramp(100))})` }} />
          {risk?.by_stop && <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: rgb(ramp(80)), boxShadow: `0 0 8px ${rgb(ramp(80))}` }} />at or above your at-risk level</span>}
        </div>
      )}

      <button onClick={() => (S.current.snap = true)} className="absolute right-8 bottom-[140px] inline-flex items-center gap-2 text-[12px] text-[var(--color-mute)] bg-[#0b121e] border border-[#223046] rounded-full px-4 py-2.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] max-[800px]:hidden"><Camera size={13} /> Save snapshot</button>
      <button onClick={() => nav(opsHref)} className="absolute right-8 bottom-[88px] inline-flex items-center gap-2 text-[12.5px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] max-[800px]:right-3 max-[800px]:bottom-[132px] max-[800px]:py-2.5">Enter operations <ArrowRight size={14} /></button>

      {/* the timeline: the modelled years, and the scenario the later ones are read on */}
      {g && (
        <div className="absolute left-0 right-0 bottom-0 px-8 pb-6 pt-5 max-[800px]:px-3" style={{ background: 'linear-gradient(0deg,#04060bE6 30%,transparent)' }}>
          <div className="flex items-center gap-4 max-w-[1200px] mx-auto flex-wrap">
            <button onClick={togglePlay} aria-label={playing ? 'Pause' : 'Play'} title={playing ? 'Pause' : 'Play'}
              className="w-11 h-11 shrink-0 rounded-full border border-[#2a3a50] bg-[#0e1626] grid place-items-center text-[#F4EFE6] hover:border-[var(--color-sky)]">
              {playing ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <div className="flex-1 min-w-[220px] flex items-center">
              {stops.map((st, i) => (
                <div key={st.key} className="flex-1 flex items-center last:flex-none">
                  <button onClick={() => goTo(i)} aria-pressed={i === stop}
                    className={`shrink-0 text-[12.5px] px-3 py-1.5 rounded-full border transition ${i === stop ? 'border-[var(--color-sky)] text-[var(--color-sky)] bg-[#0e1626]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{st.label}</button>
                  {i < stops.length - 1 && <span className={`flex-1 h-px mx-1 ${i < stop ? 'bg-[var(--color-sky)]' : 'bg-[var(--color-line-2)]'}`} />}
                </div>
              ))}
            </div>
            <label className="inline-flex items-center gap-2 text-[12px] text-[var(--color-faint)]">
              <span className="max-[560px]:hidden">Scenario</span>
              <select value={g.scenario.key} onChange={e => setScenario(e.target.value)} aria-label="Climate scenario"
                className="bg-[#0e1626] border border-[var(--color-line-2)] rounded-full px-3 py-1.5 text-[12.5px] text-[#F4EFE6] outline-none focus:border-[var(--color-sky)]">
                {g.scenarios.map(s => <option key={s.key} value={s.key}>{s.name}</option>)}
              </select>
            </label>
          </div>
        </div>
      )}

      {/* click the orbiting satellite: the live view from the International Space Station */}
      {issOpen && (
        <Dialog bare title="Earth from the International Space Station" onClose={() => setIssOpen(false)} overlayClassName="z-40 p-6" backdropClassName="bg-[#04060bee] backdrop-blur-sm" className="w-[min(1120px,94vw)]">
          <div className="flex items-center justify-between mb-3">
            <div className="inline-flex items-center gap-2 text-[12.5px] text-white/75">
              <Satellite size={13} className="text-[#9CC6FF]" /> Live from the International Space Station
              {issRef.current && <span className="text-white/45 tabular-nums">· {Math.abs(issRef.current.lat).toFixed(1)}°{issRef.current.lat >= 0 ? 'N' : 'S'}, {Math.abs(issRef.current.lon).toFixed(1)}°{issRef.current.lon >= 0 ? 'E' : 'W'}</span>}
              <InfoButton compact details={ISS_ABOUT} />
            </div>
            <CloseButton onClick={() => setIssOpen(false)} size={15} look="grid place-items-center w-8 h-8 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]" />
          </div>
          <LiveEarthHero height="66vh" showBadge={false} />
        </Dialog>
      )}

      {hexOpen && sel && (
        <Dialog bare title={`Surrounding grid · ${sel.name}`} onClose={() => setHexOpen(false)} overlayClassName="z-30 p-6" backdropClassName="bg-[#04060bcc] backdrop-blur-sm"
          className="w-[min(760px,92vw)] h-[min(560px,82vh)] rounded-2xl overflow-hidden border border-[var(--color-line-2)] bg-[#070b13]">
          <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-5 py-3 bg-[#070b13cc] backdrop-blur border-b border-[var(--color-line)]">
            <div>
              <div className="text-[12px] text-[var(--color-faint)]">Surrounding grid · {stops[stop]?.label}</div>
              <div className="display text-[18px] text-[#F4EFE6] leading-tight">{sel.name}</div>
            </div>
            <CloseButton onClick={() => setHexOpen(false)} size={15} look="grid place-items-center w-8 h-8 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]" />
          </div>
          <div className="absolute inset-0 pt-[58px]">
            <HexMap lat={sel.lat} lon={sel.lon} selectedId={sel.id} scenario={stops[stop]?.scenario} horizon={stops[stop]?.key}
              assets={assets.map(a => ({ ...a, traj: Object.fromEntries(stops.flatMap((st, i) => a.score[i] == null ? [] : [[st.key, a.score[i] as number]])) }))} />
          </div>
        </Dialog>
      )}
    </div>
  )
}
