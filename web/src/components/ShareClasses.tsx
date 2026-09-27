import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Check, X } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, SectionHead } from './ui'
import { useCurrencies } from './MoneyDeclaration'

// A fund's share classes — the versions of the fund sold to investors (same portfolio; own ISIN, currency, hedging,
// income paid out or reinvested). The European ESG Template is one row per ACTIVE share class. A class is closed,
// never deleted, so a published EET that listed it still reads.

export interface ShareClass { share_class_id: string; isin: string; name: string; currency: string; hedged: boolean; distribution: string; launch_date: string | null; status: string }

export const apiMessage = (e: unknown, fb: string) => {
  if (!(e instanceof ApiError) || typeof e.body !== 'object' || !e.body) return fb
  const b = e.body as { message?: unknown; error?: { message?: unknown } }
  return String(b.error?.message ?? b.message ?? fb)
}

const box = 'bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]'

export default function ShareClasses({ fundId }: { fundId: string }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['share-classes', fundId], queryFn: () => api.get<{ share_classes: ShareClass[] }>(`/v1/funds/${fundId}/share-classes`) })
  const currencies = useCurrencies()
  const [adding, setAdding] = useState(false)
  const [f, setF] = useState({ isin: '', name: '', currency: 'EUR', hedged: false, distribution: 'accumulating', launch_date: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const list = q.data?.share_classes ?? []
  const refresh = () => { qc.invalidateQueries({ queryKey: ['share-classes', fundId] }); qc.invalidateQueries({ queryKey: ['eet-draft'] }); qc.invalidateQueries({ queryKey: ['eet-changes'] }) }

  const add = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/v1/funds/${fundId}/share-classes`, { ...f, isin: f.isin.trim().toUpperCase(), name: f.name.trim(), launch_date: f.launch_date || undefined })
      toast.success(`Share class ${f.isin.toUpperCase()} added.`)
      setF({ isin: '', name: '', currency: 'EUR', hedged: false, distribution: 'accumulating', launch_date: '' }); setAdding(false); refresh()
    } catch (e) { setErr(apiMessage(e, 'Could not add the share class.')) } finally { setBusy(false) }
  }
  const setStatus = async (sc: ShareClass, status: string) => {
    try { await api.patch(`/v1/share-classes/${sc.share_class_id}`, { status }); toast.success(`${sc.isin} ${status === 'closed' ? 'closed' : 'reopened'}.`); refresh() }
    catch (e) { toast.error(apiMessage(e, 'Could not change the share class.')) }
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
        <SectionHead hint="one EET row each">Share classes</SectionHead>
        {!adding && <Button onClick={() => setAdding(true)}><Plus size={13} /> Add share class</Button>}
      </div>
      {adding && (
        <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">ISIN</span>
            <input value={f.isin} onChange={e => setF({ ...f, isin: e.target.value })} maxLength={12} placeholder="LU0274208692" className={`${box} mono w-36`} /></label>
          <label className="flex flex-col gap-1 flex-1 min-w-[180px]"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Name</span>
            <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Class A EUR Acc" className={box} /></label>
          <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Currency</span>
            <select value={f.currency} onChange={e => setF({ ...f, currency: e.target.value })} className={`${box} mono`}>{currencies.map(c => <option key={c}>{c}</option>)}</select></label>
          <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Income</span>
            <select value={f.distribution} onChange={e => setF({ ...f, distribution: e.target.value })} className={box}>
              <option value="accumulating">reinvested (Acc)</option><option value="distributing">paid out (Dis)</option></select></label>
          <label className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] pb-2"><input type="checkbox" checked={f.hedged} onChange={e => setF({ ...f, hedged: e.target.checked })} /> currency-hedged</label>
          <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Launched</span>
            <input type="date" value={f.launch_date} onChange={e => setF({ ...f, launch_date: e.target.value })} className={box} /></label>
          <Button variant="primary" onClick={add} disabled={busy || !f.isin || !f.name}><Check size={13} /> Add</Button>
          <button onClick={() => { setAdding(false); setErr(null) }} className="text-[var(--color-faint)] hover:text-[var(--color-ink)] pb-2" aria-label="Cancel"><X size={15} /></button>
          {err && <div className="w-full text-[12px]" style={{ color: 'var(--color-bad)' }}>{err}</div>}
        </div>
      )}
      {list.length === 0
        ? <div className="px-5 py-6 text-[12.5px] text-[var(--color-mute)]">No share classes yet. Add each version of this fund you sell — the European ESG Template has one row per share class.</div>
        : <div className="divide-y divide-[var(--color-line)]">{list.map(sc => (
            <div key={sc.share_class_id} className="px-5 py-2.5 flex items-center gap-3 text-[12.5px]">
              <span className="mono text-[var(--color-ink)] w-32 shrink-0">{sc.isin}</span>
              <span className="flex-1 min-w-0 truncate text-[var(--color-mute)]">{sc.name}</span>
              <span className="mono text-[11px] text-[var(--color-faint)] shrink-0">{sc.currency}{sc.hedged ? ' · hedged' : ''} · {sc.distribution === 'accumulating' ? 'Acc' : 'Dis'}</span>
              {sc.status === 'closed'
                ? <button onClick={() => setStatus(sc, 'active')} className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] hover:text-[var(--color-sky)] shrink-0">closed · reopen</button>
                : <button onClick={() => setStatus(sc, 'closed')} className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] hover:text-[var(--color-warn)] shrink-0">close</button>}
            </div>))}
          </div>}
    </Card>
  )
}
