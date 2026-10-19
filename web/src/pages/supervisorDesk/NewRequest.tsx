import { useState } from 'react'
import clsx from 'clsx'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../../components/ui'
import { Dialog } from '../../components/Dialog'
import { StatusChip } from '../../components/StatusChip'
import type { ListResp, Req } from '../SupervisorRequests'
import { field } from './common'

// Raise a request or finding with an entity, in a dialog. A cell raised from the full rebuild arrives prefilled (its
// title, and the cell's codes as the source the thread links back to).
export function NewRequestDialog({ d, params, onDone, onClose }: { d: ListResp; params: URLSearchParams; onDone: (id: string | null) => void; onClose: () => void }) {
  const [entity, setEntity] = useState(params.get('entity') ?? d.entities[0]?.org_id ?? '')
  const [kind, setKind] = useState(params.get('kind') ?? Object.keys(d.kinds)[0] ?? '')
  const [title, setTitle] = useState(params.get('title') ?? '')
  const [body, setBody] = useState(params.get('body') ?? '')
  const [severity, setSeverity] = useState('')
  const [due, setDue] = useState('')
  const [busy, setBusy] = useState(false)
  const k = d.kinds[kind]
  const source = params.get('geography') ? { type: 'lens_cell', geography: params.get('geography'), sector: params.get('sector') } : undefined
  const submit = async () => {
    setBusy(true)
    try {
      const r = await api.post<Req>('/v1/supervisor/requests', { supervised_org_id: entity, kind, title, body: body || null, severity: severity || null, due_date: due || null, source })
      toast.success(`${r.kind_label} raised with ${r.entity}.`); onDone(r.request_id)
    } catch (e) { toast.error(apiMessage(e, 'Could not raise it.')) } finally { setBusy(false) }
  }
  const lab = 'block text-[12px] text-[var(--color-mute)]'
  return (
    <Dialog title="New request or finding" onClose={onClose} className="sm:max-w-xl">
      <div className="space-y-3">
        {source && <StatusChip label="From the full rebuild" tone="neutral" />}
        <div className="grid sm:grid-cols-2 gap-3">
          <label className={lab}>Entity<select value={entity} onChange={e => setEntity(e.target.value)} className={clsx(field, 'w-full mt-1')}>
            {d.entities.map(e => <option key={e.org_id} value={e.org_id}>{e.name}</option>)}</select></label>
          <label className={lab}>Kind<select value={kind} onChange={e => { setKind(e.target.value); setSeverity('') }} className={clsx(field, 'w-full mt-1')}>
            {Object.entries(d.kinds).map(([kk, v]) => <option key={kk} value={kk}>{v.label}</option>)}</select></label>
        </div>
        <label className={lab}>Title<input value={title} onChange={e => setTitle(e.target.value)} className={clsx(field, 'w-full mt-1')} placeholder="What you need, in one line" /></label>
        <label className={lab}>Detail<textarea value={body} onChange={e => setBody(e.target.value)} rows={4} className={clsx(field, 'w-full mt-1')} placeholder="What you observed and what you expect" /></label>
        <div className="grid sm:grid-cols-2 gap-3 items-end">
          <label className={lab}>Due date<input type="date" value={due} onChange={e => setDue(e.target.value)} className={clsx(field, 'w-full mt-1')} /></label>
          {k?.severities.length ? (
            <div className={lab}>Severity
              <div className="flex gap-1.5 mt-1" role="group" aria-label="Severity">{k.severities.map(s => (
                <button key={s} type="button" onClick={() => setSeverity(s)} aria-pressed={severity === s}
                  className={clsx('px-2.5 py-1.5 rounded-lg border text-[12.5px]', severity === s ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)]')}>
                  {k.severity_labels[s] ?? s}</button>))}</div>
            </div>) : null}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} disabled={busy || !title.trim() || !entity}>{busy ? 'Raising…' : 'Raise with the entity'}</Button>
        </div>
      </div>
    </Dialog>
  )
}
