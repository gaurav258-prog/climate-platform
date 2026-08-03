import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Upload, Sprout } from 'lucide-react'
import { api } from '../lib/api'
import { Eyebrow, Card, Stat, StatusPill, Button } from '../components/ui'
import AddressAutocomplete, { type Place } from '../components/AddressAutocomplete'
import { hazardLabel, sevColor, sevLabel } from '../lib/hazards'

interface Plot {
  plot_id: string; commodity: string; eudr_covered: boolean; plot_name: string; region: string | null
  country: string | null; lat: number; lon: number; spend_eur: number; eudr_determination: string | null
  top_hazard: string | null; hazard_score: number | null
}
interface Portfolio { plots: Plot[] }
interface Commodity { id: string; name: string; eudr_covered: boolean }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`
const hz = (s: number | null) => s == null ? 'var(--color-faint)' : s >= 60 ? 'var(--color-bad)' : s >= 40 ? 'var(--color-warn)' : 'var(--color-good)'
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'

export default function Sourcing() {
  const q = useQuery({ queryKey: ['portfolio'], queryFn: () => api.get<Portfolio>('/v1/supply/portfolio') })
  const cq = useQuery({ queryKey: ['commodities'], queryFn: () => api.get<{ commodities: Commodity[] }>('/v1/supply/commodities') })

  const [form, setForm] = useState({ plot_name: '', commodity: '', address: '', latitude: '', longitude: '', annual_spend_eur: '', plot_area_ha: '' })
  const [chosen, setChosen] = useState<Place | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'err' } | null>(null)
  const hasCoords = form.latitude.trim() !== '' && form.longitude.trim() !== ''

  const add = async () => {
    if (!form.plot_name.trim()) { setMsg({ text: 'Give the plot a name.', tone: 'err' }); return }
    if (!form.commodity) { setMsg({ text: 'Pick the commodity sourced from this plot.', tone: 'err' }); return }
    if (!form.annual_spend_eur || Number(form.annual_spend_eur) <= 0) { setMsg({ text: 'Enter the annual spend (€) on this plot.', tone: 'err' }); return }
    const useChosen = chosen && !hasCoords
    if (!hasCoords && !chosen) { setMsg({ text: 'Search an address and pick a place, or enter coordinates.', tone: 'err' }); return }
    setBusy(true); setMsg(null)
    try {
      const r = await api.post<{ ok: boolean; plot: { lat: number; lon: number; resolved_name: string | null; needs_polygon: boolean } }>('/v1/supply/plots', {
        plot_name: form.plot_name.trim(), commodity: form.commodity,
        address: useChosen ? chosen!.display_name : (form.address.trim() || null),
        latitude: useChosen ? chosen!.lat : (form.latitude ? Number(form.latitude) : null),
        longitude: useChosen ? chosen!.lon : (form.longitude ? Number(form.longitude) : null),
        annual_spend_eur: Number(form.annual_spend_eur),
        plot_area_ha: form.plot_area_ha ? Number(form.plot_area_ha) : null,
      })
      const where = useChosen ? chosen!.display_name : `${r.plot.lat.toFixed(3)}, ${r.plot.lon.toFixed(3)}`
      const poly = r.plot.needs_polygon ? ' (>4 ha — add a polygon boundary for EUDR).' : ''
      setMsg({ text: `✓ Added "${form.plot_name.trim()}" (${form.commodity}) at ${where}. Scoring on the live hazard grid — it'll appear shortly.${poly}`, tone: 'ok' })
      setForm({ plot_name: '', commodity: '', address: '', latitude: '', longitude: '', annual_spend_eur: '', plot_area_ha: '' })
      setChosen(null)
      await q.refetch()
    } catch (e) {
      setMsg({ text: (e as { body?: { detail?: { message?: string } } })?.body?.detail?.message || 'Could not add — pick a place or enter coordinates.', tone: 'err' })
    } finally { setBusy(false) }
  }

  const upload = async (file: File) => {
    setBusy(true); setMsg(null)
    try {
      const fd = new FormData(); fd.append('file', file)
      const r = await api.post<{ n_uploaded: number; unknown_commodities: string[]; geometry_errors: { plot: string }[]; needs_polygon: string[] }>('/v1/supply/plots/upload', fd)
      const parts = [`Added ${r.n_uploaded} plot${r.n_uploaded === 1 ? '' : 's'}`]
      if (r.unknown_commodities?.length) parts.push(`${r.unknown_commodities.length} skipped (unknown commodity: ${r.unknown_commodities.join(', ')})`)
      if (r.geometry_errors?.length) parts.push(`${r.geometry_errors.length} bad geometry`)
      if (r.needs_polygon?.length) parts.push(`${r.needs_polygon.length} need a polygon (>4 ha)`)
      setMsg({ text: `✓ ${parts.join(' · ')}.`, tone: 'ok' })
      await q.refetch()
    } catch (e) {
      setMsg({ text: (e as { body?: { detail?: { missing?: string[] } } })?.body?.detail?.missing
        ? `Upload failed — missing columns: ${(e as { body: { detail: { missing: string[] } } }).body.detail.missing.join(', ')}.`
        : 'Upload failed — check the CSV columns against the template.', tone: 'err' })
    } finally { setBusy(false) }
  }

  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — is the API on :8001?</Center>
  const plots = [...q.data.plots].sort((a, b) => (b.spend_eur ?? 0) - (a.spend_eur ?? 0))
  const totalSpend = plots.reduce((s, p) => s + (p.spend_eur ?? 0), 0)
  const eudrPlots = plots.filter(p => p.eudr_covered).length
  const commodities = cq.data?.commodities ?? []
  // annual spend exposed by hazard — plain-language, traffic-light by severity
  const byHazard: Record<string, { eur: number; n: number; worst: number }> = {}
  for (const p of plots) {
    if (!p.top_hazard || p.hazard_score == null) continue
    const g = (byHazard[p.top_hazard] ??= { eur: 0, n: 0, worst: 0 })
    g.eur += p.spend_eur ?? 0; g.n += 1; g.worst = Math.max(g.worst, p.hazard_score)
  }
  const hazGroups = Object.entries(byHazard).sort((a, b) => b[1].worst - a[1].worst || b[1].eur - a[1].eur)

  return (
    <div className="fadeup space-y-7">
      <div>
        <Eyebrow>Agriculture · your book</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Sourcing book</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Every plot you source from — geolocated, scored on live hazard, and (where EUDR-covered) checked against
          satellite forest-loss. Add plots one at a time, or bulk-upload your whole procurement book.
        </p>
      </div>

      <div className="grid sm:grid-cols-3 gap-4">
        <Stat big={plots.length} label="sourcing plots" />
        <Stat big={eur(totalSpend)} label="annual spend" />
        <Stat big={eudrPlots} label="EUDR-covered plots" />
      </div>

      {/* annual spend exposed by hazard — plain-language, traffic-light */}
      {hazGroups.length > 0 && (
        <Card className="p-5">
          <div className="flex items-baseline justify-between mb-1">
            <span className="text-[14px] font-semibold">Annual spend at risk, by threat</span>
            <span className="text-[11px] text-[var(--color-faint)]">worst threat first · colour = severity</span>
          </div>
          <p className="text-[12px] text-[var(--color-mute)] mb-4">
            How much of your yearly procurement spend sits on plots whose biggest climate threat is each of these.
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {hazGroups.map(([hz, g]) => (
              <div key={hz} className="rounded-xl border p-3.5" style={{ borderColor: `${sevColor(g.worst)}55`, background: `${sevColor(g.worst)}10` }}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[12.5px] font-medium text-[var(--color-ink)]">{hazardLabel(hz)}</span>
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded" style={{ color: sevColor(g.worst), background: `${sevColor(g.worst)}22` }}>{sevLabel(g.worst)}</span>
                </div>
                <div className="text-2xl font-semibold mono" style={{ color: sevColor(g.worst) }}>{eur(g.eur)}</div>
                <div className="text-[11px] text-[var(--color-mute)] mt-0.5">{g.n} plot{g.n === 1 ? '' : 's'} · annual spend exposed</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* add plots — single, or bulk CSV */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3"><Plus size={16} className="text-[var(--color-sky)]" /><span className="text-[14px] font-semibold">Add sourcing plots</span></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Field label="Plot name *"><input className={inp} value={form.plot_name} onChange={e => setForm({ ...form, plot_name: e.target.value })} placeholder="e.g. Côte d'Ivoire cocoa lot 12" /></Field>
          <Field label="Commodity *">
            <select className={inp} value={form.commodity} onChange={e => setForm({ ...form, commodity: e.target.value })}>
              <option value="">Select…</option>
              {commodities.map(c => <option key={c.id} value={c.name}>{c.name}{c.eudr_covered ? ' · EUDR' : ''}</option>)}
            </select>
          </Field>
          <Field label="Address (or use coordinates)">
            <AddressAutocomplete value={form.address} selected={chosen} disabled={hasCoords}
              onValueChange={v => { setChosen(null); setForm(f => ({ ...f, address: v })) }}
              onSelect={p => { setChosen(p); setForm(f => ({ ...f, address: p.display_name })) }} />
            {hasCoords && form.address.trim() && <div className="mt-1.5 text-[11px] text-[var(--color-faint)]">using the coordinates below (address ignored)</div>}
          </Field>
          <Field label="Annual spend € *"><input className={inp} value={form.annual_spend_eur} onChange={e => setForm({ ...form, annual_spend_eur: e.target.value })} placeholder="2500000" inputMode="numeric" /></Field>
          <Field label="Plot area (ha)"><input className={inp} value={form.plot_area_ha} onChange={e => setForm({ ...form, plot_area_ha: e.target.value })} placeholder="optional · >4 ha needs a polygon" inputMode="decimal" /></Field>
          <Field label="Latitude"><input className={inp} value={form.latitude} onChange={e => setForm({ ...form, latitude: e.target.value })} placeholder="7.54" inputMode="decimal" /></Field>
          <Field label="Longitude"><input className={inp} value={form.longitude} onChange={e => setForm({ ...form, longitude: e.target.value })} placeholder="-5.55" inputMode="decimal" /></Field>
          <div className="flex items-end"><Button onClick={add} disabled={busy}>{busy ? 'Adding…' : 'Add & score'}</Button></div>
        </div>
        <div className="flex items-center gap-3 text-[12px] mt-3">
          <label className="inline-flex items-center gap-1.5 cursor-pointer text-[var(--color-mute)] hover:text-[var(--color-sky)]">
            <Upload size={14} /> Bulk-upload CSV
            <input type="file" accept=".csv" className="hidden" onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
          <a href="/v1/supply/plots/template.xlsx" className="text-[var(--color-faint)] hover:text-[var(--color-sky)] underline">template</a>
        </div>
        {msg && <div className={`mt-3 text-[12.5px] font-medium ${msg.tone === 'ok' ? 'text-[var(--color-good)]' : 'text-[var(--color-warn)]'}`}>{msg.text}</div>}
      </Card>

      <Card className="p-5">
        {plots.length === 0 ? <div className="py-8 text-center text-[var(--color-faint)] text-sm flex flex-col items-center gap-2"><Sprout size={20} /> No plots yet — add your first above.</div> : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <th className="font-normal py-2 pr-3">Plot</th><th className="font-normal pr-3">Commodity</th>
                <th className="font-normal pr-3">Location</th><th className="font-normal pr-3 text-right">Spend</th>
                <th className="font-normal pr-3">Hazard</th><th className="font-normal">EUDR</th>
              </tr>
            </thead>
            <tbody>
              {plots.map(p => (
                <tr key={p.plot_id} onClick={() => window.open(`/detail/plot/${p.plot_id}`, '_blank')}
                  className="border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-panel)] transition">
                  <td className="py-2.5 pr-3 text-[var(--color-ink)] hover:text-[var(--color-sky)]">{p.plot_name}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{p.commodity}</td>
                  <td className="pr-3 mono text-[11px] text-[var(--color-mute)]">{p.region ?? '—'} · {p.country ?? '—'}</td>
                  <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(p.spend_eur)}</td>
                  <td className="pr-3">
                    {p.hazard_score != null
                      ? <span className="mono text-[12px]" style={{ color: hz(p.hazard_score) }}>{p.top_hazard} {p.hazard_score.toFixed(0)}</span>
                      : <span className="mono text-[11px] text-[var(--color-faint)]">unscored</span>}
                  </td>
                  <td>{p.eudr_covered ? <StatusPill status={p.eudr_determination} /> : <span className="mono text-[11px] text-[var(--color-faint)]">n/a</span>}</td>
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
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono">{label}</div>{children}</label>
}
