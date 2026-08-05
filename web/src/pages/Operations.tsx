import { useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, Factory, Warehouse, Boxes, Building, MapPin, Upload, Plus } from 'lucide-react'
import { api } from '../lib/api'
import { Eyebrow, Card, Stat, Button } from '../components/ui'
import { hazardLabel, bucketLabel } from '../lib/hazards'
import AddressAutocomplete, { type Place } from '../components/AddressAutocomplete'

interface Site {
  site_id: string; name: string; site_type: string; lat: number | null; lon: number | null
  country: string | null; value_eur: number | null; throughput_eur: number | null; bi_at_risk_eur: number | null
  top_hazard: string | null; hazard_score: number | null; bucket: string | null
}
interface Totals { asset_value_eur: number; throughput_eur: number; bi_at_risk_eur: number; n_elevated: number }
interface SitesResp { sites: Site[]; site_types: string[]; totals: Totals; bi_note: string }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`
const hz = (s: number | null) => s == null ? 'var(--color-faint)' : s >= 60 ? 'var(--color-bad)' : s >= 40 ? 'var(--color-warn)' : 'var(--color-good)'
const pretty = hazardLabel
const typeLabel = (t: string) => t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
const TypeIcon = ({ t }: { t: string }) => {
  const I = t === 'hq' ? Building2 : t === 'factory' ? Factory : t === 'warehouse' ? Warehouse
    : t === 'distribution_centre' ? Boxes : t === 'office' ? Building : MapPin
  return <I size={15} className="text-[var(--color-sky)]" />
}

export default function Operations() {
  const q = useQuery({ queryKey: ['sites'], queryFn: () => api.get<SitesResp>('/v1/supply/sites') })
  const [form, setForm] = useState({ name: '', site_type: 'factory', address: '', latitude: '', longitude: '', annual_value_eur: '', annual_throughput_eur: '' })
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'err' } | null>(null)
  const [nameErr, setNameErr] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)
  const [chosen, setChosen] = useState<Place | null>(null)
  const hasCoords = form.latitude.trim() !== '' && form.longitude.trim() !== ''

  const add = async () => {
    if (!form.name.trim()) { setNameErr(true); nameRef.current?.focus(); setMsg({ text: 'Give the site a name first (e.g. "Frankfurt DC").', tone: 'err' }); return }
    const useChosen = chosen && !hasCoords
    if (!hasCoords && !chosen && form.address.trim()) { setMsg({ text: 'Pick the matching place from the list, or enter coordinates.', tone: 'err' }); return }
    if (!hasCoords && !chosen && !form.address.trim()) { setMsg({ text: 'Search an address and pick a place, or enter coordinates.', tone: 'err' }); return }
    setBusy(true); setMsg(null)
    try {
      const r = await api.post<{ ok: boolean; site: { lat: number; lon: number; geocode_precision: string } }>('/v1/supply/sites', {
        name: form.name.trim(), site_type: form.site_type,
        // a chosen place sends its exact coordinates (no re-geocode drift); its name rides along as the address
        address: useChosen ? chosen!.display_name : (form.address.trim() || null),
        latitude: useChosen ? chosen!.lat : (form.latitude ? Number(form.latitude) : null),
        longitude: useChosen ? chosen!.lon : (form.longitude ? Number(form.longitude) : null),
        annual_value_eur: form.annual_value_eur ? Number(form.annual_value_eur) : null,
        annual_throughput_eur: form.annual_throughput_eur ? Number(form.annual_throughput_eur) : null,
      })
      const where = useChosen ? chosen!.display_name : `${r.site.lat.toFixed(3)}, ${r.site.lon.toFixed(3)}`
      setMsg({ text: `✓ Added "${form.name.trim()}" at ${where}. Scoring on the live hazard grid — it'll appear in the table shortly (a new region may take a moment).`, tone: 'ok' })
      setForm({ name: '', site_type: 'factory', address: '', latitude: '', longitude: '', annual_value_eur: '', annual_throughput_eur: '' })
      setChosen(null)
      await q.refetch()
    } catch (e) {
      setMsg({ text: (e as { body?: { detail?: { message?: string } } })?.body?.detail?.message
        || 'Could not add — pick a place or enter coordinates.', tone: 'err' })
    } finally { setBusy(false) }
  }

  const upload = async (file: File) => {
    setBusy(true); setMsg(null)
    try {
      const fd = new FormData(); fd.append('file', file)
      const r = await api.post<{ added: number; skipped: { name: string }[] }>('/v1/supply/sites/upload', fd)
      setMsg({ text: `Added ${r.added} site${r.added === 1 ? '' : 's'}${r.skipped.length ? `, ${r.skipped.length} skipped (couldn't locate)` : ''}.`, tone: 'ok' })
      await q.refetch()
    } catch { setMsg({ text: 'Upload failed — check the CSV columns against the template.', tone: 'err' }) }
    finally { setBusy(false) }
  }

  const sites = q.data?.sites ?? []
  const types = q.data?.site_types ?? ['hq', 'factory', 'warehouse', 'distribution_centre', 'office', 'other']
  const t = q.data?.totals
  const highN = t?.n_elevated ?? sites.filter(s => (s.hazard_score ?? 0) >= 40).length

  return (
    <div className="fadeup space-y-7">
      <div>
        <Eyebrow>Agriculture · your operations</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Operations</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Your own sites — head office, plants, cold stores, distribution centres — geolocated and scored on the same
          live hazard data as your suppliers. Add a site by address or coordinates and it's on the map in seconds.
        </p>
      </div>

      <div className="grid sm:grid-cols-4 gap-4">
        <Stat big={sites.length} label="operational sites" />
        <Stat big={highN} label="at elevated hazard (≥40)" tone={highN ? 'warn' : 'ink'} />
        <Stat big={eur(t?.asset_value_eur)} label="asset value (damage exposure)" />
        <Stat big={eur(t?.bi_at_risk_eur)} label="business-interruption exposure" tone={(t?.bi_at_risk_eur ?? 0) > 0 ? 'warn' : 'ink'} />
      </div>
      <div className="text-[11px] text-[var(--color-faint)] -mt-3">{q.data?.bi_note}</div>

      {/* add a site */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <Plus size={16} className="text-[var(--color-sky)]" />
          <span className="text-[14px] font-semibold">Add a site</span>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Field label="Name *"><input ref={nameRef} className={inp}
            style={nameErr ? { borderColor: 'var(--color-warn)', boxShadow: '0 0 0 1px var(--color-warn)' } : undefined}
            value={form.name}
            onChange={e => { setForm({ ...form, name: e.target.value }); if (nameErr) setNameErr(false) }} placeholder="e.g. Frankfurt DC" /></Field>
          <Field label="Type">
            <select className={inp} value={form.site_type} onChange={e => setForm({ ...form, site_type: e.target.value })}>
              {types.map(t => <option key={t} value={t}>{typeLabel(t)}</option>)}
            </select>
          </Field>
          <Field label="Address (or use coordinates)">
            <AddressAutocomplete value={form.address} selected={chosen} disabled={hasCoords}
              onValueChange={v => { setChosen(null); setForm(f => ({ ...f, address: v })) }}
              onSelect={p => { setChosen(p); setForm(f => ({ ...f, address: p.display_name })) }} />
            {hasCoords && form.address.trim() && <div className="mt-1.5 text-[11px] text-[var(--color-faint)]">using the coordinates below (address ignored)</div>}
          </Field>
          <Field label="Asset value € (PP&E + stock)"><input className={inp} value={form.annual_value_eur} onChange={e => setForm({ ...form, annual_value_eur: e.target.value })} placeholder="85000000" inputMode="numeric" /></Field>
          <Field label="Annual throughput € (revenue)"><input className={inp} value={form.annual_throughput_eur} onChange={e => setForm({ ...form, annual_throughput_eur: e.target.value })} placeholder="210000000" inputMode="numeric" /></Field>
          <Field label="Latitude"><input className={inp} value={form.latitude} onChange={e => setForm({ ...form, latitude: e.target.value })} placeholder="37.39" inputMode="decimal" /></Field>
          <Field label="Longitude"><input className={inp} value={form.longitude} onChange={e => setForm({ ...form, longitude: e.target.value })} placeholder="-5.98" inputMode="decimal" /></Field>
          <div className="flex items-end"><Button onClick={add} disabled={busy}>{busy ? 'Adding…' : 'Add & score'}</Button></div>
          <div className="flex items-end gap-3 text-[12px]">
            <label className="inline-flex items-center gap-1.5 cursor-pointer text-[var(--color-mute)] hover:text-[var(--color-sky)]">
              <Upload size={14} /> Upload CSV
              <input type="file" accept=".csv" className="hidden" onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
            <a href="/v1/supply/sites/template.xlsx" className="text-[var(--color-faint)] hover:text-[var(--color-sky)] underline">template</a>
          </div>
        </div>
        {msg && <div className={`mt-3 text-[12.5px] font-medium ${msg.tone === 'ok' ? 'text-[var(--color-good)]' : 'text-[var(--color-warn)]'}`}>{msg.text}</div>}
      </Card>

      {/* sites table */}
      <Card className="p-5">
        {q.isLoading ? <div className="py-8 text-center text-[var(--color-faint)] text-sm">loading…</div> :
          sites.length === 0 ? <div className="py-8 text-center text-[var(--color-faint)] text-sm">No sites yet — add your first above.</div> : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                    <th className="font-normal py-2 pr-3">Site</th><th className="font-normal pr-3">Type</th>
                    <th className="font-normal pr-3">Location</th><th className="font-normal pr-3 text-right">Asset value</th>
                    <th className="font-normal pr-3 text-right">Throughput</th><th className="font-normal pr-3 text-right">BI exposure</th>
                    <th className="font-normal pr-3">Worst hazard</th>
                  </tr>
                </thead>
                <tbody>
                  {sites.map(s => (
                    <tr key={s.site_id} onClick={() => window.open(`/detail/site/${s.site_id}`, '_blank')}
                      className="border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-panel)] transition">
                      <td className="py-2.5 pr-3 text-[var(--color-ink)] hover:text-[var(--color-sky)]">{s.name}</td>
                      <td className="pr-3"><span className="inline-flex items-center gap-1.5 text-[var(--color-mute)]"><TypeIcon t={s.site_type} />{typeLabel(s.site_type)}</span></td>
                      <td className="pr-3 mono text-[11px] text-[var(--color-mute)]">{s.country ?? '—'} · {s.lat?.toFixed(2)}, {s.lon?.toFixed(2)}</td>
                      <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(s.value_eur)}</td>
                      <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(s.throughput_eur)}</td>
                      <td className="pr-3 text-right mono" style={{ color: s.bi_at_risk_eur ? 'var(--color-warn)' : 'var(--color-faint)' }}>{s.bi_at_risk_eur ? eur(s.bi_at_risk_eur) : '—'}</td>
                      <td className="pr-3">
                        {s.hazard_score != null
                          ? <span className="mono text-[12px]" style={{ color: hz(s.hazard_score) }}>{pretty(s.top_hazard)} {s.hazard_score.toFixed(0)} · {bucketLabel(s.bucket)}</span>
                          : <span className="mono text-[11px] text-[var(--color-faint)]">not yet scored</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Card>
    </div>
  )
}

const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono">{label}</div>{children}</label>
}
