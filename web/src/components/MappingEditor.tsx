import { useEffect, useMemo, useState } from 'react'
import { Columns3 } from 'lucide-react'
import { api, upload as uploadFile } from '../lib/api'

// Map a customer's own file layout onto any sector's template. We read the file on the server (CSV or Excel), propose
// which of their columns feeds each field — from the names and the values, with how sure we are — and propose our
// value for each of their values in fixed-list fields. The customer confirms or corrects, and it is saved as a named,
// versioned mapping (services/intake/mapping.py) that remembers this layout: next time the same layout is used
// automatically. Nothing here is sector-specific; it all comes from the field catalogue.

export interface Field { name: string; label: string; required?: boolean; kind?: string; field_kind?: string; description?: string; vocab?: string; allowed?: string[] }
type Transform = { multiply?: number; currency?: string; currency_column?: string; values?: Record<string, string> }
export interface SavedMapping { profile_id: string; name: string; version: number; column_map: Record<string, string>; transforms: Record<string, Transform> }
export interface MappingReport {
  profile: string; auto?: boolean; unmapped_source_columns: string[]; warnings?: string[]
  conversions: { field: string; kind: string; factor?: number; rates?: Record<string, FxUsed> }[]
}
interface FxUsed { rate: number; units_per_eur?: number | null; rate_date: string | null; source: string; basis: string; stale?: boolean; note?: string | null }
const FX_SOURCE: Record<string, string> = { ecb: 'ECB daily', imf: 'IMF month-end', peg: 'fixed by law', seed: 'setup rate', fallback: 'offline fallback' }
const fxText = (ccy: string, r: FxUsed) => `${ccy} ${r.units_per_eur ?? (r.rate ? +(1 / r.rate).toPrecision(6) : '?')} per EUR (${FX_SOURCE[r.source] ?? r.source}${r.rate_date ? `, ${r.rate_date}` : ''})`

interface Proposal { column: string; confidence: 'high' | 'medium' | 'low'; reasons: string[]; transform?: Transform }
interface Inspect {
  columns: string[]; n_rows: number; fields: Field[]
  layout_mapping: { profile_id: string; name: string; version: number } | null
  closest_mapping: (SavedMapping & { overlap: number }) | null
  suggestion: {
    fields: Record<string, Proposal>; columns: Record<string, { samples: string[] }>; hints: Record<string, string[]>
    values: Record<string, Record<string, Record<string, string | null>>>; currency_columns: string[]
  }
}

const SCALES = [{ v: 1, l: 'as is' }, { v: 1e3, l: '× 1,000' }, { v: 1e6, l: '× 1,000,000' }]
const CONF: Record<string, { l: string; c: string }> = {
  high: { l: 'sure', c: 'var(--color-good)' }, medium: { l: 'likely', c: 'var(--color-sky)' }, low: { l: 'check', c: 'var(--color-warn)' },
}
const inputCls = 'rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1 text-[12px] text-[var(--color-ink)] min-w-0'

export function useTemplateMappings(template?: string) {
  const [saved, setSaved] = useState<SavedMapping[]>([])
  const reload = async () => {
    if (!template) return
    setSaved((await api.get<{ mappings: SavedMapping[] }>(`/v1/intake/mappings?template=${template}`)).mappings)
  }
  useEffect(() => { reload().catch(() => { /* mapping is optional; our own layout still works */ }) }, [template]) // eslint-disable-line react-hooks/exhaustive-deps
  return { saved, reload }
}

