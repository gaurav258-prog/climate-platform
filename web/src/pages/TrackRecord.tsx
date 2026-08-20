import { useState } from 'react'
import { Search, Download, History, ShieldAlert } from 'lucide-react'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Eyebrow, Card } from '../components/ui'

// Climate Track Record — the diligence deliverable. Enter any location; get the real events that have already
// crossed it (observed catalogue) plus its current hazard scores, and hand over a one-page PDF dossier.

interface REvent { kind: string; name?: string; year: number | null; severity: string; closest_km?: number }
interface Hazard { hazard: string; label: string; score: number; bucket: string }
interface Dossier {
  location: { name: string | null; lat: number; lon: number; h3_cell: string }
  verdict: string; since_year: number | null
  realized: { n_events: number; n_storms: number; n_earthquakes: number; events: REvent[] }
  current_risk: Hazard[]; headline_current: Hazard | null; note: string
}

const PRESETS: [string, number, number][] = [
  ['Warehouse · SW Portugal', 37.95, -8.87],
  ['Vineyard · Valencia, ES', 39.47, -0.38],
  ['Plant · Sicily, IT', 37.5, 15.09],
  ['Port · Rotterdam, NL', 51.95, 4.14],
]
const BUCKET_COLOR: Record<string, string> = { VH: '#D23B3B', H: '#E8744A', M: '#E8B24C', L: '#7BBF8F', none: '#6d8299' }

export default function TrackRecord() {
  const [lat, setLat] = useState('37.95')
  const [lon, setLon] = useState('-8.87')
  const [name, setName] = useState('Warehouse · SW Portugal')
  const [d, setD] = useState<Dossier | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async (la = lat, lo = lon, nm = name) => {
    setBusy(true)
    try {
      const qs = `lat=${encodeURIComponent(la)}&lon=${encodeURIComponent(lo)}${nm ? `&name=${encodeURIComponent(nm)}` : ''}`
      setD(await api.get<Dossier>(`/v1/realized-exposure/track-record?${qs}`))
    } catch { toast.error('Could not build the track record — check the coordinates.') } finally { setBusy(false) }
  }
  const pdf = () => {
    const qs = `lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}${name ? `&name=${encodeURIComponent(name)}` : ''}`
    download(`/v1/realized-exposure/track-record.pdf?${qs}`, 'climate-track-record.pdf').catch(() => toast.error('Download failed.'))
  }

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Diligence · any address on Earth</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Climate Track Record</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Underwriting a risk, lending against an asset, or acquiring a book? Get one location's climate track record — the real events that have <em>already</em> crossed it, and its current hazard scores. Observed catalogue + golden source. A dossier, not a filing.
        </p>
      </div>

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Latitude</span>
            <input value={lat} onChange={e => setLat(e.target.value)} className="w-28 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] tabular-nums" /></label>
          <label className="flex flex-col gap-1"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Longitude</span>
            <input value={lon} onChange={e => setLon(e.target.value)} className="w-28 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] tabular-nums" /></label>
          <label className="flex flex-col gap-1 flex-1 min-w-[180px]"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Label (optional)</span>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px]" /></label>
          <button onClick={() => run()} disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[#08131f] font-semibold px-3.5 py-2 text-[13px] disabled:opacity-60">
            <Search size={14} /> {busy ? 'Building…' : 'Get track record'}</button>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {PRESETS.map(([nm, la, lo]) => (
            <button key={nm} onClick={() => { setLat(String(la)); setLon(String(lo)); setName(nm); run(String(la), String(lo), nm) }}
              className="mono text-[10.5px] px-2 py-1 rounded-lg border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">{nm}</button>
          ))}
        </div>
      </Card>

      {d && (
        <Card className="p-5" style={{ borderColor: 'var(--color-blued)' }}>
          <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
            <div>
              <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-sky)]">{d.location.name || 'Location'}</div>
              <div className="mono text-[11px] text-[var(--color-faint)]">{d.location.lat.toFixed(5)}, {d.location.lon.toFixed(5)} · H3 {d.location.h3_cell}</div>
            </div>
            <button onClick={pdf} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]"><Download size={13} /> Download dossier (PDF)</button>
          </div>
          <p className="display text-[19px] font-semibold text-[var(--color-ink)] leading-snug max-w-3xl">{d.verdict}</p>

          <div className="grid md:grid-cols-2 gap-4 mt-4">
            <div>
              <div className="flex items-center gap-1.5 mb-2"><History size={14} className="text-[var(--color-warn)]" /><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Already crossed this location · observed</span></div>
              {d.realized.events.length === 0
                ? <div className="text-[12.5px] text-[var(--color-mute)]">No catalogued storm or earthquake within the felt radius.</div>
                : <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
                    {d.realized.events.slice(0, 8).map((e, i) => (
                      <div key={i} className="flex items-baseline gap-2 py-1.5 text-[12.5px]">
                        <span>{e.kind === 'earthquake' ? '⊕' : '🌀'}</span>
                        <span className="font-medium text-[var(--color-ink)]">{e.name}</span>
                        <span className="mono text-[10px] text-[var(--color-faint)]">{e.year ?? '—'}</span>
                        <span className="ml-auto mono text-[10.5px] text-[var(--color-mute)]">{e.severity} · {e.closest_km}km</span>
                      </div>
                    ))}
                  </div>}
            </div>
            <div>
              <div className="flex items-center gap-1.5 mb-2"><ShieldAlert size={14} className="text-[var(--color-sky)]" /><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Current physical risk · golden source</span></div>
              {d.current_risk.length === 0
                ? <div className="text-[12.5px] text-[var(--color-mute)]">Not yet scored for this cell (scores on demand in production).</div>
                : <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
                    {d.current_risk.slice(0, 8).map(h => (
                      <div key={h.hazard} className="flex items-center gap-2 py-1.5 text-[12.5px]">
                        <span className="text-[var(--color-ink)]">{h.label}</span>
                        <span className="ml-auto mono text-[10.5px] px-1.5 py-0.5 rounded" style={{ background: `${BUCKET_COLOR[h.bucket] || '#6d8299'}22`, color: BUCKET_COLOR[h.bucket] || '#6d8299' }}>{h.bucket} · {h.score}/100</span>
                      </div>
                    ))}
                  </div>}
            </div>
          </div>
          <div className="mono text-[9.5px] text-[var(--color-faint)] mt-4">{d.note}</div>
        </Card>
      )}
    </div>
  )
}
