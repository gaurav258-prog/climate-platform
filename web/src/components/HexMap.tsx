import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, Polygon, CircleMarker, Tooltip, useMapEvents } from 'react-leaflet'
import { latLngToCell, cellToBoundary } from 'h3-js'
import 'leaflet/dist/leaflet.css'
import { api } from '../lib/api'

// Interactive H3 drill-down beneath the overview globe: a real pan/zoom basemap with this org's assets
// pinned to their H3 res-8 hexagons, coloured by their real worst-hazard score. Zoom out to roam the
// whole book, zoom in to the ~0.7 km cell. Around the SELECTED site we also render the k-ring of
// neighbouring cells, each scored ON DEMAND by the golden-source baselines (seismic/heat/storm) — so you
// see the risk TEXTURE the site sits in, not just its own cell. A cell is coloured only where a real
// score exists — nothing invented; cells still filling in show a faint outline. Dark Carto raster tiles.
interface A { id: string; name: string; lat: number; lon: number; region?: string; traj: Record<string, number> }
interface HexCell { cell: string; is_center: boolean; boundary: [number, number][]; score: number | null }
interface HexResp { center: string; n_cells: number; n_scored: number; computing: boolean; center_score: number | null; cells: HexCell[] }

function col(l: number): [number, number, number] {
  return l < 28 ? [207, 232, 255] : l < 50 ? [232, 178, 76] : l < 75 ? [233, 116, 74] : [210, 59, 59]
}
function stateName(l: number) { return l < 28 ? 'safe' : l < 50 ? 'elevated' : l < 75 ? 'high' : 'severe' }

function ZoomWatch({ onZoom }: { onZoom: (z: number) => void }) {
  const m = useMapEvents({ zoomend: () => onZoom(m.getZoom()) })
  return null
}

export default function HexMap({ lat, lon, horizon = '2050', scenario = 'disorderly_2c', assets, selectedId }:
  { lat: number; lon: number; horizon?: string; scenario?: string; assets: A[]; selectedId?: string }) {
  const [zoom, setZoom] = useState(12)
  const asHex = zoom >= 11   // res-8 cells are ~0.7 km — show polygons zoomed-in, dots when zoomed-out

  // The scored k-ring texture around the selected site. Poll while the backend is still warming cells.
  const ring = useQuery({
    queryKey: ['hexes', lat, lon, scenario, horizon],
    queryFn: () => api.get<HexResp>(`/v1/me/hexes?lat=${lat}&lon=${lon}&k=2&scenario=${scenario}&horizon=${horizon}&score=true`),
    refetchInterval: (q) => (q.state.data?.computing ? 4000 : false),
  })
  const ringCells = ring.data?.cells ?? []

  const cells = useMemo(() => assets.filter(a => a.lat != null && a.lon != null).map(a => {
    const cell = latLngToCell(a.lat, a.lon, 8)
    const score = a.traj?.[horizon] ?? a.traj?.current ?? 0
    return { id: a.id, name: a.name, boundary: cellToBoundary(cell) as [number, number][], score, lat: a.lat, lon: a.lon, sel: a.id === selectedId }
  }), [assets, horizon, selectedId])
  const selCell = cells.find(c => c.sel)

  return (
    <div className="relative w-full h-full">
      <MapContainer center={[lat, lon]} zoom={12} minZoom={2} maxZoom={16} scrollWheelZoom worldCopyJump
        style={{ width: '100%', height: '100%', background: '#0b1524' }}>
        <TileLayer attribution="&copy; OpenStreetMap &copy; CARTO"
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" subdomains="abcd" />
        <ZoomWatch onZoom={setZoom} />

        {/* Risk texture: the scored neighbour ring, drawn UNDER the asset hexes. Only shown zoomed-in
            (the cells are ~0.7 km). Scored cells fill faintly by severity; unscored show a bare outline. */}
        {asHex && ringCells.map(c => {
          if (c.is_center) return null   // the site's own cell is drawn as an asset hex below
          if (c.score == null) return (
            <Polygon key={c.cell} positions={c.boundary}
              pathOptions={{ color: '#33415580', weight: 0.8, fill: false, dashArray: '3 4' }} />
          )
          const [r, g, b] = col(c.score)
          return (
            <Polygon key={c.cell} positions={c.boundary}
              pathOptions={{ color: `rgb(${r},${g},${b})`, weight: 0.8, fillColor: `rgb(${r},${g},${b})`, fillOpacity: 0.16 }}>
              <Tooltip sticky>neighbour cell · {Math.round(c.score)}/100 · {stateName(c.score)}</Tooltip>
            </Polygon>
          )
        })}

        {/* The book: every asset on its own cell, coloured by its real worst-hazard score. */}
        {cells.map(c => {
          const [r, g, b] = col(c.score)
          const stroke = `rgb(${r},${g},${b})`
          return asHex ? (
            <Polygon key={c.id} positions={c.boundary}
              pathOptions={{ color: stroke, weight: c.sel ? 3 : 1.4, fillColor: stroke, fillOpacity: c.sel ? 0.5 : 0.3 }}>
              <Tooltip sticky>{c.name} · {Math.round(c.score)}/100</Tooltip>
            </Polygon>
          ) : (
            <CircleMarker key={c.id} center={[c.lat, c.lon]} radius={c.sel ? 7 : 4}
              pathOptions={{ color: stroke, weight: c.sel ? 2 : 1, fillColor: stroke, fillOpacity: 0.85 }}>
              <Tooltip>{c.name} · {Math.round(c.score)}/100</Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>

      {/* still-scoring chip */}
      {ring.data?.computing && (
        <div className="absolute right-3 top-3 z-[500] mono text-[10.5px] text-[#cdd7e6] bg-[#070b13cc] backdrop-blur border border-[#26344f] rounded-lg px-3 py-1.5 flex items-center gap-2 pointer-events-none">
          <span className="w-1.5 h-1.5 rounded-full bg-[#6bb1ff] animate-pulse" />
          scoring the surrounding cells… {ring.data.n_scored}/{ring.data.n_cells}
        </div>
      )}

      <div className="absolute left-3 bottom-3 z-[500] mono text-[10.5px] text-[#cdd7e6] bg-[#070b13cc] backdrop-blur border border-[#26344f] rounded-lg px-3 py-2 leading-relaxed pointer-events-none">
        H3 res-8 grid · ~0.7 km cells · {assets.length} asset{assets.length !== 1 ? 's' : ''} on the book<br />
        {selCell
          ? <>selected: <b className="text-[#F4EFE6]">{Math.round(selCell.score)}/100</b> · {stateName(selCell.score)} · {horizon}
              {asHex
                ? <><br /><span className="text-[#8ea3c0]">surrounding cells: heat · seismic · storm, scored live from the baselines</span></>
                : ' · zoom in for local texture'}</>
          : 'scroll to zoom · drag to pan'}
      </div>
    </div>
  )
}