export default function MappingEditor({ template, file, base, onSaved, onCancel }: {
  template: string; file: File; base?: SavedMapping; onSaved: (profileId: string) => void; onCancel: () => void
}) {
  const [ins, setIns] = useState<Inspect | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [name, setName] = useState(base?.name ?? '')
  const [cmap, setCmap] = useState<Record<string, string>>({})
  const [tr, setTr] = useState<Record<string, Transform>>({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    uploadFile<Inspect>(`/v1/intake/templates/${template}/inspect`, file).then(r => {
      setIns(r)
      const start = base ?? r.closest_mapping ?? null
      const has = new Set(r.columns)
      const proposed = Object.fromEntries(Object.entries(r.suggestion.fields).filter(([, p]) => p.confidence !== 'low').map(([f, p]) => [f, p.column]))
      const fromSaved = start ? Object.fromEntries(Object.entries(start.column_map).filter(([, c]) => has.has(c))) : {}
      setCmap({ ...proposed, ...fromSaved })
      const units = Object.fromEntries(Object.entries(r.suggestion.fields).filter(([, p]) => p.transform).map(([f, p]) => [f, p.transform!]))
      setTr({ ...units, ...(start?.transforms ?? {}) })
      if (!base && r.closest_mapping) setName(r.closest_mapping.name)
    }).catch((e: unknown) => setErr((e as { body?: { error?: { message?: string } } })?.body?.error?.message ?? 'We could not read the file.'))
  }, [template, file, base])

  const fields = ins?.fields ?? []
  const used = useMemo(() => new Set(Object.values(cmap).filter(Boolean)), [cmap])
  const missing = fields.filter(f => f.required && !cmap[f.name])
  const setT = (f: string, patch: Transform) => setTr(t => {
    const next: Transform = { ...(t[f] ?? {}), ...patch }
    if (next.multiply === 1) delete next.multiply
    if (!next.currency || next.currency.toUpperCase() === 'EUR') delete next.currency
    if (!next.currency_column) delete next.currency_column
    return { ...t, [f]: next }
  })
  const valueMatches = (f: Field) => (cmap[f.name] && ins?.suggestion.values[f.name]?.[cmap[f.name]]) || null

  const save = async () => {
    if (!ins) return
    setBusy(true); setErr(null)
    try {
      const transforms = Object.fromEntries(Object.entries(tr).filter(([f, v]) => cmap[f] && Object.keys(v).length)
        .map(([f, v]) => [f, v.currency ? { ...v, currency: v.currency.toUpperCase() } : v]))
      const r = await api.post<{ profile_id: string }>('/v1/intake/mappings', { template, name, column_map: cmap, transforms, source_columns: ins.columns })
      onSaved(r.profile_id)
    } catch (e: unknown) {
      setErr((e as { body?: { error?: { message?: string } } })?.body?.error?.message ?? 'The mapping could not be saved.')
    } finally { setBusy(false) }
  }

  return (
    <div className="mt-3 rounded-xl border border-[var(--color-line)] overflow-hidden">
      <div className="flex items-center gap-2 flex-wrap px-4 py-2.5 bg-[var(--color-bg-2)] border-b border-[var(--color-line)]">
        <Columns3 size={14} className="text-[var(--color-faint)]" />
        <span className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)]">Map your columns</span>
        <span className="text-[11.5px] text-[var(--color-mute)]">— we’ve proposed a match from your column names and values. Check it; it’s used automatically next time.</span>
      </div>
      {!ins && !err && <div className="px-4 py-3 mono text-[11px] text-[var(--color-faint)]">reading your columns…</div>}
      {ins && ins.closest_mapping && !base && <div className="px-4 pt-2 text-[11.5px] text-[var(--color-mute)]">Started from your mapping “{ins.closest_mapping.name}” — {Math.round(ins.closest_mapping.overlap * 100)}% of its columns are still in this file.</div>}
      {ins && (
        <div className="px-4 py-3 space-y-2 max-h-[460px] overflow-y-auto">
          {fields.map(f => {
            const p = ins.suggestion.fields[f.name]
            const col = cmap[f.name]
            const samples = col ? ins.suggestion.columns[col]?.samples ?? [] : []
            const vm = f.vocab ? valueMatches(f) : null
            return (
              <div key={f.name} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-2 gap-y-1 items-start text-[12px]">
                <span className="text-[var(--color-ink)] truncate pt-1" title={f.description}>{f.label}{f.required && <span style={{ color: 'var(--color-warn)' }}> *</span>}</span>
                <span className="flex flex-col gap-1 min-w-0">
                  <span className="flex items-center gap-1.5 min-w-0">
                    <select value={col ?? ''} onChange={e => setCmap(m => ({ ...m, [f.name]: e.target.value }))} className={inputCls + ' flex-1'}>
                      <option value="">{f.required ? '— choose your column —' : '— not in my file —'}</option>
                      {ins.columns.map(c => <option key={c} value={c} disabled={used.has(c) && col !== c}>{c}</option>)}
                    </select>
                    {p && col === p.column && <span className="mono text-[9.5px] px-1.5 py-0.5 rounded-full shrink-0" title={p.reasons.join(' · ')}
                      style={{ color: CONF[p.confidence].c, background: `color-mix(in oklab, ${CONF[p.confidence].c} 14%, transparent)` }}>{CONF[p.confidence].l}</span>}
                  </span>
                  {p && p.confidence === 'low' && col !== p.column && <span className="text-[11px]" style={{ color: 'var(--color-warn)' }}>Maybe “{p.column}”? {p.reasons.slice(1).join('; ')}</span>}
                  {samples.length > 0 && <span className="mono text-[10px] text-[var(--color-faint)] truncate">e.g. {samples.slice(0, 3).join(' · ')}</span>}
                  {f.kind === 'money' && col && (
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="mono text-[10px] text-[var(--color-faint)]">scale</span>
                      <select value={tr[f.name]?.multiply ?? 1} onChange={e => setT(f.name, { multiply: Number(e.target.value) })} className={inputCls}>
                        {SCALES.map(s => <option key={s.v} value={s.v}>{s.l}</option>)}
                      </select>
                      <span className="mono text-[10px] text-[var(--color-faint)]">currency</span>
                      <select value={tr[f.name]?.currency_column ? `col:${tr[f.name]?.currency_column}` : 'fixed'}
                        onChange={e => setT(f.name, e.target.value.startsWith('col:') ? { currency_column: e.target.value.slice(4), currency: undefined } : { currency_column: undefined })} className={inputCls}>
                        <option value="fixed">one currency</option>
                        {ins.columns.filter(c => c !== col).map(c => <option key={c} value={`col:${c}`}>per row, from “{c}”</option>)}
                      </select>
                      {!tr[f.name]?.currency_column && <input value={tr[f.name]?.currency ?? 'EUR'} onChange={e => setT(f.name, { currency: e.target.value.slice(0, 3) })}
                        aria-label={`${f.label} currency`} className={inputCls + ' w-14 mono uppercase'} />}
                      {(ins.suggestion.hints[f.name] ?? []).map((h, i) => <span key={i} className="w-full text-[11px] text-[var(--color-mute)]">{h}</span>)}
                    </span>
                  )}
                </span>
                {vm && <div className="col-span-2"><ValueMap field={f} matches={vm} chosen={tr[f.name]?.values ?? {}}
                  onChange={values => setTr(t => ({ ...t, [f.name]: { ...(t[f.name] ?? {}), values } }))} /></div>}
              </div>
            )
          })}
        </div>
      )}
      <div className="flex items-end gap-2.5 flex-wrap px-4 py-3 border-t border-[var(--color-line-2)]">
        <label className="text-[11px] text-[var(--color-mute)]">name this mapping (usually the source system)
          <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Core banking export" className={inputCls + ' block mt-0.5 w-64 py-1.5'} /></label>
        <button onClick={save} disabled={busy || !ins || !name.trim() || missing.length > 0}
          className="mono text-[11.5px] px-3.5 py-2 rounded-lg bg-[var(--color-sky)] text-white hover:brightness-110 transition disabled:opacity-45">
          {busy ? 'saving…' : 'Save mapping & check the file'}</button>
        <button onClick={onCancel} className="mono text-[10.5px] text-[var(--color-faint)] hover:text-[var(--color-ink)]">cancel</button>
        {ins && missing.length > 0 && <span className="w-full text-[11.5px]" style={{ color: 'var(--color-warn)' }}>Still to map: {missing.map(f => f.label).join(', ')}</span>}
        {err && <span className="w-full text-[11.5px]" style={{ color: 'var(--color-warn)' }}>{err}</span>}
        <span className="w-full mono text-[9.5px] text-[var(--color-faint)]">Other currencies are converted to EUR at the official rate for the book date — ECB daily, a rate fixed by law, or the IMF month-end for currencies the ECB doesn’t quote. A rate too old for its source goes to a second person.</span>
      </div>
    </div>
  )
}

