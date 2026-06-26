import { useEffect, useRef, useMemo } from 'react'
import maplibregl from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { H3HexagonLayer } from '@deck.gl/geo-layers'
import 'maplibre-gl/dist/maplibre-gl.css'
import { scoreToColor, INITIAL_VIEW_STATE, HAZARD_VIEWS } from '../mockData'

const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

export default function RiskMap({ scores, onCellClick, hazard }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const overlayRef = useRef(null)

  // Build the H3 layer from current scores
  const h3Layer = useMemo(() => new H3HexagonLayer({
    id: 'risk-h3',
    data: scores,
    getHexagon: d => d.h3_cell,
    getFillColor: d => scoreToColor(d.score, Math.abs((d.velocity_24h ?? 0)) > 5 ? 220 : 180),
    getElevation: d => d.score * 30,
    elevationScale: 1,
    extruded: true,
    wireframe: false,
    pickable: true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 60],
    onClick: ({ object }) => object && onCellClick(object),
  }), [scores, onCellClick])

  // Mount the map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [INITIAL_VIEW_STATE.longitude, INITIAL_VIEW_STATE.latitude],
      zoom: INITIAL_VIEW_STATE.zoom,
      pitch: INITIAL_VIEW_STATE.pitch,
      bearing: INITIAL_VIEW_STATE.bearing,
      antialias: true,
    })

    const overlay = new MapboxOverlay({ interleaved: false, layers: [] })
    map.addControl(overlay)

    mapRef.current = map
    overlayRef.current = overlay

    return () => {
      overlay.finalize()
      map.remove()
      mapRef.current = null
      overlayRef.current = null
    }
  }, [])

  // Update layers whenever scores change
  useEffect(() => {
    overlayRef.current?.setProps({ layers: [h3Layer] })
  }, [h3Layer])

  // Fly to hazard region when switching
  useEffect(() => {
    if (!mapRef.current || !hazard) return
    const view = HAZARD_VIEWS[hazard]
    if (!view) return
    mapRef.current.flyTo({
      center: [view.longitude, view.latitude],
      zoom: view.zoom,
      pitch: view.pitch,
      bearing: view.bearing,
      duration: 1400,
      essential: true,
    })
  }, [hazard])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%' }}
    />
  )
}
