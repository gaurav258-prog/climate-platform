import { useMemo, useState } from 'react'
import { MapContainer, TileLayer, Polygon, CircleMarker, Tooltip, useMapEvents } from 'react-leaflet'
import { latLngToCell, cellToBoundary } from 'h3-js'
import 'leaflet/dist/leaflet.css'

// Interactive H3 drill-down beneath the overview globe: a real pan/zoom basemap with this org's assets
// pinned to their H3 res-8 hexagons, coloured by their real worst-hazard score. Zoom out to roam the
// whole book, zoom in to the ~0.7 km cell. A cell is coloured only where a real score exists — nothing
// invented. Dark Carto raster tiles (plain <img>, no WebGL) so it always paints.
interface A { id: string; name: string; lat: number; lon: number; region?: string; traj: Record<string, number> }

function col(l: number): [number, number, number] {
  return l < 28 ? [207, 232, 255] : l < 50 ? [232, 178, 76] : l < 75 ? [233, 116, 74] : [210, 59, 59]
}
function stateName(l: number) { return l < 28 ? 'safe' : l < 50 ? 'elevated' : l < 75 ? 'high' : 'severe' }

function ZoomWatch({ onZoom }: { onZoom: (z: number) => void }) {
  const m = useMapEvents({ zoomend: () => onZoom(m.getZoom()) })
  return null
}

export default function HexMap({ lat, lon, horizon = '2050', assets, selectedId }:
  { lat: number; lon: number; horizon?: string; assets: A[]; selectedId?: string }) {
  const [zoom, setZoom] = useState(12)
  const asHex = zoom >= 11   // res-8 cells are ~0.7 km — show polygons zoomed-in, dots when zoomed-out

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

      <div className="absolute left-3 bottom-3 z-[500] mono text-[10.5px] text-[#cdd7e6] bg-[#070b13cc] backdrop-blur border border-[#26344f] rounded-lg px-3 py-2 leading-relaxed pointer-events-none">
        H3 res-8 grid · ~0.7 km cells · {assets.length} asset{assets.length !== 1 ? 's' : ''} on the book<br />
        {selCell
          ? <>selected: <b className="text-[#F4EFE6]">{Math.round(selCell.score)}/100</b> · {stateName(selCell.score)} · {horizon}</>
          : 'scroll to zoom · drag to pan'}
      </div>
    </div>
  )
}
