import { useEffect, useRef, useState } from 'react'

// A small located-point map built from STATIC raster tiles (<img>), not interactive maplibre.
// Rationale: maplibre-6 leaves its WebGL raster blank until the first user gesture; a plain <img>
// tile grid always paints on load. Deterministic, reliable, no paint quirk. Non-interactive by design.
const TILE = (z: number, x: number, y: number) => `https://a.basemaps.cartocdn.com/rastertiles/voyager/${z}/${x}/${y}.png`

export default function MiniMap({ lat, lon, color = '#38bdf8', zoom = 6 }: { lat: number; lon: number; color?: string; zoom?: number }) {
  const el = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    if (!el.current) return
    const measure = () => { if (el.current) setSize({ w: el.current.clientWidth, h: el.current.clientHeight }) }
    measure()
    const ro = new ResizeObserver(measure); ro.observe(el.current)
    return () => ro.disconnect()
  }, [])

  const { w, h } = size
  const z = Math.max(1, Math.min(12, Math.round(zoom)))
  const n = 2 ** z
  const cx = (lon + 180) / 360 * n                                   // fractional tile X of the point
  const latRad = lat * Math.PI / 180
  const cy = (1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n  // fractional tile Y

  const tiles: { key: string; src: string; left: number; top: number }[] = []
  if (w > 0 && h > 0) {
    const cols = Math.ceil(w / 2 / 256) + 1
    const rows = Math.ceil(h / 2 / 256) + 1
    const fx = Math.floor(cx), fy = Math.floor(cy)
    for (let tx = fx - cols; tx <= fx + cols; tx++) {
      for (let ty = fy - rows; ty <= fy + rows; ty++) {
        if (ty < 0 || ty >= n) continue
        const wx = ((tx % n) + n) % n                                // wrap longitude
        tiles.push({ key: `${tx}_${ty}`, src: TILE(z, wx, ty), left: w / 2 - (cx - tx) * 256, top: h / 2 - (cy - ty) * 256 })
      }
    }
  }

  return (
    <div ref={el} className="relative h-72 w-full rounded-xl overflow-hidden" style={{ background: '#a9d3ef' }}>
      {tiles.map(t => (
        <img key={t.key} src={t.src} width={256} height={256} draggable={false}
          className="absolute select-none pointer-events-none max-w-none" style={{ left: t.left, top: t.top }} alt="" />
      ))}
      {w > 0 && (
        <div className="absolute" style={{ left: w / 2 - 8, top: h / 2 - 8, width: 16, height: 16, borderRadius: '50%', background: color, border: '2px solid #fff', boxShadow: '0 0 0 2px rgba(15,23,42,.2)' }} />
      )}
    </div>
  )
}
