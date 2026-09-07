import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// Where the book actually sits. Every located asset in the current list is a dot coloured by its headline
// severity; the open asset is ringed and the map flies to it. Fits to whatever the list shows — a hazard
// filter therefore also filters the map. Keyless Esri Canvas tiles, light or dark to match the theme.
export interface SitePoint { id: string; name: string; lat: number; lon: number; score: number | null; sub?: string; value?: string }

// default dot colour by 0-100 severity — plain hex, because leaflet writes SVG attributes (a CSS var() would not resolve)
export const severityHex = (s: number | null) => s == null ? '#8a94a6' : s >= 75 ? '#d23b3b' : s >= 50 ? '#e9744a' : s >= 28 ? '#e8b24c' : '#5fb98c'

const LIGHT = 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'
const DARK = 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'

function useDark() {
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark')
  useEffect(() => {
    const mo = new MutationObserver(() => setDark(document.documentElement.dataset.theme === 'dark'))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return dark
}

function Fit({ points, selectedId }: { points: SitePoint[]; selectedId?: string | null }) {
  const map = useMap()
  const key = points.map(p => p.id).join('|')
  useEffect(() => {
    if (!points.length) return
    if (points.length === 1) { map.setView([points[0].lat, points[0].lon], 9); return }
    map.fitBounds(points.map(p => [p.lat, p.lon] as [number, number]), { padding: [28, 28], maxZoom: 10 })
  }, [key])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const p = points.find(x => x.id === selectedId)
    if (p) map.flyTo([p.lat, p.lon], Math.max(map.getZoom(), 9), { duration: 0.6 })
  }, [selectedId])   // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

export default function SiteMap({ points, selectedId, onSelect, color, noun = 'sites' }:
  { points: SitePoint[]; selectedId?: string | null; onSelect?: (id: string) => void; color: (score: number) => string; noun?: string }) {
  const dark = useDark()
  const located = useMemo(() => points.filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon)), [points])
  const center: [number, number] = located.length ? [located[0].lat, located[0].lon] : [48, 8]
  return (
    <div className="relative w-full h-full min-h-[360px] rounded-xl overflow-hidden border border-[var(--color-line)]">
      <MapContainer center={center} zoom={4} minZoom={2} maxZoom={16} scrollWheelZoom={false} worldCopyJump
        style={{ width: '100%', height: '100%', background: dark ? '#0b1524' : '#e8eef4' }}>
        <TileLayer key={dark ? 'd' : 'l'} attribution="Tiles &copy; Esri" maxZoom={16} url={dark ? DARK : LIGHT} />
        <Fit points={located} selectedId={selectedId} />
        {located.map(p => {
          const c = color(p.score ?? 0)
          const sel = p.id === selectedId
          return (
            <CircleMarker key={p.id} center={[p.lat, p.lon]} radius={sel ? 9 : 6}
              pathOptions={{ color: sel ? (dark ? '#fff' : '#0f172a') : c, weight: sel ? 2.5 : 1,
                             fillColor: c, fillOpacity: p.score == null ? 0.35 : 0.85 }}
              eventHandlers={{ click: () => onSelect?.(p.id) }}>
              <Tooltip direction="top" offset={[0, -6]} opacity={1}>
                <span style={{ fontSize: 12 }}><b>{p.name}</b>{p.sub ? ` · ${p.sub}` : ''}{p.value ? ` · ${p.value}` : ''}
                  {p.score != null ? ` · ${Math.round(p.score)}/100` : ''}</span>
              </Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>
      <div className="absolute left-2 bottom-2 z-[500] mono text-[10px] px-2 py-1 rounded-md bg-[var(--color-panel)]/90 text-[var(--color-faint)] border border-[var(--color-line)]">
        {located.length} of {points.length} {noun} located · click a dot to open it
      </div>
    </div>
  )
}


// The STANDARD "book beside its map" layout, used by every sector's asset list (financial portfolio, agri sites,
// sourcing plots): the list on the left, the map of exactly those rows on the right (sticky, wide screens only).
// If none of the rows carries a location the map column is not rendered at all — no empty map.
export function BookWithMap({ points, selectedId, onSelect, color, height = 520, noun = 'sites', children }:
  { points: SitePoint[]; selectedId?: string | null; onSelect?: (id: string) => void; color: (score: number) => string;
    height?: number; noun?: string; children: ReactNode }) {
  const anyLocated = points.some(p => Number.isFinite(p.lat) && Number.isFinite(p.lon))
  if (!anyLocated) return <>{children}</>
  return (
    <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(320px,40%)]">
      <div className="min-w-0">{children}</div>
      <div className="hidden lg:block p-3 border-l border-[var(--color-line)]">
        <div className="sticky top-3" style={{ height }}>
          <SiteMap points={points} selectedId={selectedId} onSelect={onSelect} color={color} noun={noun} />
        </div>
      </div>
    </div>
  )
}
