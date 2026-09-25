import { useEffect, useMemo, useState } from 'react'
import { Columns3 } from 'lucide-react'
import { api } from '../lib/api'

// Map a customer's own file layout onto our template: which of their columns feeds each of our fields, and whether a
// money column is in thousands/millions or another currency. Saved as a named, versioned mapping
// (services/intake/mapping.py) — every batch records the exact version that produced its values.

export interface Field { name: string; label: string; required?: boolean; kind?: string; description?: string }
export interface SavedMapping {
  profile_id: string; name: string; version: number; column_map: Record<string, string>
  transforms: Record<string, { multiply?: number; currency?: string }>
}
export interface MappingReport {
  profile: string; unmapped_source_columns: string[]; warnings?: string[]
  conversions: { field: string; kind: string; factor?: number; rates?: Record<string, { rate: number; rate_date: string | null }> }[]
}

const SCALES = [{ v: 1, l: 'as is' }, { v: 1e3, l: '× 1,000' }, { v: 1e6, l: '× 1,000,000' }]

export function useTemplateMappings(template?: string) {
  const [fields, setFields] = useState<Field[]>([])
  const [saved, setSaved] = useState<SavedMapping[]>([])
  const reload = async () => {
    if (!template) return
    const [f, m] = await Promise.all([
      api.get<{ fields: Field[] }>(`/v1/intake/templates/${template}/fields`),
      api.get<{ mappings: SavedMapping[] }>(`/v1/intake/mappings?template=${template}`),
    ])
    setFields(f.fields); setSaved(m.mappings)
  }
  useEffect(() => { reload().catch(() => { /* mapping is optional; the template layout still works */ }) }, [template]) // eslint-disable-line react-hooks/exhaustive-deps
  return { fields, saved, reload }
}

