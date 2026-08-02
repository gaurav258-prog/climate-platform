import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

// The granular drill-down beneath the overview globe: a real basemap under the site with the H3 res-8
// grid overlaid. The cell the site falls in is filled by its real worst-hazard score; the surrounding
// cells are drawn as the true H3 tessellation (geometry only — a neighbour is coloured only once it has
// been scored, never guessed). Tiles are static Carto raster (<img>) so it always paints on load.
const TILE = (z: number, x: number, y: number) => `https://a.basemaps.cartocdn.com/rastertiles/voyager/${z}/${x}/${y}.png`
const D2R = Math.PI / 180

interface Cell { cell: string; is_center: boolean; boundary: number[][]; score: number | null }
interface Hexes { center: string; resolution: number; cell_km: number; scenario: string; horizon: string; center_score: number | null; cells: Cell[] }

function col(l: number): [number, number, number] {
  return l < 28 ? [207, 232, 255] : l < 50 ? [232, 178, 76] : l < 75 ? [233, 116, 74] : [210, 59, 59]
}
function stateName(l: number) { return l < 28 ? 'safe' : l < 50 ? 'elevated' : l < 75 ? 'high' : 'severe' }

// web-mercator: lat/lon → global pixel at zoom z
function projPx(lat: number, lon: number, z: number): [number, number] {
  const n = 2 ** z * 256
  const x = (lon + 180) / 360 * n
  const s = Math.sin(lat * D2R)
  const y = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n
  return [x, y]
}

export default function HexMap({ lat, lon, scenario = 'disorderly_2c', horizon = '2050', zoom = 13 }:
  { lat: number; lon: number; scenario?: string; horizon?: string; zoom?: number }) {
  const box = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    if (!box.current) return
    const measure = () => { if (box.current) setSize({ w: box.current.clientWidth, h: box.current.clientHeight }) }
    measure(); const ro = new ResizeObserver(measure); ro.observe(box.current); return () => ro.disconnect()
  }, [])

  const q = useQuery({
    queryKey: ['hexes', lat, lon, scenario, horizon],
    queryFn: () => api.get<Hexes>(`/v1/me/hexes?lat=${lat}&lon=${lon}&scenario=${scenario}&horizon=${horizon}`),
  })
  const data = q.data

  const { w, h } = size
  const z = Math.max(1, Math.min(15, Math.round(zoom)))
  const [cpx, cpy] = projPx(lat, lon, z)                       // site's global pixel (map centre)
  const toScreen = (la: number, lo: number): [number, number] => {
    const [px, py] = projPx(la, lo, z); return [w / 2 + (px - cpx), h / 2 + (py - cpy)]
  }

  // basemap tiles covering the viewport
  const tiles: { key: string; src: string; left: number; top: number }[] = []
  if (w > 0 && h > 0) {
    const n = 2 ** z
    const ctx = cpx / 256, cty = cpy / 256, fx = Math.floor(ctx), fy = Math.floor(cty)
    const cols = Math.ceil(w / 2 / 256) + 1, rows = Math.ceil(h / 2 / 256) + 1
    for (let tx = fx - cols; tx <= fx + cols; tx++)
      for (let ty = fy - rows; ty <= fy + rows; ty++) {
        if (ty < 0 || ty >= n) continue
        const wx = ((tx % n) + n) % n
        tiles.push({ key: `${tx}_${ty}`, src: TILE(z, wx, ty), left: w / 2 - (ctx - tx) * 256, top: h / 2 - (cty - ty) * 256 })
      }
  }

  return (
    <div ref={box} className="relative w-full h-full rounded-xl overflow-hidden" style={{ background: '#0b1524' }}>
      {tiles.map(t => (
        <img key={t.key} src={t.src} width={256} height={256} draggable={false} alt=""
          className="absolute select-none pointer-events-none max-w-none" style={{ left: t.left, top: t.top, opacity: 0.9 }} />
      ))}
      {/* darken the basemap a touch so the hexes read on the dark UI */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'rgba(6,10,18,0.28)' }} />

      {w > 0 && data && (
        <svg className="absolute inset-0 pointer-events-none" width={w} height={h}>
          {data.cells.map(c => {
            const pts = c.boundary.map(([la, lo]) => toScreen(la, lo).join(',')).join(' ')
            if (c.is_center) {
              const s = data.center_score
              const [r, g, b] = s != null ? col(s) : [150, 170, 200]
              return <polygon key={c.cell} points={pts} fill={`rgba(${r},${g},${b},0.42)`} stroke={`rgb(${r},${g},${b})`} strokeWidth={2.5} strokeLinejoin="round" />
            }
            const scored = c.score != null
            const [r, g, b] = scored ? col(c.score!) : [140, 160, 190]
            return <polygon key={c.cell} points={pts}
              fill={scored ? `rgba(${r},${g},${b},0.34)` : 'rgba(150,170,200,0.04)'}
              stroke={`rgba(${r},${g},${b},${scored ? 0.85 : 0.35})`} strokeWidth={scored ? 1.6 : 1} strokeLinejoin="round" />
          })}
          {/* centre marker */}
          {(() => { const [x, y] = toScreen(lat, lon); return <circle cx={x} cy={y} r={4} fill="#fff" stroke="#0b1524" strokeWidth={1.5} /> })()}
        </svg>
      )}

      {/* caption */}
      <div className="absolute left-3 bottom-3 mono text-[10.5px] text-[#cdd7e6] bg-[#070b13cc] backdrop-blur border border-[#26344f] rounded-lg px-3 py-2 leading-relaxed">
        H3 res-{data?.resolution ?? 8} grid · ~{data?.cell_km ?? 0.7} km cells<br />
        {data?.center_score != null
          ? <>this cell: <b className="text-[#F4EFE6]">{Math.round(data.center_score)}/100</b> · {stateName(data.center_score)} · {horizon}</>
          : 'this cell: scoring…'}
      </div>
      {q.isLoading && <div className="absolute inset-0 grid place-items-center mono text-[11px] text-[var(--color-mute)]">loading grid…</div>}
    </div>
  )
}
