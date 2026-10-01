import { useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, Factory, Warehouse, Boxes, Building, MapPin, Plus, AlertTriangle, Coins, Activity } from 'lucide-react'
import { api } from '../lib/api'
import MoneyDeclaration from '../components/MoneyDeclaration'
import ValidatedUpload from '../components/ValidatedUpload'
import { useAuth } from '../lib/auth'
import { Card, Button, ExportButton, PageHeader, HeroBanner, SectionHead } from '../components/ui'
import { downloadCsv } from '../lib/export'
import { hazardLabel, bucketLabel, sevColor } from '../lib/hazards'
import MethodGap from '../components/MethodGap'
import { BookWithMap, severityHex } from '../components/SiteMap'
import AddressAutocomplete, { type Place } from '../components/AddressAutocomplete'
import SectionTabs, { DATA_TABS } from '../components/SectionTabs'
import { balance, flow } from '../lib/money'
import { pressable } from '../lib/pressable'

interface Site {
  site_id: string; name: string; site_type: string; lat: number | null; lon: number | null
  country: string | null; value_eur: number | null; throughput_eur: number | null; bi_at_risk_eur: number | null
  top_hazard: string | null; hazard_score: number | null; bucket: string | null; bi_gap?: string
}
interface Totals { asset_value_eur: number; throughput_eur: number; bi_at_risk_eur: number | null; n_elevated: number | null; at_risk_level: number | null }
interface SitesResp { sites: Site[]; site_types: string[]; totals: Totals; bi_note: string; gap?: string }

// colour by the platform's one score band (core.types), not a scale of this page's own
const hz = (s: number | null) => s == null ? 'var(--color-faint)' : sevColor(s)
const pretty = hazardLabel
const typeLabel = (t: string) => t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
const TypeIcon = ({ t }: { t: string }) => {
  const I = t === 'hq' ? Building2 : t === 'factory' ? Factory : t === 'warehouse' ? Warehouse
    : t === 'distribution_centre' ? Boxes : t === 'office' ? Building : MapPin
  return <I size={15} className="text-[var(--color-sky)]" />
}

