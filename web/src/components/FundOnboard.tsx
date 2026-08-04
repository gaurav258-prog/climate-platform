import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, FileSpreadsheet, Check } from 'lucide-react'
import { api, ApiError, download } from '../lib/api'
import { Card, Button } from './ui'

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
          <p className="text-[12px] text-[var(--color-mute)]">Upload a CSV of ISINs (+ market value). Each is resolved to its issuer, located on the H3 grid and value-weighted into the fund — filling the SFDR statement automatically. Start from the template.</p>
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
            <button onClick={() => download('/v1/holdings/template.csv', 'tellumen_holdings_template.csv').catch(() => alert('Could not download the template.'))}
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
