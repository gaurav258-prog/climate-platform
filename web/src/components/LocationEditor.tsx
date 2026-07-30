import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Pencil, Trash2, X } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Button } from './ui'

type Field = { key: string; label: string; type: 'text' | 'number' | 'select'; options?: string[]; material?: boolean }

const SITE_TYPES = ['hq', 'factory', 'warehouse', 'distribution_centre', 'office', 'other']
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'

// which fields are editable per kind (material ones are flagged so the user knows they may need approval)
const SITE_FIELDS: Field[] = [
  { key: 'name', label: 'Name', type: 'text' },
  { key: 'site_type', label: 'Type', type: 'select', options: SITE_TYPES },
  { key: 'country', label: 'Country', type: 'text' },
  { key: 'region', label: 'Region', type: 'text' },
  { key: 'annual_value_eur', label: 'Asset value €', type: 'number', material: true },
  { key: 'annual_throughput_eur', label: 'Throughput €', type: 'number', material: true },
  { key: 'latitude', label: 'Latitude', type: 'number', material: true },
  { key: 'longitude', label: 'Longitude', type: 'number', material: true },
]
const PLOT_FIELDS: Field[] = [
  { key: 'plot_name', label: 'Plot name', type: 'text' },
  { key: 'commodity', label: 'Commodity', type: 'select' },
  { key: 'country', label: 'Country', type: 'text' },
  { key: 'region', label: 'Region', type: 'text' },
  { key: 'annual_spend_eur', label: 'Annual spend €', type: 'number', material: true },
  { key: 'plot_area_ha', label: 'Area (ha)', type: 'number' },
  { key: 'latitude', label: 'Latitude', type: 'number', material: true },
  { key: 'longitude', label: 'Longitude', type: 'number', material: true },
]

// map the detail record's own keys → the API's field keys for prefilling
function initial(kind: 'site' | 'plot', rec: Record<string, unknown>): Record<string, string> {
  const g = (k: string) => rec[k] == null ? '' : String(rec[k])
  if (kind === 'site') return {
    name: g('name'), site_type: g('site_type'), country: g('country'), region: g('region'),
    annual_value_eur: g('value_eur'), annual_throughput_eur: g('throughput_eur'), latitude: g('lat'), longitude: g('lon'),
  }
  return {
    plot_name: g('plot_name'), commodity: g('commodity'), country: g('country'), region: g('region'),
    annual_spend_eur: g('spend_eur'), plot_area_ha: g('plot_area_ha'), latitude: g('lat'), longitude: g('lon'),
  }
}

export default function LocationEditor({ kind, id, record, onChanged }:
  { kind: 'site' | 'plot'; id: string; record: Record<string, unknown>; onChanged: () => void }) {
  const { profile } = useAuth()
  const nav = useNavigate()
  const canWrite = profile?.permissions?.includes('supply.locations.write')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'pending' | 'err' } | null>(null)
  const base = initial(kind, record)
  const [form, setForm] = useState<Record<string, string>>(base)
  const cq = useQuery({ queryKey: ['commodities'], queryFn: () => api.get<{ commodities: { name: string }[] }>('/v1/supply/commodities'), enabled: kind === 'plot' })
  const fields = kind === 'site' ? SITE_FIELDS : PLOT_FIELDS

  if (!canWrite) return null

  const result = (r: { status: string }) => {
    if (r.status === 'pending') setMsg({ text: 'Submitted for approval — a second approver must clear this change (4-eyes). It is not applied yet.', tone: 'pending' })
    else setMsg({ text: '✓ Change applied and audited.', tone: 'ok' })
  }
  const err = (e: unknown) => setMsg({ text: (e as { body?: { detail?: { message?: string } } })?.body?.detail?.message || 'Could not save.', tone: 'err' })

  const save = async () => {
    // send only CHANGED fields, so a rename doesn't trip the material-edit approval rule
    const changes: Record<string, string | number> = {}
    for (const f of fields) {
      const v = (form[f.key] ?? '').trim()
      if (v !== (base[f.key] ?? '').trim()) changes[f.key] = f.type === 'number' ? Number(v) : v
    }
    if (Object.keys(changes).length === 0) { setMsg({ text: 'No changes to save.', tone: 'err' }); return }
    setBusy(true); setMsg(null)
    try {
      const r = await api.patch<{ status: string }>(`/v1/supply/${kind}/${id}`, changes)
      result(r); setOpen(false)
      if (r.status !== 'pending') onChanged()
    } catch (e) { err(e) } finally { setBusy(false) }
  }

  const del = async () => {
    if (!confirm(`Delete this ${kind}? Depending on your approval matrix this may require a second approver.`)) return
    setBusy(true); setMsg(null)
    try {
      const r = await api.del<{ status: string }>(`/v1/supply/${kind}/${id}`)
      if (r.status === 'pending') result(r)
      else { setMsg({ text: '✓ Deleted and audited.', tone: 'ok' }); setTimeout(() => nav(kind === 'site' ? '/operations' : '/sourcing'), 900) }
    } catch (e) { err(e) } finally { setBusy(false) }
  }

  return (
    <div className="w-full">
      <div className="flex items-center gap-2">
        <button onClick={() => { setOpen(o => !o); setForm(base); setMsg(null) }}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[13px] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition">
          {open ? <X size={14} /> : <Pencil size={14} />} {open ? 'Cancel' : 'Edit'}
        </button>
        <button onClick={del} disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[13px] text-[var(--color-mute)] hover:border-[var(--color-bad)] hover:text-[var(--color-bad)] transition">
          <Trash2 size={14} /> Delete
        </button>
      </div>

      {msg && <div className={`mt-2 text-[12.5px] font-medium ${msg.tone === 'ok' ? 'text-[var(--color-good)]' : msg.tone === 'pending' ? 'text-[var(--color-warn)]' : 'text-[var(--color-bad)]'}`}>{msg.text}</div>}

      {open && (
        <div className="mt-3 rounded-xl border border-[var(--color-line-2)] p-4 bg-[var(--color-panel)]">
          <div className="grid sm:grid-cols-2 gap-3">
            {fields.map(f => (
              <label key={f.key} className="block">
                <div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono flex items-center gap-1.5">
                  {f.label}{f.material && <span className="text-[var(--color-warn)] normal-case tracking-normal">· needs approval</span>}
                </div>
                {f.type === 'select'
                  ? <select className={inp} value={form[f.key] ?? ''} onChange={e => setForm({ ...form, [f.key]: e.target.value })}>
                      {(f.options ?? (cq.data?.commodities ?? []).map(c => c.name)).map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  : <input className={inp} value={form[f.key] ?? ''} inputMode={f.type === 'number' ? 'decimal' : undefined}
                      onChange={e => setForm({ ...form, [f.key]: e.target.value })} />}
              </label>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</Button>
            <span className="text-[11px] text-[var(--color-faint)]">Material edits (coordinates, value/spend) go to 4-eyes approval; the rest apply directly. Everything is audited.</span>
          </div>
        </div>
      )}
    </div>
  )
}
