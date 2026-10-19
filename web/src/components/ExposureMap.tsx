import { useEffect, useMemo, useState } from 'react'
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { severityHex } from './SiteMap'
import { balance } from '../lib/money'
import { regionTooltip, type Region } from './exposureMapWords'

export type { Region }

// The supervisor's map. Regions (NUTS-3 in the EU, H3 hexagons elsewhere) are always drawn — the unit filings
// use, no site identifiable. Individual sites are layered on top ONLY for entities that granted site access.
export interface Site { id: string; name: string; kind: string; lat: number; lon: number; value_eur: number; score: number | null; hazard: string | null }

// a site's kind: the engine books name themselves ('financed asset', 'property'); an agriculture site or plot is a code
const SITE_KIND: Record<string, string> = { site: 'Operating site', plot: 'Sourcing plot' }
const siteKind = (k: string) => SITE_KIND[k] ?? k[0].toUpperCase() + k.slice(1)

const LIGHT = 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'
const DARK = 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'

function useDark() {
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark')
  useEffect(() => {
    const mo = new MutationObserver(() => setDark(document.documentElement.dataset.theme === 'dark'))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }); return () => mo.disconnect()
  }, [])
  return dark
}

function Fit({ regions, focusKey }: { regions: Region[]; focusKey?: string | null }) {
  const map = useMap()
  const key = regions.map(r => r.key).join('|') + '#' + (focusKey ?? '')
  useEffect(() => {
    const focus = focusKey ? regions.filter(r => r.key === focusKey) : []
    const target = focus.length ? focus : regions
    const pts: [number, number][] = []
    for (const r of target) {
      const g = r.geometry as { type: string; coordinates: unknown }
      const rings = g.type === 'Polygon' ? [(g.coordinates as number[][][])[0]] : (g.coordinates as number[][][][]).map(p => p[0])
      for (const ring of rings) for (const [x, y] of ring) pts.push([y, x])
    }
    if (pts.length) map.fitBounds(pts, { padding: [24, 24], maxZoom: focus.length ? 10 : 8 })
  }, [key])   // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

export default function ExposureMap({ regions, sites, height = 480, focusKey }: { regions: Region[]; sites?: Site[]; height?: number; focusKey?: string | null }) {
  const dark = useDark()
  const fc = useMemo(() => ({ type: 'FeatureCollection' as const,
    features: regions.map(r => ({ type: 'Feature' as const, geometry: r.geometry, properties: r })) }), [regions])
  return (
    <div className="relative w-full rounded-xl overflow-hidden border border-[var(--color-line)]" style={{ height }}>
      <MapContainer center={[48, 8]} zoom={4} minZoom={2} maxZoom={14} scrollWheelZoom={false} worldCopyJump
        style={{ width: '100%', height: '100%', background: dark ? '#0b1524' : '#e8eef4' }}>
        <TileLayer key={dark ? 'd' : 'l'} attribution="Tiles &copy; Esri · NUTS &copy; EuroGeographics" url={dark ? DARK : LIGHT} />
        <Fit regions={regions} focusKey={focusKey} />
        <GeoJSON key={fc.features.length + (dark ? 'd' : 'l') + (focusKey ?? '')} data={fc}
          style={(f) => { const r = f?.properties as Region; const c = severityHex(r.max_score); const hot = focusKey && r.key === focusKey
            return { color: hot ? (dark ? '#fff' : '#0f172a') : c, weight: hot ? 3 : r.kind === 'h3' ? 1 : 1.2, dashArray: r.kind === 'h3' ? '4 3' : undefined, fillColor: c, fillOpacity: r.max_score == null ? 0.15 : 0.45 } }}
          onEachFeature={(f, layer) => { layer.bindTooltip(regionTooltip(f.properties as Region), { sticky: true }) }} />
        {(sites ?? []).map(s => (
          <CircleMarker key={s.id} center={[s.lat, s.lon]} radius={5}
            pathOptions={{ color: dark ? '#fff' : '#0f172a', weight: 1, fillColor: severityHex(s.score), fillOpacity: 0.9 }}>
            <Tooltip direction="top" offset={[0, -5]} opacity={1}>
              <span style={{ fontSize: 12 }}><b>{s.name}</b> · {siteKind(s.kind)} · {balance(s.value_eur)}{s.score != null ? ` · ${Math.round(s.score)}/100` : ''}</span>
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
      <div className="absolute left-2 bottom-2 z-[500] text-[10.5px] px-2 py-1 rounded-md bg-[var(--color-panel)]/90 text-[var(--color-faint)] border border-[var(--color-line)]">
        {regions.length} areas{sites ? ` · ${sites.length} individual sites, as granted` : ' · regions only'}
      </div>
    </div>
  )
}
