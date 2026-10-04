import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { GeoJSON, MapContainer, TileLayer } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Sprout } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { Card, PageHeader, SectionHead } from '../components/ui'
import ReviewTabs from '../components/ReviewTabs'

// Crop calibration coverage (E165) — for each crop, every country its crop map holds and what the platform publishes
// there: a loss and a gain range, a loss range, tested and held (no number), or not calibrated with the reason.
// Categories, not verdicts. Grows as reviewed data and calibrations land.

type Cat = 'both' | 'loss' | 'held' | 'none'
interface Row { origin: string; area_share: number; area_ha: number; category: Cat; label: string; why: string | null; drivers: string | null; r2_oos: number | null }
interface Resp { commodities: { commodity: string; origins: number; generated_at: string }[]; commodity: string | null; rows: Row[]; area_share_pct: Record<Cat, number>; categories: Record<Cat, string>; geometry: Record<string, GeoJSON.Geometry> }

const COLOR: Record<Cat, string> = { both: '#16a34a', loss: '#0ea5e9', held: '#f59e0b', none: '#94a3b8' }
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

export default function CropCoverage() {
  const [crop, setCrop] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['crop-coverage', crop], queryFn: () => api.get<Resp>(`/v1/supply/coverage${crop ? `?commodity=${encodeURIComponent(crop)}` : ''}`) })
  const d = q.data
  const dark = useDark()
  const fc = useMemo(() => ({ type: 'FeatureCollection' as const, features: (d?.rows ?? []).filter(r => d?.geometry[r.origin])
    .map(r => ({ type: 'Feature' as const, geometry: d!.geometry[r.origin], properties: r })) }), [d])
  return (
    <div className="fadeup space-y-5">
      <ReviewTabs />
      <PageHeader eyebrow="Review · crop coverage" title="Where each crop is calibrated"
        lead="Every country a crop's map shows it growing in, and what the platform publishes there. A range is published only where its calibration passed its gate; elsewhere the figure is held or the country is not calibrated yet, and the reason is given." />
      {q.isLoading ? <Card className="p-8 text-center text-[13px] text-[var(--color-faint)]">loading…</Card>
        : !d ? <Card className="p-8 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the coverage.')}</Card>
        : <>
          <div className="flex flex-wrap gap-1.5">
            {d.commodities.map(c => (
              <button key={c.commodity} onClick={() => setCrop(c.commodity)}
                className={`px-3 py-1 rounded-lg text-[12px] border transition ${d.commodity === c.commodity ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] border-transparent' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
                {c.commodity} <span className="opacity-70">· {c.origins}</span></button>))}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {(Object.keys(d.categories) as Cat[]).map(k => (
              <Card key={k} className="p-4">
                <div className="flex items-center gap-2 mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">
                  <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: COLOR[k] }} />{d.categories[k]}</div>
                <div className="mono text-[20px] text-[var(--color-ink)] mt-1 tabular-nums">{d.area_share_pct[k].toFixed(1)}%</div>
                <div className="text-[11px] text-[var(--color-faint)]">of {d.commodity}'s mapped harvested area</div>
              </Card>))}
          </div>
          <div className="relative w-full rounded-xl overflow-hidden border border-[var(--color-line)]" style={{ height: 420 }}>
            <MapContainer center={[25, 10]} zoom={2} minZoom={1} maxZoom={8} scrollWheelZoom={false} worldCopyJump
              style={{ width: '100%', height: '100%', background: dark ? '#0b1524' : '#e8eef4' }}>
              <TileLayer key={dark ? 'd' : 'l'} attribution="Tiles &copy; Esri · Countries &copy; EuroGeographics (GISCO)" url={dark ? DARK : LIGHT} />
              <GeoJSON key={`${d.commodity}-${fc.features.length}-${dark}`} data={fc}
                style={(f) => { const r = f?.properties as Row; return { color: COLOR[r.category], weight: 0.8, fillColor: COLOR[r.category], fillOpacity: 0.5 } }}
                onEachFeature={(f, layer) => { const r = f.properties as Row
                  layer.bindTooltip(`<b>${r.origin}</b> · ${r.label}<br/>${(r.area_share * 100).toFixed(1)}% of the mapped area` + (r.why ? `<br/><span style="opacity:.75">${r.why}</span>` : ''), { sticky: true }) }} />
            </MapContainer>
          </div>
          <Card className="p-0 overflow-hidden">
            <SectionHead icon={Sprout} className="px-5 py-3 border-b border-[var(--color-line)]">{d.commodity} · {d.rows.length} countries</SectionHead>
            <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
              <table className="w-full text-[12px] tabular-nums">
                <thead className="sticky top-0 bg-[var(--color-panel)]"><tr className="text-[var(--color-faint)] mono text-[10px] uppercase text-left">
                  {['Country', 'Share of mapped area', 'Published', 'Driver', 'r²oos', 'Why'].map(h => <th key={h} className="font-normal px-3 py-2">{h}</th>)}
                </tr></thead>
                <tbody>{d.rows.map(r => (
                  <tr key={r.origin} className="border-t border-[var(--color-line)]">
                    <td className="px-3 py-1 mono text-[var(--color-ink)]">{r.origin}</td>
                    <td className="px-3 mono">{(r.area_share * 100).toFixed(2)}%</td>
                    <td className="px-3"><span className="inline-flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-sm" style={{ background: COLOR[r.category] }} />{r.label}</span></td>
                    <td className="px-3">{r.drivers ?? '—'}</td>
                    <td className="px-3 mono">{r.r2_oos == null ? '—' : r.r2_oos.toFixed(2)}</td>
                    <td className="px-3 text-[11px] text-[var(--color-mute)]">{r.why ?? ''}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </Card>
        </>}
    </div>
  )
}
