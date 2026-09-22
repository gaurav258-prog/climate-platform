import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, FileSpreadsheet, Check } from 'lucide-react'
import { api, ApiError, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, SectionHead } from './ui'

// Two write actions on a fund: onboard holdings by ISIN (the golden source resolves + locates + value-weights
// each one), and choose the voluntary PAI indicators the fund adopts (≥1 environmental + ≥1 social).

// Minimal RFC-4180-ish CSV parser (handles quoted fields + escaped quotes) — the holdings endpoint takes
// JSON, so we parse the template CSV client-side rather than shipping a half-broken split(',').
function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = []; let cur: string[] = [], field = '', inQ = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (inQ) { if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++ } else inQ = false } else field += c }
    else if (c === '"') inQ = true
    else if (c === ',') { cur.push(field); field = '' }
    else if (c === '\n' || c === '\r') { if (field !== '' || cur.length) { cur.push(field); rows.push(cur); cur = []; field = '' } if (c === '\r' && text[i + 1] === '\n') i++ }
    else field += c
  }
  if (field !== '' || cur.length) { cur.push(field); rows.push(cur) }
  if (!rows.length) return []
  const header = rows[0].map(h => h.trim())
  return rows.slice(1).filter(r => r.some(c => c.trim() !== '')).map(r => { const o: Record<string, string> = {}; header.forEach((h, i) => o[h] = (r[i] ?? '').trim()); return o })
}
function coerce(v: string): string | number | boolean | undefined {
  if (v === '') return undefined
  if (v === 'true' || v === 'false') return v === 'true'
  const n = Number(v)
  return v.trim() !== '' && isFinite(n) ? n : v
}

interface OnboardResp { holdings_submitted: number; distinct_isins: number; positions_created: number
  coverage: { matched: number; match_rate_pct: number; unmatched: string[] }; note?: string; error?: string }