// Their values in a fixed-list field → ours. Exact equivalents are matched for them; anything else they choose (or
// leave blank on purpose). Only their explicit choices are saved on the mapping.
function ValueMap({ field, matches, chosen, onChange }: {
  field: Field; matches: Record<string, string | null>; chosen: Record<string, string>; onChange: (v: Record<string, string>) => void
}) {
  const theirs = Object.keys(matches)
  const open = theirs.filter(v => matches[v] == null)
  return (
    <details className="rounded-md border border-[var(--color-line-2)] px-2 py-1.5" open={open.some(v => !(v in chosen))}>
      <summary className="cursor-pointer text-[11px] text-[var(--color-mute)]">
        values: {theirs.length - open.length} of {theirs.length} match ours{open.length ? <span style={{ color: 'var(--color-warn)' }}> · {open.length} to map</span> : ''}</summary>
      <div className="mt-1.5 space-y-1">
        {theirs.map(v => (
          <div key={v} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-2 items-center">
            <span className="mono text-[11px] text-[var(--color-ink)] truncate">{v}</span>
            {matches[v] != null && !(v in chosen)
              ? <span className="mono text-[11px] text-[var(--color-good)] truncate">→ {matches[v]}</span>
              : <select value={chosen[v] ?? '__unset'} onChange={e => { const n = { ...chosen }; if (e.target.value === '__unset') delete n[v]; else n[v] = e.target.value; onChange(n) }} className={inputCls}>
                  <option value="__unset">— not mapped (left blank, flagged) —</option>
                  <option value="">leave blank on purpose</option>
                  {(field.allowed ?? []).map(a => <option key={a} value={a}>{a}</option>)}
                </select>}
          </div>
        ))}
      </div>
    </details>
  )
}

export function MappingNote({ report }: { report: MappingReport }) {
  const conv = report.conversions.map(c => c.kind === 'scale' ? `${c.field} × ${c.factor?.toLocaleString()}`
    : c.kind === 'currency' ? `${c.field}: ${Object.entries(c.rates ?? {}).map(([k, r]) => fxText(k, r)).join(', ')}` : `${c.field}: your values → ours`)
  return (
    <div className="flex items-start gap-2 px-4 py-2 border-b border-[var(--color-line-2)] text-[12px]">
      <Columns3 size={14} className="mt-0.5 shrink-0 text-[var(--color-faint)]" />
      <div><b className="text-[var(--color-ink)]">Read with your mapping “{report.profile}”</b>{report.auto && <span className="text-[var(--color-mute)]"> — used automatically: same layout as last time</span>}
        {conv.length > 0 && <span className="text-[var(--color-mute)]"> — {conv.join(' · ')}</span>}
        {report.unmapped_source_columns.length > 0 && <div className="text-[var(--color-faint)]">Not used: {report.unmapped_source_columns.join(', ')}</div>}
        {report.warnings?.map((w, i) => <div key={i} style={{ color: 'var(--color-warn)' }}>{w}</div>)}</div>
    </div>
  )
}
