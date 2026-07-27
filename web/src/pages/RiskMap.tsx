import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { LatLngBoundsExpression } from 'leaflet'
import { api } from '../lib/api'
import { Eyebrow, Card } from '../components/ui'

interface Plot {
  plot_id: string; commodity: string; eudr_covered: boolean; plot_name: string; country: string | null
  lat: number; lon: number; spend_eur: number; eudr_determination: string | null
  top_hazard: string | null; hazard_score: number | null
}
interface Portfolio { plots: Plot[] }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`
const color = (s: number | null) => s == null ? '#64748b' : s >= 60 ? '#fb7185' : s >= 40 ? '#f59e0b' : '#34d399'

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression | null }) {
  const map = useMap()
  useMemo(() => { if (bounds) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 6 }) }, [bounds, map])
  return null
}

export default function RiskMap() {
  const q = useQuery({ queryKey: ['portfolio'], queryFn: () => api.get<Portfolio>('/v1/supply/portfolio') })
  const plots = (q.data?.plots ?? []).filter(p => p.lat != null && p.lon != null)
  const bounds = plots.length ? plots.map(p => [p.lat, p.lon]) as LatLngBoundsExpression : null

  return (
    <div className="fadeup space-y-5">
      <div>
        <Eyebrow>Agriculture · where the risk sits</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Risk map</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Every sourcing plot on the map, coloured by live climate hazard. Click a plot to see its hazard, spend and
          EUDR determination.
        </p>
      </div>

      <div className="flex items-center gap-4 text-[12px] text-[var(--color-mute)]">
        <Legend c="#34d399" l="low (<40)" /><Legend c="#f59e0b" l="medium (40–60)" />
        <Legend c="#fb7185" l="high (≥60)" /><Legend c="#64748b" l="unscored" />
      </div>

      <Card className="p-0 overflow-hidden" >
        <div className="h-[560px]">
          {q.isLoading ? <div className="h-full grid place-items-center text-[var(--color-faint)] text-sm">loading map…</div> :
            <MapContainer center={[20, 0]} zoom={2} style={{ height: '100%', width: '100%', background: '#0a0f1c' }} scrollWheelZoom={false}>
              <TileLayer attribution="&copy; OpenStreetMap &copy; CARTO"
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
              <FitBounds bounds={bounds} />
              {plots.map(p => (
                <CircleMarker key={p.plot_id} center={[p.lat, p.lon]} radius={8}
                  pathOptions={{ color: color(p.hazard_score), fillColor: color(p.hazard_score), fillOpacity: 0.55, weight: 2 }}>
                  <Popup>
                    <div style={{ minWidth: 180 }}>
                      <div style={{ fontWeight: 600 }}>{p.plot_name}</div>
                      <div style={{ color: '#475569', fontSize: 12 }}>{p.commodity} · {p.country ?? '—'} · {eur(p.spend_eur)}</div>
                      <div style={{ fontSize: 12, marginTop: 4 }}>
                        Hazard: {p.top_hazard ?? '—'} {p.hazard_score != null ? p.hazard_score.toFixed(0) : ''}
                      </div>
                      {p.eudr_covered && <div style={{ fontSize: 12, marginTop: 4 }}>EUDR: {p.eudr_determination ?? 'not checked'}</div>}
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </MapContainer>}
        </div>
      </Card>

      <div className="text-[11px] text-[var(--color-faint)] mono">{plots.length} plots plotted · click a marker for detail</div>
    </div>
  )
}
function Legend({ c, l }: { c: string; l: string }) {
  return <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />{l}</span>
}
