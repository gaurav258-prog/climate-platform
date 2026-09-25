import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderInput, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button } from './ui'

// Drop-folder channels — where a customer's SFTP feed lands. One folder per template; every finished file runs
// through the same intake pipeline as an upload (services/intake/dropfolder.py). Works the same for every sector.

export const SECTOR_TEMPLATES: Record<string, { key: string; label: string }[]> = {
  bank: [{ key: 'bank_assets', label: 'loan tape' }],
  insurer: [{ key: 'insurance_policies', label: 'Statement of Values' }],
  reit: [{ key: 'realestate_properties', label: 'property schedule' }],
  asset_manager: [{ key: 'assetmgmt_holdings', label: 'holdings book' }],
  manufacturer: [{ key: 'supply_plots', label: 'sourcing plots' }],
}

interface Channel { channel_id: string; template: string; label: string; sftp_path: string; owner_email: string; n_waiting: number; last_swept_at: string | null; enabled: boolean }
interface SweepResult { file: string; state: string; reason?: string; moved_to?: string }
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
const STATE_TONE: Record<string, string> = { imported: 'var(--color-good)', awaiting_approval: 'var(--color-warn)', held: 'var(--color-warn)', refused: 'var(--color-bad, #e0574a)', error: 'var(--color-bad, #e0574a)' }

export default function DropFolders({ sector }: { sector: string }) {
  const q = useQuery({ queryKey: ['intake-channels'], queryFn: () => api.get<{ channels: Channel[] }>('/v1/intake/channels') })
  const uq = useQuery({ queryKey: ['admin-users'], queryFn: () => api.get<{ id: string; email: string; status: string }[]>('/v1/admin/users') })
  const templates = SECTOR_TEMPLATES[sector] ?? []
  const channels = q.data?.channels ?? []
  const open = templates.filter(t => !channels.some(c => c.template === t.key))
  const [tpl, setTpl] = useState('')
  const [owner, setOwner] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<Record<string, SweepResult[]>>({})

  const create = async () => {
    const template = tpl || open[0]?.key
    if (!template || !owner) { toast.error('Choose who stands as the sender.'); return }
    setBusy(true)
    try { await api.post('/v1/intake/channels', { template, owner_user_id: owner }); q.refetch() }
    catch (e: unknown) { toast.error((e as { body?: { error?: { message?: string } } })?.body?.error?.message ?? 'Could not open the folder.') }
    finally { setBusy(false) }
  }
  const sweep = async (id: string) => {
    try {
      const r = await api.post<{ files: SweepResult[] }>(`/v1/intake/channels/${id}/sweep`)
      setResults(x => ({ ...x, [id]: r.files })); q.refetch()
      if (!r.files.length) toast.success('Nothing finished arriving yet.')
    } catch { toast.error('Could not pick up the files.') }
  }

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2"><FolderInput size={15} className="text-[var(--color-sky)]" /><h3 className="text-[14px] font-semibold text-[var(--color-ink)]">Drop folders (SFTP)</h3></div>
      <p className="text-[12.5px] text-[var(--color-mute)] mt-1 max-w-2xl">Your system sends files to a folder instead of calling the API. Every file that has finished arriving is picked up every 5 minutes and checked exactly like an upload — your saved column mapping is used automatically. A file that fails a check goes to a second person; a refused file is moved aside with the reason next to it.</p>

      {channels.length > 0 && (
        <div className="mt-3 divide-y divide-[var(--color-line)] border border-[var(--color-line)] rounded-lg">
          {channels.map(c => (
            <div key={c.channel_id} className="px-3.5 py-2.5 text-[12.5px]">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-[var(--color-ink)] capitalize">{c.label}</span>
                <code className="mono text-[11px] text-[var(--color-mute)]">{c.sftp_path}</code>
                <span className="text-[11.5px] text-[var(--color-faint)]">sender: {c.owner_email}</span>
                <span className="text-[11.5px] text-[var(--color-faint)]">{c.n_waiting} waiting · last picked up {c.last_swept_at ? c.last_swept_at.replace('T', ' ') : 'never'}</span>
                <button onClick={() => sweep(c.channel_id)} className="ml-auto inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><RefreshCw size={12} /> Pick up now</button>
              </div>
              {(results[c.channel_id] ?? []).map((r, i) => (
                <div key={i} className="mt-1 text-[11.5px]"><span className="mono">{r.file}</span> — <span style={{ color: STATE_TONE[r.state] }}>{r.state.replace('_', ' ')}</span>{r.reason ? `: ${r.reason}` : ''}</div>
              ))}
            </div>
          ))}
        </div>
      )}

      {open.length > 0 && (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          {open.length > 1 && <label className="min-w-[180px]"><span className="text-[11.5px] text-[var(--color-mute)]">Book</span>
            <select value={tpl} onChange={e => setTpl(e.target.value)} className={inp + ' mt-1'}>{open.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}</select></label>}
          <label className="flex-1 min-w-[220px]"><span className="text-[11.5px] text-[var(--color-mute)]">Sender (a failed check goes to someone else)</span>
            <select value={owner} onChange={e => setOwner(e.target.value)} className={inp + ' mt-1'}>
              <option value="">— choose a person —</option>
              {(uq.data ?? []).filter(u => u.status === 'active').map(u => <option key={u.id} value={u.id}>{u.email}</option>)}
            </select></label>
          <Button onClick={create} disabled={busy}>{busy ? 'Opening…' : `Open a drop folder for your ${open[0].label}`}</Button>
        </div>
      )}
      <div className="text-[11px] text-[var(--color-faint)] mt-3">SFTP access to these folders is set up with our team (one login per organisation, keys only).</div>
    </Card>
  )
}