export default function Operations() {
  const { profile } = useAuth()
  const q = useQuery({ queryKey: ['sites'], queryFn: () => api.get<SitesResp>('/v1/supply/sites') })
  const EMPTY = { name: '', site_type: 'factory', address: '', latitude: '', longitude: '', annual_value_eur: '', annual_throughput_eur: '', area_ha: '', held_from: '', entity_id: '' }
  const [form, setForm] = useState(EMPTY)
  // the organisation's legal entities: which one holds a site (none set up → the organisation itself)
  const ents = useQuery({ queryKey: ['filing-entities'], queryFn: () => api.get<{ entities: { entity_id: string; name: string; kind: string }[] }>('/v1/filings/entities') })
  const holders = (ents.data?.entities ?? []).filter(e => e.kind !== 'group')
  const [ccy, setCcy] = useState('')
  const [bookDate, setBookDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'err' } | null>(null)
  const [sel, setSel] = useState<string | null>(null)   // the site ringed on the map
  const [nameErr, setNameErr] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)
  const [chosen, setChosen] = useState<Place | null>(null)
  const hasCoords = form.latitude.trim() !== '' && form.longitude.trim() !== ''

  const add = async () => {
    if (!form.name.trim()) { setNameErr(true); nameRef.current?.focus(); setMsg({ text: 'Give the site a name first (e.g. "Frankfurt DC").', tone: 'err' }); return }
    const useChosen = chosen && !hasCoords
    if (!hasCoords && !chosen && form.address.trim()) { setMsg({ text: 'Pick the matching place from the list, or enter coordinates.', tone: 'err' }); return }
    if (!hasCoords && !chosen && !form.address.trim()) { setMsg({ text: 'Search an address and pick a place, or enter coordinates.', tone: 'err' }); return }
    if ((form.annual_value_eur || form.annual_throughput_eur) && (!ccy || !bookDate)) { setMsg({ text: 'Choose the currency of the amounts and the date they describe.', tone: 'err' }); return }
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
        currency: ccy || null, book_date: bookDate || null,
        area_ha: form.area_ha ? Number(form.area_ha) : null, held_from: form.held_from || null, entity_id: form.entity_id || null,
      })
      const where = useChosen ? chosen!.display_name : `${r.site.lat.toFixed(3)}, ${r.site.lon.toFixed(3)}`
      setMsg({ text: `✓ Added "${form.name.trim()}" at ${where}. Scoring on the live hazard grid — it'll appear in the table shortly (a new region may take a moment).`, tone: 'ok' })
      setForm(EMPTY)
      setChosen(null)
      await q.refetch()
    } catch (e) {
      setMsg({ text: (e as { body?: { detail?: { message?: string }; error?: { message?: string } } })?.body?.error?.message || (e as { body?: { detail?: { message?: string } } })?.body?.detail?.message
        || 'Could not add — pick a place or enter coordinates.', tone: 'err' })
    } finally { setBusy(false) }
  }

  const sites = q.data?.sites ?? []
  const types = q.data?.site_types ?? ['hq', 'factory', 'warehouse', 'distribution_centre', 'office', 'other']
  const t = q.data?.totals
  const highN = t?.n_elevated ?? null

  const exportSites = () => downloadCsv('tellumen-operational-sites',
    [{ key: 'name', label: 'Site' }, { key: 'type', label: 'Type' }, { key: 'country', label: 'Country' },
     { key: 'lat', label: 'Lat' }, { key: 'lon', label: 'Lon' }, { key: 'value', label: 'Asset value (EUR)' },
     { key: 'throughput', label: 'Throughput (EUR)' }, { key: 'bi', label: 'BI exposure (EUR)' },
     { key: 'hazard', label: 'Worst hazard' }, { key: 'score', label: 'Score' }, { key: 'bucket', label: 'Severity' }],
    sites.map(s => ({
      name: s.name, type: typeLabel(s.site_type), country: s.country ?? '', lat: s.lat ?? '', lon: s.lon ?? '',
      value: s.value_eur ?? '', throughput: s.throughput_eur ?? '', bi: s.bi_at_risk_eur ?? '',
      hazard: s.top_hazard ? hazardLabel(s.top_hazard) : '', score: s.hazard_score ?? '', bucket: s.bucket ? bucketLabel(s.bucket) : '',
    })),
    { title: 'Operational sites', org: profile?.org?.name })

  return (
    <div className="fadeup space-y-7">
      <SectionTabs tabs={DATA_TABS} />
      <PageHeader eyebrow="Agriculture · your operations" title="Operations"
        lead="Your own sites — head office, plants, cold stores, distribution centres — geolocated and scored on the same live hazard data as your suppliers. Add a site by address or coordinates and it's on the map in seconds."
        actions={sites.length > 0 ? <ExportButton onExport={exportSites} /> : undefined} />

      <HeroBanner
        eyebrow="Your operations"
        title={highN == null ? 'Your at-risk level is not stated.' : highN > 0 ? 'Some sites sit at or above your at-risk level.' : 'No site is at or above your at-risk level.'}
        lead="Your own sites on the same live hazard data as your suppliers — damage and business-interruption exposure, priced."
        stat={[
          { label: 'operational sites', value: sites.length, icon: Building2, tone: 'var(--color-sky)' },
          { label: t?.at_risk_level != null ? `at or above your level (≥${t.at_risk_level})` : 'at risk — level not stated', value: highN ?? '—', icon: AlertTriangle, tone: highN ? '#E8853C' : undefined },
          { label: 'asset value (damage exposure)', value: balance(t?.asset_value_eur), icon: Coins },
          { label: 'business-interruption exposure', value: t?.bi_at_risk_eur == null ? 'not stated' : flow(t.bi_at_risk_eur), icon: Activity, tone: (t?.bi_at_risk_eur ?? 0) > 0 ? '#E8853C' : undefined },
        ]} />
      <div className="text-[11px] text-[var(--color-faint)] -mt-3">{q.data?.bi_note}</div>
      {q.data?.gap && <MethodGap gap={q.data.gap} what="Operations at risk" />}

      {/* add a site */}
      <Card className="p-5">
        <SectionHead icon={Plus} className="mb-3">Add a site</SectionHead>
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
          <div className="col-span-full"><MoneyDeclaration currency={ccy} setCurrency={setCcy} bookDate={bookDate} setBookDate={setBookDate}
            note="Needed when you give an asset value or throughput (here or in the CSV — a row's currency / book_date columns override these). Asset value converts at the book date's rate; throughput (a yearly figure) at the average of the 12 months to it." /></div>
          <Field label="Asset value (PP&E + stock)"><input className={inp} value={form.annual_value_eur} onChange={e => setForm({ ...form, annual_value_eur: e.target.value })} placeholder="85000000" inputMode="numeric" /></Field>
          <Field label="Annual throughput (revenue)"><input className={inp} value={form.annual_throughput_eur} onChange={e => setForm({ ...form, annual_throughput_eur: e.target.value })} placeholder="210000000" inputMode="numeric" /></Field>
          <Field label="Latitude"><input className={inp} value={form.latitude} onChange={e => setForm({ ...form, latitude: e.target.value })} placeholder="37.39" inputMode="decimal" /></Field>
          <Field label="Longitude"><input className={inp} value={form.longitude} onChange={e => setForm({ ...form, longitude: e.target.value })} placeholder="-5.98" inputMode="decimal" /></Field>
          <Field label="Site area (ha)"><input className={inp} value={form.area_ha} onChange={e => setForm({ ...form, area_ha: e.target.value })} placeholder="12.5" inputMode="decimal" /></Field>
          <Field label="Held since"><input type="date" className={inp} value={form.held_from} onChange={e => setForm({ ...form, held_from: e.target.value })} /></Field>
          {holders.length > 1 && <Field label="Held by (legal entity)">
            <select className={inp} value={form.entity_id} onChange={e => setForm({ ...form, entity_id: e.target.value })}>
              <option value="">— choose —</option>
              {holders.map(e => <option key={e.entity_id} value={e.entity_id}>{e.name}</option>)}
            </select></Field>}
          <div className="flex items-end"><Button onClick={add} disabled={busy}>{busy ? 'Adding…' : 'Add & score'}</Button></div>
        </div>
        <div className="mt-4 pt-4 border-t border-[var(--color-line)]">
          <ValidatedUpload dropLabel="sites file" accept=".csv,.xlsx" template="company_sites" onDone={() => q.refetch()}
            intro={<>Bulk-add or update sites from a file. Every file is inspected and every row checked <b className="text-[var(--color-ink)]">before</b> anything is saved; rows with your own site ID update that site; if a check fails, a second person approves before import.</>}
            endpoints={{ validate: '/v1/supply/sites/validate', upload: '/v1/supply/sites/upload', template: '/v1/supply/sites/template.xlsx', templateFile: 'company_sites_template.xlsx' }}
            renderDone={r => <>{Number(r.n_uploaded) || 0} site{Number(r.n_uploaded) === 1 ? '' : 's'} in your book.</>} />
        </div>
        <div className="mt-4 pt-4 border-t border-[var(--color-line)]">
          <ValidatedUpload dropLabel="year-end values file" accept=".csv,.xlsx" template="site_year_end_values" onDone={() => q.refetch()}
            intro={<>Finance's <b className="text-[var(--color-ink)]">year-end figures per site</b>: the carrying amount at the period end (converted at that day's closing rate) and the year's net revenue (at the year's average rate). Each value is kept as a dated statement; a closed period is corrected only by a restatement with its reason, approved by a second person.</>}
            endpoints={{ validate: '/v1/supply/sites/year-end/validate', upload: '/v1/supply/sites/year-end/upload', template: '/v1/supply/sites/year-end/template.xlsx', templateFile: 'site_year_end_values_template.xlsx' }}
            renderDone={r => <>{Number(r.n_uploaded) || 0} site-period value{Number(r.n_uploaded) === 1 ? '' : 's'} recorded.</>} />
        </div>
        {msg && <div className={`mt-3 text-[12.5px] font-medium ${msg.tone === 'ok' ? 'text-[var(--color-good)]' : 'text-[var(--color-warn)]'}`}>{msg.text}</div>}
      </Card>

      {/* sites table */}
      <Card className="p-5">
        {q.isLoading ? <div className="py-8 text-center text-[var(--color-faint)] text-sm">loading…</div> :
          sites.length === 0 ? <div className="py-8 text-center text-[var(--color-faint)] text-sm">No sites yet — add your first above.</div> : (
            <BookWithMap color={severityHex} selectedId={sel} onSelect={(id) => setSel(prev => (prev === id ? null : id))}
              points={sites.map(s => ({ id: s.site_id, name: s.name, lat: s.lat as number, lon: s.lon as number, score: s.hazard_score,
                                        sub: [s.country, typeLabel(s.site_type)].filter(Boolean).join(' · '), value: balance(s.value_eur) }))}>
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
                    <tr key={s.site_id} {...pressable(() => setSel(prev => (prev === s.site_id ? null : s.site_id)), { row: true, expanded: sel === s.site_id })}
                      className={`border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-panel)] transition ${sel === s.site_id ? 'bg-[var(--color-panel)]' : ''}`}>
                      <td className="py-2 pr-3 text-[var(--color-ink)]">
                        <a href={`/detail/site/${s.site_id}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                           className="hover:text-[var(--color-sky)] hover:underline" title="Open the site's full detail">{s.name}</a>
                      </td>
                      <td className="pr-3"><span className="inline-flex items-center gap-1.5 text-[var(--color-mute)]"><TypeIcon t={s.site_type} />{typeLabel(s.site_type)}</span></td>
                      <td className="pr-3 mono text-[11px] text-[var(--color-mute)]">{s.country ?? '—'} · {s.lat?.toFixed(2)}, {s.lon?.toFixed(2)}</td>
                      <td className="pr-3 text-right mono text-[var(--color-mute)]">{balance(s.value_eur)}</td>
                      <td className="pr-3 text-right mono text-[var(--color-mute)]">{flow(s.throughput_eur)}</td>
                      <td className="pr-3 text-right mono" style={{ color: s.bi_at_risk_eur ? 'var(--color-warn)' : 'var(--color-faint)' }}>{s.bi_at_risk_eur ? flow(s.bi_at_risk_eur) : '—'}</td>
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
            </BookWithMap>
          )}
      </Card>
    </div>
  )
}

const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono">{label}</div>{children}</label>
}
