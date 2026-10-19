import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, FileSpreadsheet, ListPlus, PackagePlus } from 'lucide-react'
import { api, apiMessage, apiDetail, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, SectionHead } from './ui'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Meter, SidePanel } from './sfdr/visuals'

// Two write actions on a fund: add holdings by ISIN (each matched to its issuer, located and weighted by value into the
// fund), and choose the additional adverse-impact indicators the fund adopts (at least one environmental and one social).

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

interface OnboardResp {
  holdings_submitted: number; distinct_isins: number; positions_created: number; coverage: { matched: number; match_rate_pct: number }
  messages: { summary: Message } & Partial<Record<'unmatched' | 'errored' | 'fx' | 'sector' | 'located' | 'own' | 'refused', Message>>
}
type Problem = { label: string; detail: ReturnType<typeof apiDetail> } | null

export function OnboardHoldings({ fundId, onDone }: { fundId: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<OnboardResp | null>(null)
  const [err, setErr] = useState<Problem>(null)

  const send = async (file: File) => {
    setBusy(true); setErr(null); setRes(null)
    try {
      const rows = parseCsv(await file.text())
      if (!rows.length) { setErr({ label: 'The file has no rows.', detail: { what: 'The file holds a header but no holdings.', next: 'Fill the template with one row per holding.' } }); return }
      const holdings = rows.map(r => { const o: Record<string, unknown> = {}; for (const k in r) { const c = coerce(r[k]); if (c !== undefined) o[k] = c } return o }).filter(h => h.isin)
      if (!holdings.length) { setErr({ label: 'No row has an ISIN.', detail: { what: 'Each holding is matched to its issuer by its ISIN.', next: 'Fill the ISIN column of the template.' } }); return }
      const r = await api.post<OnboardResp>(`/v1/funds/${fundId}/holdings`, { holdings })
      setRes(r); onDone()
    } catch (e) { setErr({ label: apiMessage(e, 'Could not add the holdings.'), detail: apiDetail(e) }) }
    finally { setBusy(false) }
  }
  const extra = res ? (['unmatched', 'errored', 'fx', 'sector', 'located', 'own', 'refused'] as const).map(k => res.messages[k]).filter(Boolean) as Message[] : []

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <SectionHead icon={PackagePlus}>Add holdings</SectionHead>
          <InfoButton compact details={{ title: 'Add holdings', sections: [
            { heading: HEADING.shows, body: 'Upload a file of ISINs with their market value. Each is matched to its issuer, located on the map and weighted by value into the fund, which fills its figures.' },
            { heading: HEADING.read, body: 'Start from the template. Optional columns carry what you hold about each issuer — industry, emissions, revenue, Taxonomy shares — and fill the figures investees do not report.' }] }} />
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => download('/v1/holdings/template.csv', 'tellumen_holdings_template.csv').catch(() => toast.error('Could not download the template.'))}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12.5px] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={14} /> Template</button>
          <label className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-medium cursor-pointer transition ${busy ? 'bg-[var(--color-panel)] text-[var(--color-faint)]' : 'bg-[var(--color-sky)] text-[#08111f] hover:bg-[var(--color-blue)]'}`}>
            <Upload size={14} /> {busy ? 'Adding…' : 'Upload'}
            <input type="file" accept=".csv" className="hidden" disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) send(f); e.target.value = '' }} />
          </label>
        </div>
      </div>
      {err && <MessageLine m={err} className="mt-3 text-[12.5px] text-[var(--color-bad)]" />}
      {res && (
        <div className="mt-3 grid gap-3 sm:grid-cols-[auto_1fr] items-start">
          <div className="space-y-1.5">
            <MessageLine m={res.messages.summary} className="text-[13px] text-[var(--color-good)]" />
            <div className="flex items-center gap-2 text-[11.5px] text-[var(--color-faint)]">ISINs matched <Meter value={res.coverage.match_rate_pct} width="w-24" /></div>
          </div>
          {extra.length > 0 && <div className="flex flex-wrap gap-x-4 gap-y-1 sm:justify-end">{extra.map((m, i) => <MessageLine key={i} m={m} className="text-[12px] text-[var(--color-warn)]" />)}</div>}
        </div>)}
    </Card>
  )
}

interface Cat { key: string; table: number; row: string; kind: string; name: string; metric: string; unit: string }
export function VoluntaryPai({ fundId, selected, onDone }: { fundId: string; selected: string[]; onDone: () => void }) {
  const qc = useQueryClient()
  const cat = useQuery({ queryKey: ['vpai-catalog'], queryFn: () => api.get<{ indicators: Cat[] }>('/v1/voluntary-pai/catalog') })
  const [open, setOpen] = useState(false)
  const [sel, setSel] = useState<string[]>(selected)
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Problem>(null)
  const inds = cat.data?.indicators ?? []
  const env = inds.filter(i => i.kind === 'environmental'), soc = inds.filter(i => i.kind === 'social')
  const toggle = (k: string) => setSel(s => s.includes(k) ? s.filter(x => x !== k) : [...s, k])
  const nEnv = (list: string[]) => list.filter(k => env.some(e => e.key === k)).length
  const nSoc = (list: string[]) => list.filter(k => soc.some(e => e.key === k)).length

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api.put<{ msg: Message }>(`/v1/funds/${fundId}/voluntary-pai`, { indicator_keys: sel })
      toast.success(r.msg.label); qc.invalidateQueries({ queryKey: ['fund-sfdr', fundId] }); onDone(); setOpen(false)
    } catch (e) { setErr({ label: apiMessage(e, 'Could not save.'), detail: apiDetail(e) }) }
    finally { setBusy(false) }
  }

  const group = (title: string, list: Cat[]) => (
    <div>
      <div className="text-[12.5px] font-medium text-[var(--color-ink)] mb-1.5">{title}</div>
      <div className="space-y-1.5">
        {list.map(i => (
          <label key={i.key} className="flex items-start gap-2 text-[12.5px] cursor-pointer">
            <input type="checkbox" checked={sel.includes(i.key)} onChange={() => toggle(i.key)} className="mt-0.5" />
            <span className="text-[var(--color-mute)]">{i.name} <span className="text-[var(--color-faint)] text-[11px]">{i.unit}</span></span>
            <InfoButton compact details={{ title: i.name, sections: [{ heading: 'Metric', body: i.metric }, { heading: 'Where the Regulation prints it', body: `Annex I, Table ${i.table}, indicator ${i.row}` }] }} />
          </label>
        ))}
      </div>
    </div>
  )
  const ok = (list: string[]) => nEnv(list) >= 1 && nSoc(list) >= 1

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <SectionHead icon={ListPlus}>Additional indicators</SectionHead>
          <StatusChip tone={ok(selected) ? 'good' : 'warn'} label={`${nEnv(selected)} environmental · ${nSoc(selected)} social`} />
          <InfoButton compact details={{ title: 'Additional indicators', sections: [
            { heading: HEADING.shows, body: 'Besides the mandatory indicators, a fund adopts at least one more environmental and one more social indicator.' },
            { heading: HEADING.limits, body: 'Indicators for government bonds, real estate and green bonds need data not held per issuer, so they are not offered.' },
            { heading: 'Legal basis', body: 'Delegated Regulation (EU) 2022/1288, Annex I, Tables 2 and 3.' }] }} />
        </div>
        <Button variant="ghost" onClick={() => { setSel(selected); setErr(null); setOpen(true) }}>Choose</Button>
      </div>
      {open && (
        <SidePanel title="Additional indicators" onClose={() => setOpen(false)}>
          <div className="space-y-4">
            {err && <MessageLine m={err} className="text-[12px] text-[var(--color-bad)]" />}
            {group('Environmental', env)}{group('Social', soc)}
            <div className="flex items-center gap-3 pt-2 border-t border-[var(--color-line)]">
              <Button variant="primary" onClick={save} disabled={busy || !ok(sel)}>Save selection</Button>
              <StatusChip tone={ok(sel) ? 'good' : 'warn'} label={`${nEnv(sel)} environmental · ${nSoc(sel)} social`} />
            </div>
          </div>
        </SidePanel>)}
    </Card>
  )
}