export default function MappingEditor({ template, fields, sourceColumns, suggested, base, onSaved, onCancel }: {
  template: string; fields: Field[]; sourceColumns: string[]; suggested?: Record<string, string>; base?: SavedMapping
  onSaved: (profileId: string) => void; onCancel: () => void
}) {
  const [name, setName] = useState(base?.name ?? '')
  const [cmap, setCmap] = useState<Record<string, string>>(() => base?.column_map ?? suggested
    ?? Object.fromEntries(fields.filter(f => sourceColumns.includes(f.name)).map(f => [f.name, f.name])))
  const [tr, setTr] = useState<Record<string, { multiply?: number; currency?: string }>>(() => base?.transforms ?? {})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const used = useMemo(() => new Set(Object.values(cmap).filter(Boolean)), [cmap])
  const missing = fields.filter(f => f.required && !cmap[f.name])
  const setT = (f: string, patch: { multiply?: number; currency?: string }) => setTr(t => {
    const next = { ...(t[f] ?? {}), ...patch }
    if (next.multiply === 1) delete next.multiply
    if (!next.currency || next.currency.toUpperCase() === 'EUR') delete next.currency
    return { ...t, [f]: next }
  })

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const transforms = Object.fromEntries(Object.entries(tr).filter(([f, v]) => cmap[f] && Object.keys(v).length)
        .map(([f, v]) => [f, v.currency ? { ...v, currency: v.currency.toUpperCase() } : v]))
      const r = await api.post<{ profile_id: string }>('/v1/intake/mappings', { template, name, column_map: cmap, transforms })
      onSaved(r.profile_id)
    } catch (e: unknown) {
      setErr((e as { body?: { error?: { message?: string } } })?.body?.error?.message ?? 'The mapping could not be saved.')
    } finally { setBusy(false) }
  }

  return (
    <div className="mt-3 rounded-xl border border-[var(--color-line)] overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 bg-[var(--color-bg-2)] border-b border-[var(--color-line)]">
        <Columns3 size={14} className="text-[var(--color-faint)]" />
        <span className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)]">Map your columns</span>
        <span className="text-[11.5px] text-[var(--color-mute)]">— tell us which of your columns is which. Saved for next time.</span>
      </div>
      <div className="px-4 py-3 space-y-1.5 max-h-[420px] overflow-y-auto">
        {fields.map(f => (
          <div key={f.name} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-2 gap-y-1 items-center text-[12px]">
            <span className="text-[var(--color-ink)] truncate" title={f.description}>{f.label}{f.required && <span style={{ color: 'var(--color-warn)' }}> *</span>}</span>
            <select value={cmap[f.name] ?? ''} onChange={e => setCmap(m => ({ ...m, [f.name]: e.target.value }))}
              className="rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1 text-[12px] text-[var(--color-ink)] min-w-0">
              <option value="">{f.required ? '— choose your column —' : '— not in my file —'}</option>
              {sourceColumns.map(c => <option key={c} value={c} disabled={used.has(c) && cmap[f.name] !== c}>{c}</option>)}
            </select>
            {f.kind === 'money' && cmap[f.name] ? (
              <span className="flex flex-wrap items-center gap-1.5 col-start-2 min-w-0">
                <span className="mono text-[10px] text-[var(--color-faint)]">scale</span>
                <select value={tr[f.name]?.multiply ?? 1} onChange={e => setT(f.name, { multiply: Number(e.target.value) })}
                  className="rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-1.5 py-1 mono text-[11px] text-[var(--color-ink)]">
                  {SCALES.map(s => <option key={s.v} value={s.v}>{s.l}</option>)}
                </select>
                <span className="mono text-[10px] text-[var(--color-faint)]">currency</span>
                <input value={tr[f.name]?.currency ?? 'EUR'} onChange={e => setT(f.name, { currency: e.target.value.slice(0, 3) })} aria-label={`${f.label} currency`}
                  className="w-14 rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-1.5 py-1 mono text-[11px] uppercase text-[var(--color-ink)]" />
              </span>
            ) : null}
          </div>
        ))}
      </div>
      <div className="flex items-end gap-2.5 flex-wrap px-4 py-3 border-t border-[var(--color-line-2)]">
        <label className="text-[11px] text-[var(--color-mute)]">name this mapping (usually the source system)
          <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Core banking export"
            className="block mt-0.5 w-64 rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1.5 text-[12px] text-[var(--color-ink)]" /></label>
        <button onClick={save} disabled={busy || !name.trim() || missing.length > 0}
          className="mono text-[11.5px] px-3.5 py-2 rounded-lg bg-[var(--color-sky)] text-white hover:brightness-110 transition disabled:opacity-45">
          {busy ? 'saving…' : 'Save mapping & check the file'}</button>
        <button onClick={onCancel} className="mono text-[10.5px] text-[var(--color-faint)] hover:text-[var(--color-ink)]">cancel</button>
        {missing.length > 0 && <span className="w-full text-[11.5px]" style={{ color: 'var(--color-warn)' }}>Still to map: {missing.map(f => f.label).join(', ')}</span>}
        {err && <span className="w-full text-[11.5px]" style={{ color: 'var(--color-warn)' }}>{err}</span>}
        <span className="w-full mono text-[9.5px] text-[var(--color-faint)]">Other currencies are converted to EUR at the ECB rate for the book date; if our latest rate is older than a week, a second person must accept it.</span>
      </div>
    </div>
  )
}

export function MappingNote({ report }: { report: MappingReport }) {
  const conv = report.conversions.map(c => c.kind === 'scale' ? `${c.field} × ${c.factor?.toLocaleString()}`
    : c.kind === 'currency' ? `${c.field}: ${Object.entries(c.rates ?? {}).map(([k, r]) => `${k}→EUR ${r.rate} (${r.rate_date})`).join(', ')}` : `${c.field}: your values → ours`)
  return (
    <div className="flex items-start gap-2 px-4 py-2 border-b border-[var(--color-line-2)] text-[12px]">
      <Columns3 size={14} className="mt-0.5 shrink-0 text-[var(--color-faint)]" />
      <div><b className="text-[var(--color-ink)]">Read with your mapping “{report.profile}”</b>
        {conv.length > 0 && <span className="text-[var(--color-mute)]"> — {conv.join(' · ')}</span>}
        {report.unmapped_source_columns.length > 0 && <div className="text-[var(--color-faint)]">Not used: {report.unmapped_source_columns.join(', ')}</div>}
        {report.warnings?.map((w, i) => <div key={i} style={{ color: 'var(--color-warn)' }}>{w}</div>)}</div>
    </div>
  )
}
