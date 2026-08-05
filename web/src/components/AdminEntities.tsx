import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, CornerDownRight, Check, X } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { Card, Button } from './ui'

// Manage the reporting-entity hierarchy — the legal-entity / fund tree a group files and consolidates over.
// A filing can be scoped to one entity (its own book) or a parent/group (its whole subtree, consolidated).

interface Ent {
  entity_id: string; name: string; kind: string; parent_entity_id: string | null
  ownership_pct: number; consolidation_method: string; n_assets: number; value_eur: number
}
interface Form { name: string; kind: string; parent_entity_id: string; ownership_pct: number; consolidation_method: string }

const KINDS = ['group', 'sub_group', 'legal_entity', 'fund', 'division']
const METHODS = ['full', 'proportional', 'equity']
const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const err = (e: unknown, fb: string) => e instanceof ApiError ? (typeof e.body === 'object' && e.body && 'message' in e.body ? String((e.body as { message: unknown }).message) : fb) : fb

export default function AdminEntities() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['filing-entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/filings/entities') })
  const ents = q.data?.entities ?? []
  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const refresh = () => { qc.invalidateQueries({ queryKey: ['filing-entities'] }); qc.invalidateQueries({ queryKey: ['filings'] }) }

  // build the tree for indented rendering
  const byParent = new Map<string | null, Ent[]>()
  for (const e of ents) { const k = e.parent_entity_id; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k)!.push(e) }
  const rows: { e: Ent; depth: number }[] = []
  const walk = (parent: string | null, depth: number) => {
    for (const e of (byParent.get(parent) ?? [])) { rows.push({ e, depth }); walk(e.entity_id, depth + 1) }
  }
  walk(null, 0)

  const del = async (e: Ent) => {
    if (!confirm(`Remove “${e.name}”? Its ${e.n_assets} asset(s) fall back to whole-org scope.`)) return
    setMsg(null)
    try { await api.del(`/v1/filings/entities/${e.entity_id}`); refresh() }
    catch (ex) { setMsg(err(ex, 'Could not remove the entity.')) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <p className="text-[13px] text-[var(--color-mute)] max-w-2xl">The legal-entity / fund structure you file over. A filing can cover one entity (its own book) or a <b>group</b> — which consolidates its whole subtree, weighting proportional lines by ownership.</p>
        {!adding && <Button variant="ghost" onClick={() => { setAdding(true); setEditId(null) }}><Plus size={14} /> Add entity</Button>}
      </div>
      {msg && <div className="text-[12.5px] text-[var(--color-bad)]">{msg}</div>}

      {adding && <EntityForm ents={ents} onCancel={() => setAdding(false)} onSaved={() => { setAdding(false); refresh() }} onError={setMsg} />}

      <Card className="p-0 overflow-hidden">
        <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-4 px-5 py-2 border-b border-[var(--color-line)] mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">
          <div>Entity</div><div className="text-right">Book</div><div className="text-right">Consolidation</div><div></div>
        </div>
        {q.isLoading ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">loading…</div>
          : rows.length === 0 ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">No reporting entities yet — add one to build the group structure.</div>
          : <div className="divide-y divide-[var(--color-line)]">
              {rows.map(({ e, depth }) => editId === e.entity_id
                ? <div key={e.entity_id} className="px-5 py-3"><EntityForm ents={ents} edit={e} onCancel={() => setEditId(null)} onSaved={() => { setEditId(null); refresh() }} onError={setMsg} /></div>
                : (
                <div key={e.entity_id} className="grid grid-cols-[1fr_auto_auto_auto] gap-x-4 items-center px-5 py-3 hover:bg-[var(--color-bg-2)]">
                  <div className="min-w-0 flex items-center" style={{ paddingLeft: depth * 22 }}>
                    {depth > 0 && <CornerDownRight size={13} className="text-[var(--color-faint)] mr-1.5 shrink-0" />}
                    <div className="min-w-0">
                      <div className="text-[13.5px] text-[var(--color-ink)] truncate">{e.name}</div>
                      <div className="mono text-[10px] text-[var(--color-faint)]">{e.kind.replace(/_/g, ' ')}</div>
                    </div>
                  </div>
                  <div className="text-right"><div className="mono text-[12.5px] text-[var(--color-mute)]">{eur(e.value_eur)}</div><div className="mono text-[9.5px] text-[var(--color-faint)]">{e.n_assets} asset{e.n_assets === 1 ? '' : 's'}</div></div>
                  <div className="text-right w-40">
                    {e.parent_entity_id
                      ? <span className="mono text-[11px]" style={{ color: e.consolidation_method === 'full' ? 'var(--color-mute)' : 'var(--color-warn)' }}>{e.consolidation_method}{e.consolidation_method !== 'full' ? ` · ${Math.round(e.ownership_pct)}%` : ''}</span>
                      : <span className="mono text-[10px] text-[var(--color-faint)]">top level</span>}
                  </div>
                  <div className="flex items-center gap-1 justify-end">
                    <button onClick={() => { setEditId(e.entity_id); setAdding(false) }} title="Edit" className="text-[var(--color-faint)] hover:text-[var(--color-sky)] p-1"><Pencil size={13} /></button>
                    <button onClick={() => del(e)} title="Remove" className="text-[var(--color-faint)] hover:text-[var(--color-bad)] p-1"><Trash2 size={13} /></button>
                  </div>
                </div>
              ))}
            </div>}
      </Card>
    </div>
  )
}

