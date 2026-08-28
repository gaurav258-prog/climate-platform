import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { api } from '../lib/api'
import { PLACE_LABELS } from '../lib/placeLabels'
import { Card, PageHeader } from '../components/ui'
import { hazardLabel } from '../lib/hazards'

interface Plot {
  plot_id: string; commodity: string; eudr_covered: boolean; plot_name: string; country: string | null
  lat: number; lon: number; spend_eur: number; eudr_determination: string | null
  top_hazard: string | null; hazard_score: number | null
}
interface Portfolio { plots: Plot[] }

interface HexPlot { name: string; commodity: string; country: string | null }
interface Hex { cell: string; rings: [number, number][][]; score: number | null; bucket: string | null
  driver_hazard: string | null; n_plots: number; plots?: HexPlot[]; is_plot_cell: boolean; status: string }
interface HexResponse { resolution: number; hexes: Hex[]; n_plot_cells?: number }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`
const hazardColor = (s: number | null) => s == null ? '#64748b' : s >= 60 ? '#fb7185' : s >= 40 ? '#f59e0b' : s >= 1 ? '#34d399' : '#64748b'
const bandLabel = (s: number | null) => s == null ? 'unscored' : s >= 60 ? 'High' : s >= 40 ? 'Medium' : 'Low'
const prettyHazard = hazardLabel

// H3 display resolution follows the map zoom — coarse cells zoomed out, finer as you zoom in.
// Calibrated so a cell stays roughly readable on screen (~30px) instead of shrinking as you zoom.
const resForZoom = (z: number) => Math.max(2, Math.min(7, Math.round(0.72 * z - 0.6)))

// A calm, light-blue "clear sky" map — Voyager tiles desaturated and held semi-transparent over a
// sky-blue ground, so land and sea read as soft blues. Everything on top (place names, plots, and the
// H3 hex grid) is drawn as a DOM/SVG overlay — maplibre-6 can leave its own vector layers unrendered
// until the user's first gesture, but overlays projected via map.project() paint on load, reliably.
// Keyless, LABEL-FREE light base (Esri Light Gray Canvas) — no API key, and no baked-in place names, so the
// only labels are the app's own English ones below (plain OSM bakes in local-language labels; CARTO's
// no-label base now needs a key). Attribution required.
const TILES = ['https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}']
const SKY = '#a9d3ef'        // ocean blue behind everything (shows through the sea)
const INK = '#12314f'        // deep navy for labels on the light land

function baseStyle(): maplibregl.StyleSpecification {
  return {
    version: 8,
    sources: { base: { type: 'raster', tiles: TILES, tileSize: 256, maxzoom: 16, attribution: 'Tiles © Esri' } },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': SKY } },
      // full-strength, lightly-cooled Voyager with a contrast boost — clear blue sea vs light land,
      // coastlines and borders read cleanly (the earlier translucent version washed everything out).
      { id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -0.15, 'raster-brightness-min': 0.06, 'raster-brightness-max': 1, 'raster-contrast': 0.18, 'raster-opacity': 1 } },
    ],
  }
}

// Sovereign-boundary overlay. Global basemaps render the de-facto / UN view, which does NOT match the
// Survey of India's official depiction (J&K, Ladakh incl. Aksai Chin, Arunachal Pradesh) — a legal
// requirement for maps shown in India. This draws an AUTHORITATIVE boundary GeoJSON on top when one is
// present at /geo/official_boundaries.geojson; it is a graceful no-op until that (licensed) file is supplied,
// so we never render a fabricated official boundary. See web/public/geo/README.md.
async function addOfficialBoundaries(m: maplibregl.Map) {
  try {
    const res = await fetch('/geo/official_boundaries.geojson')
    if (!res.ok) return                       // no authoritative file yet → no-op (never fabricate)
    const geo = await res.json()
    if (m.getSource('official-boundaries')) return
    m.addSource('official-boundaries', { type: 'geojson', data: geo })
    m.addLayer({
      id: 'official-boundaries', type: 'line', source: 'official-boundaries',
      paint: { 'line-color': '#12314f', 'line-width': 1.1 },
    })
  } catch { /* overlay is optional — never break the map */ }
}

// ── DOM helpers ──────────────────────────────────────────────────────────────
function labelEl(name: string, kind: string) {
  const d = document.createElement('div')
  d.textContent = kind === 'continent' ? name.toUpperCase() : name
  d.style.cssText = `pointer-events:none;white-space:nowrap;font-family:system-ui,sans-serif;
    text-shadow:0 0 3px #fff,0 0 3px #fff,0 1px 2px rgba(255,255,255,.9);transition:opacity .2s;`
  if (kind === 'continent') { d.style.fontSize = '12px'; d.style.letterSpacing = '0.2em'; d.style.color = '#33507a'; d.style.fontWeight = '600' }
  else { d.style.fontSize = '11px'; d.style.letterSpacing = '0.02em'; d.style.color = INK }
  return d
}
function plotEl(color: string) {
  const d = document.createElement('div')
  d.style.cssText = `width:11px;height:11px;border-radius:50%;background:${color};
    border:1.5px solid #fff;box-shadow:0 0 0 1px rgba(30,58,95,.25);cursor:pointer;`
  return d
}

