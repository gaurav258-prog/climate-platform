import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileSignature, Upload, Download, Trash2, X, ShieldCheck } from 'lucide-react'
import { api, download, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, PageHeader, Button, SectionHead } from '../components/ui'

interface Contract {
  contract_id: string; title: string; counterparty: string | null; contract_type: string; status: string
  signed_date: string | null; effective_date: string | null; expiry_date: string | null
  filename: string; content_type: string | null; size_bytes: number; created_at: string | null
  uploaded_by: string | null; uploaded_by_email: string | null
}
interface ContractsResp { contracts: Contract[]; can_manage: boolean }

const TYPE_LABEL: Record<string, string> = { msa: 'MSA', dpa: 'DPA', sow: 'SOW', order_form: 'Order form', nda: 'NDA', other: 'Other' }
const STATUS_TONE: Record<string, string> = { active: 'var(--color-good)', expired: 'var(--color-warn)', terminated: 'var(--color-bad)', draft: 'var(--color-faint)' }
const kb = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`

export default function Contracts() {
  const q = useQuery({ queryKey: ['contracts'], queryFn: () => api.get<ContractsResp>('/v1/contracts') })
  const [showUp, setShowUp] = useState(false)
  const qc = useQueryClient()

  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>You don't have access to contracts, or the API is unreachable.</Center>
  const d = q.data

  const remove = async (c: Contract) => {
    if (!confirm(`Remove "${c.title}"? This can't be undone.`)) return
    try { await api.del(`/v1/contracts/${c.contract_id}`); toast.success('Contract removed'); qc.invalidateQueries({ queryKey: ['contracts'] }) }
    catch { toast.error('Could not remove the contract.') }
  }

  return (
    <div className="fadeup space-y-6">
      <div className="flex items-start justify-between gap-4">
        <PageHeader eyebrow="Set up · governed documents" title="Contracts"
          lead="Your organization's signed agreements — MSAs, DPAs, SOWs, order forms. Visible to members by role; every download is audited." />
        {d.can_manage && (
          <button onClick={() => setShowUp(true)}
            className="shrink-0 mt-1 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-3.5 py-2 text-[13px] font-medium hover:bg-[var(--color-blue)] transition">
            <Upload size={15} /> Upload contract
          </button>
        )}
      </div>
      {showUp && <UploadModal onClose={() => setShowUp(false)} onDone={() => { setShowUp(false); qc.invalidateQueries({ queryKey: ['contracts'] }) }} />}

      <Card className="p-3.5 flex items-center gap-2 text-[12.5px] text-[var(--color-mute)]">
        <ShieldCheck size={15} className="text-[var(--color-good)] shrink-0" />
        Access is role-based: admins &amp; approvers can view; only admins can upload or remove. {d.can_manage ? 'You can manage contracts.' : 'You have view access.'}
      </Card>

      {d.contracts.length === 0 ? (
        <Card className="p-10 text-center text-[13px] text-[var(--color-faint)]">No contracts on file yet.{d.can_manage ? ' Upload the first signed agreement above.' : ''}</Card>
      ) : (
        <Card className="p-0 overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[11px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
              <th className="font-normal py-2.5 px-4">Contract</th><th className="font-normal px-4">Type</th>
              <th className="font-normal px-4">Counterparty</th><th className="font-normal px-4">Status</th>
              <th className="font-normal px-4">Signed</th><th className="font-normal px-4 text-right">Size</th>
              <th className="font-normal px-4"></th>
            </tr></thead>
            <tbody>
              {d.contracts.map(c => (
                <tr key={c.contract_id} className="border-b border-[var(--color-line)] last:border-0 hover:bg-[var(--color-panel)] transition">
                  <td className="py-2.5 px-4"><div className="text-[var(--color-ink)]">{c.title}</div><div className="mono text-[10px] text-[var(--color-faint)]">{c.filename}</div></td>
                  <td className="px-4 mono text-[11px] text-[var(--color-mute)]">{TYPE_LABEL[c.contract_type] ?? c.contract_type}</td>
                  <td className="px-4 text-[var(--color-mute)]">{c.counterparty ?? '—'}</td>
                  <td className="px-4"><span className="mono text-[10px] px-2 py-0.5 rounded-full" style={{ color: STATUS_TONE[c.status], background: `color-mix(in oklab, ${STATUS_TONE[c.status]} 13%, transparent)` }}>{c.status}</span></td>
                  <td className="px-4 text-[var(--color-mute)] mono text-[11px]">{c.signed_date ?? '—'}</td>
                  <td className="px-4 text-right mono text-[11px] text-[var(--color-faint)]">{kb(c.size_bytes)}</td>
                  <td className="px-4">
                    <div className="flex items-center gap-2 justify-end">
                      <button title="Download" onClick={() => download(`/v1/contracts/${c.contract_id}/file`, c.filename).catch(() => toast.error('Could not download.'))}
                        className="text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={15} /></button>
                      {d.can_manage && <button title="Remove" onClick={() => remove(c)} className="text-[var(--color-faint)] hover:text-[var(--color-bad)]"><Trash2 size={15} /></button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

function UploadModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ title: '', counterparty: '', contract_type: 'msa', status: 'active', signed_date: '' })
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: string) => setF(s => ({ ...s, [k]: v }))

  const submit = async () => {
    if (!f.title.trim()) { toast.error('A title is required.'); return }
    if (!file) { toast.error('Choose a file to upload.'); return }
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', file); fd.append('title', f.title.trim())
      if (f.counterparty) fd.append('counterparty', f.counterparty)
      fd.append('contract_type', f.contract_type); fd.append('status', f.status)
      if (f.signed_date) fd.append('signed_date', f.signed_date)
      await api.post('/v1/contracts', fd)
      toast.success('Contract uploaded'); onDone()
    } catch (err) {
      toast.error(err instanceof ApiError ? (err.body as { message?: string })?.message ?? 'Upload failed.' : 'Upload failed.')
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-[480px]" onClick={e => e.stopPropagation()}>
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <SectionHead icon={FileSignature}>Upload a signed contract</SectionHead>
            <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
          </div>
          <div className="space-y-3">
            <label className="flex flex-col gap-1">
              <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Title *</span>
              <input value={f.title} onChange={e => set('title', e.target.value)} placeholder="Master Services Agreement"
                className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]" />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Type</span>
                <select value={f.contract_type} onChange={e => set('contract_type', e.target.value)}
                  className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]">
                  {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Status</span>
                <select value={f.status} onChange={e => set('status', e.target.value)}
                  className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]">
                  {['active', 'expired', 'terminated', 'draft'].map(x => <option key={x} value={x}>{x}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Counterparty</span>
                <input value={f.counterparty} onChange={e => set('counterparty', e.target.value)} placeholder="Tellumen Ltd"
                  className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Signed date</span>
                <input type="date" value={f.signed_date} onChange={e => set('signed_date', e.target.value)}
                  className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]" />
              </label>
            </div>
            <label className="flex flex-col gap-1">
              <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">File *</span>
              <input type="file" onChange={e => setFile(e.target.files?.[0] ?? null)}
                className="text-[12px] text-[var(--color-mute)] file:mr-3 file:rounded-md file:border-0 file:bg-[var(--color-panel-2)] file:px-3 file:py-1.5 file:text-[12px] file:text-[var(--color-ink)]" />
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" onClick={onClose}>Cancel</Button>
              <Button onClick={submit} disabled={busy}>{busy ? 'Uploading…' : 'Upload'}</Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[55vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