function EntityForm({ ents, edit, onCancel, onSaved, onError }: { ents: Ent[]; edit?: Ent; onCancel: () => void; onSaved: () => void; onError: (m: string) => void }) {
  const [f, setF] = useState<Form>({
    name: edit?.name ?? '', kind: edit?.kind ?? 'legal_entity',
    parent_entity_id: edit?.parent_entity_id ?? '', ownership_pct: edit?.ownership_pct ?? 100,
    consolidation_method: edit?.consolidation_method ?? 'full',
  })
  const [busy, setBusy] = useState(false)
  // a node can't be its own parent or (on edit) parented under a descendant — the backend enforces it too;
  // here we just drop self from the options for a cleaner list
  const parentOpts = ents.filter(e => e.entity_id !== edit?.entity_id)
  const set = (k: keyof Form, v: string | number) => setF(s => ({ ...s, [k]: v }))
  const box = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]'

  const save = async () => {
    if (!f.name.trim()) { onError('Name is required.'); return }
    setBusy(true); onError('')
    try {
      const body = { name: f.name.trim(), kind: f.kind, ownership_pct: Number(f.ownership_pct), consolidation_method: f.consolidation_method }
      if (edit) await api.patch(`/v1/filings/entities/${edit.entity_id}`, { ...body, set_parent: true, parent_entity_id: f.parent_entity_id || null })
      else await api.post('/v1/filings/entities', { ...body, parent_entity_id: f.parent_entity_id || null })
      onSaved()
    } catch (ex) { onError(err(ex, 'Could not save the entity.')) }
    finally { setBusy(false) }
  }

  return (
    <div className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] p-3 flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Name</span>
        <input autoFocus value={f.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Meridian Leasing GmbH" className={`${box} w-56`} /></label>
      <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Kind</span>
        <select value={f.kind} onChange={e => set('kind', e.target.value)} className={box}>{KINDS.map(k => <option key={k} value={k}>{k.replace(/_/g, ' ')}</option>)}</select></label>
      <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Parent</span>
        <select value={f.parent_entity_id} onChange={e => set('parent_entity_id', e.target.value)} className={box}>
          <option value="">— top level —</option>
          {parentOpts.map(e => <option key={e.entity_id} value={e.entity_id}>{e.name}</option>)}
        </select></label>
      <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Consolidation</span>
        <select value={f.consolidation_method} onChange={e => set('consolidation_method', e.target.value)} className={box}>{METHODS.map(m => <option key={m} value={m}>{m}</option>)}</select></label>
      {f.consolidation_method !== 'full' && (
        <label className="flex flex-col gap-1"><span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Ownership %</span>
          <input type="number" min={0} max={100} value={f.ownership_pct} onChange={e => set('ownership_pct', e.target.value)} className={`${box} w-24`} /></label>
      )}
      <Button variant="primary" onClick={save} disabled={busy}><Check size={14} /> {edit ? 'Save' : 'Add'}</Button>
      <Button variant="ghost" onClick={onCancel}><X size={14} /> Cancel</Button>
    </div>
  )
}