export default function RiskMap() {
  const q = useQuery({ queryKey: ['portfolio'], queryFn: () => api.get<Portfolio>('/v1/supply/portfolio') })
  const el = useRef<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const labelMarkers = useRef<{ marker: maplibregl.Marker; kind: string }[]>([])
  const plotMarkers = useRef<maplibregl.Marker[]>([])
  const hexes = useRef<Hex[]>([])
  const curRes = useRef(-1)
  const [ready, setReady] = useState(false)
  const [selected, setSelected] = useState<Hex | null>(null)           // clicked cell → info panel
  const [hover, setHover] = useState<{ plot: Plot; x: number; y: number } | null>(null)  // hovered plot → tooltip
  const nav = useNavigate()

  // paint the H3 grid as SVG polygons, projected from lng/lat to screen — runs every render frame so it
  // stays glued to the map through pan/zoom, and (unlike a maplibre vector layer) shows on first load.
  function drawHexes() {
    const m = map.current, svg = svgRef.current
    if (!m || !svg) return
    let out = ''
    for (const h of hexes.current) {
      const scored = h.status === 'scored'
      const fill = scored ? hazardColor(h.score) : 'none'
      const fo = scored ? 0.4 : 0
      const stroke = scored ? 'rgba(30,58,95,0.55)' : 'rgba(51,80,122,0.28)'
      const sw = scored ? 1.1 : 0.6
      // a cell can clip into several land pieces at a jagged coast — draw each ring
      for (const ring of h.rings) {
        const pts = ring.map(([lon, lat]) => { const p = m.project([lon, lat]); return `${p.x.toFixed(1)},${p.y.toFixed(1)}` }).join(' ')
        out += `<polygon points="${pts}" fill="${fill}" fill-opacity="${fo}" stroke="${stroke}" stroke-width="${sw}" ` +
          `data-cell="${h.cell}" style="pointer-events:${scored ? 'auto' : 'none'};cursor:${scored ? 'pointer' : 'default'}"/>`
      }
    }
    svg.innerHTML = out
  }

  const INIT_CENTER: [number, number] = [-4.5, 39.3]
  const INIT_ZOOM = 4.9

  // init once
  useEffect(() => {
    if (!el.current || map.current) return
    const m = new maplibregl.Map({
      container: el.current, style: baseStyle(),
      // framed on the main sourcing cluster (Iberia) so the hex grid reads clearly on load; zoom out for the rest
      center: INIT_CENTER, zoom: INIT_ZOOM, minZoom: 1.5, maxZoom: 9, attributionControl: false,
      canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('style.load', () => { m.resize(); setReady(true); addOfficialBoundaries(m) })
    m.on('render', drawHexes)   // keep the SVG grid aligned to the map every frame
    const ro = new ResizeObserver(() => m.resize())
    ro.observe(el.current)
    map.current = m
    return () => { ro.disconnect(); m.remove(); map.current = null; setReady(false) }
  }, [])

  // load the H3 grid for the current zoom's resolution, then repaint
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    const load = async () => {
      const res = resForZoom(m.getZoom())
      if (res === curRes.current) return
      curRes.current = res
      try {
        const r = await api.get<HexResponse>(`/v1/supply/hex-hazard?res=${res}`)
        hexes.current = r.hexes
        drawHexes()
      } catch { curRes.current = -1 /* allow a retry on next zoom */ }
    }
    load()
    m.on('zoomend', load)

    // click a scored hexagon → open ONE info panel (replaces any open one); click empty map → close it
    const svg = svgRef.current
    const onClick = (e: MouseEvent) => {
      const cell = (e.target as SVGElement).getAttribute?.('data-cell')
      const h = cell && hexes.current.find(x => x.cell === cell)
      if (h && h.status === 'scored') setSelected(h)
    }
    const clear = () => setSelected(null)
    svg?.addEventListener('click', onClick)
    m.on('click', clear)   // clicks on empty map (not on a hex polygon) fall through the SVG to the canvas
    return () => { m.off('zoomend', load); m.off('click', clear); svg?.removeEventListener('click', onClick) }
  }, [ready])

  // place-name markers (English); country labels reveal as you zoom in
  useEffect(() => {
    const m = map.current
    if (!m || !ready || labelMarkers.current.length) return
    PLACE_LABELS.features.forEach(f => {
      const kind = f.properties.kind
      const marker = new maplibregl.Marker({ element: labelEl(f.properties.name, kind), anchor: 'center' })
        .setLngLat(f.geometry.coordinates as [number, number]).addTo(m)
      labelMarkers.current.push({ marker, kind })
    })
    const applyZoom = () => {
      const z = m.getZoom()
      labelMarkers.current.forEach(({ marker, kind }) => {
        marker.getElement().style.opacity = kind === 'continent' ? (z < 4.5 ? '1' : '0') : (z >= 2.4 ? '1' : '0')
      })
    }
    applyZoom(); m.on('zoom', applyZoom)
  }, [ready])

  // plot markers — hover shows the plot detail tooltip, mouse-out hides it
  useEffect(() => {
    const m = map.current, plots = q.data?.plots
    if (!m || !ready || !plots) return
    plotMarkers.current.forEach(mk => mk.remove()); plotMarkers.current = []
    plots.filter(p => p.lat != null && p.lon != null).forEach(p => {
      const elem = plotEl(hazardColor(p.hazard_score))
      elem.style.cursor = 'pointer'
      elem.addEventListener('mouseenter', () => {
        const c = el.current?.getBoundingClientRect(); const r = elem.getBoundingClientRect()
        if (c) setHover({ plot: p, x: r.left - c.left + r.width / 2, y: r.top - c.top })
      })
      elem.addEventListener('mouseleave', () => setHover(null))
      // click a plot marker → its full detail page (parity with every other clickable item in the app)
      elem.addEventListener('click', ev => { ev.stopPropagation(); nav(`/detail/plot/${p.plot_id}`) })
      const marker = new maplibregl.Marker({ element: elem, anchor: 'center' }).setLngLat([p.lon, p.lat]).addTo(m)
      plotMarkers.current.push(marker)
    })
  }, [q.data, ready])

  return (
    <div className="fadeup space-y-5">
      <PageHeader eyebrow="Agriculture · where the risk sits" title="Risk map"
        lead={<>
          The Earth as we index it — broken into <span className="text-[var(--color-ink)]">H3 hexagonal cells</span>.
          Each cell around your book carries its own hazard reading from the golden source. Zoom in and the cells get
          finer. Click a hexagon or a plot for the detail.
        </>} />

      <div className="flex flex-wrap items-center gap-4 text-[12px] text-[var(--color-mute)]">
        <Legend c="#34d399" l="low (<40)" /><Legend c="#f59e0b" l="medium (40–60)" />
        <Legend c="#fb7185" l="high (≥60)" /><Legend c="#64748b" l="not yet scored" />
        <span className="text-[var(--color-faint)]">· filled hex = per-cell hazard · outline = grid extends here</span>
      </div>

      <Card className="p-0 overflow-hidden">
        <div className="relative">
          <div ref={el} className="h-[600px] w-full" style={{ background: SKY }} />
          <svg ref={svgRef} className="absolute inset-0 w-full h-full" style={{ pointerEvents: 'none' }} />

          {/* hovered plot → floating tooltip */}
          {hover && (
            <div className="absolute z-10 rounded-lg px-3 py-2 shadow-xl"
              style={{ left: hover.x, top: hover.y, transform: 'translate(-50%,-100%) translateY(-12px)',
                pointerEvents: 'none', background: '#0b1a2e', border: '1px solid rgba(255,255,255,.1)', minWidth: 172 }}>
              <div className="text-[13px] font-semibold" style={{ color: '#f1f5f9' }}>{hover.plot.plot_name}</div>
              <div className="text-[11px] mt-0.5" style={{ color: '#9db4d4' }}>{hover.plot.commodity} · {hover.plot.country ?? '—'} · {eur(hover.plot.spend_eur)}</div>
              <div className="text-[11px] mt-1 flex items-center gap-1.5" style={{ color: '#cbd5e1' }}>
                <span className="inline-block w-2 h-2 rounded-full" style={{ background: hazardColor(hover.plot.hazard_score) }} />
                {prettyHazard(hover.plot.top_hazard)} hazard {hover.plot.hazard_score != null ? Math.round(hover.plot.hazard_score) : ''}
              </div>
              {hover.plot.eudr_covered && <div className="text-[11px] mt-0.5" style={{ color: '#9db4d4' }}>EUDR: {hover.plot.eudr_determination ?? 'not checked'}</div>}
            </div>
          )}

          {/* clicked cell → one info panel */}
          {selected && (
            <div className="absolute top-3 right-3 z-20 w-[264px] rounded-xl overflow-hidden shadow-2xl text-left"
              style={{ background: '#0b1a2e', border: '1px solid rgba(255,255,255,.1)' }}>
              <div className="h-1" style={{ background: hazardColor(selected.score) }} />
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="mono text-[9px] uppercase tracking-[0.18em]" style={{ color: '#7f9cc0' }}>H3 cell · hazard</div>
                    <div className="flex items-baseline gap-2 mt-1">
                      <span className="text-[26px] font-semibold leading-none" style={{ color: '#f1f5f9' }}>{Math.round(selected.score as number)}</span>
                      <span className="text-[12px] font-medium" style={{ color: hazardColor(selected.score) }}>{bandLabel(selected.score)}</span>
                    </div>
                  </div>
                  <button onClick={() => setSelected(null)} aria-label="Close"
                    className="text-[18px] leading-none px-1" style={{ color: '#7f9cc0' }}>×</button>
                </div>
                <div className="mt-3 space-y-1.5 text-[12px]">
                  <div className="flex justify-between"><span style={{ color: '#7f9cc0' }}>Driver</span><span style={{ color: '#e2e8f0' }}>{prettyHazard(selected.driver_hazard)}</span></div>
                  <div className="flex justify-between"><span style={{ color: '#7f9cc0' }}>Plots in cell</span><span style={{ color: '#e2e8f0' }}>{selected.n_plots}</span></div>
                </div>
                {selected.plots?.length ? (
                  <div className="mt-3 pt-3 space-y-1 max-h-[160px] overflow-y-auto" style={{ borderTop: '1px solid rgba(255,255,255,.08)' }}>
                    {selected.plots.map((pl, i) => (
                      <div key={i} className="flex items-center justify-between text-[12px]">
                        <span className="truncate mr-2" style={{ color: '#e2e8f0' }}>{pl.name}</span>
                        <span className="shrink-0" style={{ color: '#7f9cc0' }}>{pl.commodity}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="mt-3 mono text-[9px]" style={{ color: '#5b7396' }}>{selected.cell}</div>
              </div>
            </div>
          )}
        </div>
      </Card>
      <div className="text-[11px] text-[var(--color-faint)] mono">{q.data?.plots.length ?? 0} plots · scroll to zoom · drag to pan</div>
    </div>
  )
}
function Legend({ c, l }: { c: string; l: string }) {
  return <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />{l}</span>
}
