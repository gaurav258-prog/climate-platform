import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderInput, KeyRound, RefreshCw, Trash2 } from 'lucide-react'
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
      <SftpKeys />
    </Card>
  )
}

interface SftpKey { key_id: string; label: string; key_type: string; fingerprint: string; bits: number | null; created_by: string | null; created_at: string; revoked_at: string | null }

// Public keys your systems use to log in to these folders by SFTP (one login per organisation, keys only — no
// passwords). Each key is checked (type, strength), fingerprinted, and added / revoked on the audit trail.
function SftpKeys() {
  const q = useQuery({ queryKey: ['sftp-keys'], queryFn: () => api.get<{ keys: SftpKey[] }>('/v1/intake/sftp-keys') })
  const [label, setLabel] = useState('')
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const keys = q.data?.keys ?? []
  const add = async () => {
    setBusy(true)
    try { await api.post('/v1/intake/sftp-keys', { label: label.trim(), public_key: key.trim() }); setLabel(''); setKey(''); q.refetch(); toast.success('Key added.') }
    catch (e: unknown) { toast.error((e as { body?: { error?: { message?: string } } })?.body?.error?.message ?? 'Could not add the key.') }
    finally { setBusy(false) }
  }
  const revoke = async (id: string) => {
    if (!confirm('Revoke this key? The system using it can no longer log in.')) return
    try { await api.del(`/v1/intake/sftp-keys/${id}`); q.refetch() } catch { toast.error('Could not revoke.') }
  }
  return (
    <div className="mt-4 pt-4 border-t border-[var(--color-line)]">
      <div className="flex items-center gap-2"><KeyRound size={14} className="text-[var(--color-sky)]" /><span className="text-[13px] font-semibold text-[var(--color-ink)]">SFTP access keys</span></div>
      <p className="text-[12px] text-[var(--color-mute)] mt-1 max-w-2xl">Paste the <b>public</b> key (the <code className="mono">.pub</code> file) of each system that sends files. ssh-ed25519 is preferred; RSA must be at least 3072 bits. Never paste a private key.</p>
      {keys.length > 0 && (
        <div className="mt-2 divide-y divide-[var(--color-line)] border border-[var(--color-line)] rounded-lg">
          {keys.map(k => (
            <div key={k.key_id} className="flex items-center gap-3 flex-wrap px-3.5 py-2 text-[12.5px]" style={k.revoked_at ? { opacity: 0.55 } : undefined}>
              <span className="text-[var(--color-ink)]">{k.label}</span>
              <code className="mono text-[10.5px] text-[var(--color-mute)] break-all">{k.fingerprint}</code>
              <span className="text-[11px] text-[var(--color-faint)]">{k.key_type}{k.bits ? ` · ${k.bits} bits` : ''} · added {k.created_at.slice(0, 10)}{k.created_by ? ` by ${k.created_by}` : ''}</span>
              {k.revoked_at ? <span className="ml-auto mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">revoked {k.revoked_at.slice(0, 10)}</span>
                : <button onClick={() => revoke(k.key_id)} className="ml-auto inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-bad)]"><Trash2 size={12} /> Revoke</button>}
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="min-w-[180px]"><span className="text-[11.5px] text-[var(--color-mute)]">Label</span>
          <input value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Core banking nightly" maxLength={80} className={inp + ' mt-1'} /></label>
        <label className="flex-1 min-w-[260px]"><span className="text-[11.5px] text-[var(--color-mute)]">Public key</span>
          <input value={key} onChange={e => setKey(e.target.value)} placeholder="ssh-ed25519 AAAAC3Nza… name@host" className={inp + ' mt-1 mono text-[11.5px]'} /></label>
        <Button onClick={add} disabled={busy || !label.trim() || !key.trim()}>{busy ? 'Adding…' : 'Add key'}</Button>
      </div>
    </div>
  )
}