export function OnboardHoldings({ fundId, onDone }: { fundId: string; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<OnboardResp | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const send = async (file: File) => {
    setBusy(true); setErr(null); setRes(null)
    try {
      const rows = parseCsv(await file.text())
      if (!rows.length) { setErr('The CSV had no data rows.'); return }
      const holdings = rows.map(r => { const o: Record<string, unknown> = {}; for (const k in r) { const c = coerce(r[k]); if (c !== undefined) o[k] = c } return o }).filter(h => h.isin)
      if (!holdings.length) { setErr('No rows had an ISIN.'); return }
      const r = await api.post<OnboardResp>(`/v1/funds/${fundId}/holdings`, { holdings })
      if (r.error) { setErr(r.error); return }
      setRes(r); onDone()
    } catch (e) { setErr(e instanceof ApiError ? String(e.body ?? e.message) : 'Could not onboard the holdings.') }
    finally { setBusy(false) }
  }

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Onboard holdings by ISIN</div>
        <button onClick={() => setOpen(o => !o)} className="mono text-[11px] text-[var(--color-sky)] hover:underline">{open ? 'close' : 'add holdings'}</button>
      </div>
      {open && (
        <div className="mt-3 space-y-2">
          <p className="text-[12px] text-[var(--color-mute)]">Upload a CSV of ISINs (+ market value). Each is resolved to its issuer, located on our hexagonal grid and value-weighted into the fund — filling the SFDR statement automatically. Start from the template.</p>
          {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}
          {res && (
            <div className="text-[12px] text-[var(--color-good)]">
              Onboarded {res.positions_created} position{res.positions_created === 1 ? '' : 's'} · {res.coverage.matched}/{res.distinct_isins} ISINs matched ({Math.round(res.coverage.match_rate_pct)}%).
              {res.coverage.unmatched?.length ? <span className="text-[var(--color-warn)]"> Unmatched: {res.coverage.unmatched.slice(0, 6).join(', ')}{res.coverage.unmatched.length > 6 ? '…' : ''}</span> : null}
            </div>
          )}
          <div className="flex items-center gap-3">
            <label className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-medium cursor-pointer transition ${busy ? 'bg-[var(--color-panel)] text-[var(--color-faint)]' : 'bg-[var(--color-sky)] text-[#08111f] hover:bg-[var(--color-blue)]'}`}>
              <Upload size={14} /> {busy ? 'onboarding…' : 'Upload CSV'}
              <input type="file" accept=".csv" className="hidden" disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) send(f); e.target.value = '' }} />
            </label>
            <button onClick={() => download('/v1/holdings/template.csv', 'tellumen_holdings_template.csv').catch(() => toast.error('Could not download the template.'))}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-4 py-2 text-[13px] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={14} /> Template</button>
          </div>
        </div>
      )}
    </Card>
  )
}

interface Cat { key: string; table: string; kind: string; name: string; unit: string }
export function VoluntaryPai({ fundId, selected, onDone }: { fundId: string; selected: string[]; onDone: () => void }) {
  const qc = useQueryClient()
  const cat = useQuery({ queryKey: ['vpai-catalog'], queryFn: () => api.get<{ indicators: Cat[] }>('/v1/voluntary-pai/catalog') })
  const [open, setOpen] = useState(false)
  const [sel, setSel] = useState<string[]>(selected)
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null); const [ok, setOk] = useState(false)
  const inds = cat.data?.indicators ?? []
  const env = inds.filter(i => i.kind === 'environmental'), soc = inds.filter(i => i.kind === 'social')
  const toggle = (k: string) => setSel(s => s.includes(k) ? s.filter(x => x !== k) : [...s, k])
  const nEnv = sel.filter(k => env.some(e => e.key === k)).length
  const nSoc = sel.filter(k => soc.some(e => e.key === k)).length

  const save = async () => {
    setBusy(true); setErr(null); setOk(false)
    try {
      const r = await api.put<{ error?: string }>(`/v1/funds/${fundId}/voluntary-pai`, { indicator_keys: sel })
      if (r.error) { setErr(r.error); return }
      setOk(true); qc.invalidateQueries({ queryKey: ['fund-sfdr', fundId] }); onDone()
    } catch (e) { setErr(e instanceof ApiError ? String(e.body ?? e.message) : 'Could not save.') }
    finally { setBusy(false) }
  }

  const group = (title: string, list: Cat[]) => (
    <div>
      <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1">{title}</div>
      <div className="space-y-1">
        {list.map(i => (
          <label key={i.key} className="flex items-start gap-2 text-[12px] cursor-pointer">
            <input type="checkbox" checked={sel.includes(i.key)} onChange={() => toggle(i.key)} className="mt-0.5" />
            <span className="text-[var(--color-mute)]">{i.name} <span className="text-[var(--color-faint)] mono text-[10px]">{i.unit}</span></span>
          </label>
        ))}
      </div>
    </div>
  )

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Voluntary PAI indicators <span className="text-[var(--color-mute)]">· {selected.length} adopted</span></div>
        <button onClick={() => { setSel(selected); setOpen(o => !o); setOk(false); setErr(null) }} className="mono text-[11px] text-[var(--color-sky)] hover:underline">{open ? 'close' : 'choose'}</button>
      </div>
      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-[11.5px] text-[var(--color-mute)]">SFDR requires adopting at least one additional environmental and one additional social indicator (RTS Tables 2 &amp; 3).</p>
          {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}
          {ok && <div className="text-[12px] text-[var(--color-good)] inline-flex items-center gap-1"><Check size={13} /> Saved.</div>}
          <div className="grid sm:grid-cols-2 gap-4">{group('Environmental', env)}{group('Social', soc)}</div>
          <div className="flex items-center gap-3">
            <Button variant="primary" onClick={save} disabled={busy || nEnv < 1 || nSoc < 1}>Save selection</Button>
            <span className="mono text-[10.5px]" style={{ color: nEnv >= 1 && nSoc >= 1 ? 'var(--color-good)' : 'var(--color-faint)' }}>{nEnv} env · {nSoc} social</span>
          </div>
        </div>
      )}
    </Card>
  )
}

// SFDR Article 8/9 pre-contractual disclosure (RTS Annex II/III) — the template that must be annexed to
// the fund's prospectus, distinct from both the PAI statement (backward, mandatory) and the periodic
// report. Assembled server-side (ml/regulatory/sfdr_precontractual.py) as a list of sections, each
// computed from the golden source, manager-declared, or an honest gap. Rendered generically here —
// driven entirely by each section's `key`/`keys` (the funds.sfdr_precontractual JSONB field name(s) the
// PUT endpoint accepts) — rather than one hand-written form per field, so the frontend never drifts from
// the Python source of truth as fields are added.
interface PCField {
  field: string; status: string; value: unknown; source?: string | null
  input_required?: string | null; note?: string | null
  key?: string | null; keys?: string[] | null
}
interface PCResp {
  error?: string; template?: string
  sections?: PCField[]
  coverage_summary?: { fields: number; computed: number; declared: number; not_available: number; note: string }
}

const PC_STATUS: Record<string, { c: string; label: string }> = {
  computed: { c: '#34d399', label: 'computed' },
  declared: { c: '#5cc8ff', label: 'declared' },
  not_available: { c: '#fb7185', label: 'not available' },
  not_applicable: { c: '#64748b', label: 'n/a' },
}

function renderPCValue(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (typeof v === 'string' || typeof v === 'number') return String(v)
  if (Array.isArray(v)) return v.length ? v.map(x => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join(', ') : '—'
  if (typeof v === 'object') {
    const parts = Object.entries(v as Record<string, unknown>)
      .filter(([, x]) => x != null && x !== '')
      .map(([k, x]) => `${k.replace(/_/g, ' ')}: ${typeof x === 'object' ? JSON.stringify(x) : String(x)}`)
    return parts.length ? parts.join(' · ') : '—'
  }
  return String(v)
}

function PCFieldInput({ fieldKey, value, onChange }: { fieldKey: string; value: string; onChange: (v: string) => void }) {
  const label = fieldKey.replace(/_/g, ' ')
  if (fieldKey === 'makes_sustainable_investments') return (
    <select value={value} onChange={e => onChange(e.target.value)} className="block w-full mt-0.5 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]">
      <option value="">— {label} —</option><option value="true">Yes</option><option value="false">No</option>
    </select>
  )
  if (fieldKey === 'taxonomy_kpi_basis') return (
    <select value={value} onChange={e => onChange(e.target.value)} className="block w-full mt-0.5 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]">
      <option value="">— basis (default turnover) —</option><option value="turnover">Turnover</option><option value="capex">CapEx</option><option value="opex">OpEx</option>
    </select>
  )
  if (fieldKey.endsWith('_pct')) return (
    <input type="number" min={0} max={100} step="0.1" placeholder={label} value={value} onChange={e => onChange(e.target.value)}
      className="block w-full mt-0.5 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]" />
  )
  if (fieldKey.endsWith('_url') || fieldKey.endsWith('_name')) return (
    <input type="text" placeholder={label} value={value} onChange={e => onChange(e.target.value)}
      className="block w-full mt-0.5 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]" />
  )
  return (
    <textarea placeholder={label} rows={3} value={value} onChange={e => onChange(e.target.value)}
      className="block w-full mt-0.5 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]" />
  )
}

export function PrecontractualDisclosure({ fundId, onDone }: { fundId: string; onDone: () => void }) {
  const qc = useQueryClient()
  const pc = useQuery({ queryKey: ['fund-precontractual', fundId], queryFn: () => api.get<PCResp>(`/v1/funds/${fundId}/precontractual`) })
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const data = pc.data
  if (pc.isLoading || !data || data.error) return null
  const sections = data.sections ?? []
  const cov = data.coverage_summary

  const editKeysOf = (s: PCField): string[] => (s.keys && s.keys.length ? s.keys : s.key ? [s.key] : [])

  const startEdit = (s: PCField) => {
    const keys = editKeysOf(s)
    const d: Record<string, string> = {}
    keys.forEach(k => { d[k] = '' })
    if (s.key && typeof s.value !== 'object') d[s.key] = s.value != null ? String(s.value) : ''
    setDraft(d); setEditing(s.field); setErr(null)
  }

  const save = async (s: PCField) => {
    setBusy(true); setErr(null)
    try {
      const patch: Record<string, unknown> = {}
      for (const k of editKeysOf(s)) {
        const raw = draft[k]
        if (raw === undefined || raw === '') continue
        if (k === 'makes_sustainable_investments') patch[k] = raw === 'true'
        else if (k.endsWith('_pct')) patch[k] = Number(raw)
        else patch[k] = raw
      }
      if (!Object.keys(patch).length) { setEditing(null); return }
      const r = await api.put<{ error?: string }>(`/v1/funds/${fundId}/precontractual`, patch)
      if (r.error) { setErr(r.error); return }
      setEditing(null); qc.invalidateQueries({ queryKey: ['fund-precontractual', fundId] }); onDone()
    } catch (e) { setErr(e instanceof ApiError ? String(e.body ?? e.message) : 'Could not save.') }
    finally { setBusy(false) }
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)]">
        <SectionHead>SFDR pre-contractual disclosure</SectionHead>
        {cov && <div className="mono text-[11px] text-[var(--color-faint)] mt-0.5">{data.template} · {cov.computed}/{cov.fields} computed · {cov.declared} declared · {cov.not_available} missing</div>}
      </div>
      <div className="divide-y divide-[var(--color-line)]">
        {sections.map((s, i) => {
          const badge = PC_STATUS[s.status] ?? { c: 'var(--color-faint)', label: s.status }
          const keys = editKeysOf(s)
          const isEditing = editing === s.field
          return (
            <div key={i} className="px-5 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="text-[12.5px] text-[var(--color-ink)] max-w-[65%]">{s.field}</div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="mono text-[10px]" style={{ color: badge.c }}>{badge.label}</span>
                  {keys.length > 0 && !isEditing && <button onClick={() => startEdit(s)} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline">edit</button>}
                </div>
              </div>
              {!isEditing && <div className="text-[12px] text-[var(--color-mute)] mt-1">{renderPCValue(s.value)}</div>}
              {s.note && <div className="text-[10.5px] text-[var(--color-faint)] mt-1">{s.note}</div>}
              {s.input_required && !isEditing && <div className="text-[10.5px] text-[var(--color-warn)] mt-1">Needed: {s.input_required}</div>}
              {isEditing && (
                <div className="mt-2 space-y-2 max-w-md">
                  {keys.map(k => <PCFieldInput key={k} fieldKey={k} value={draft[k] ?? ''} onChange={v => setDraft(d => ({ ...d, [k]: v }))} />)}
                  {err && <div className="text-[11px] text-[var(--color-bad)]">{err}</div>}
                  <div className="flex items-center gap-3">
                    <Button variant="primary" onClick={() => save(s)} disabled={busy}>Save</Button>
                    <button onClick={() => setEditing(null)} className="mono text-[11px] text-[var(--color-mute)] hover:underline">cancel</button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}
