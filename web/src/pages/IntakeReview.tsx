import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Rocket, Copy, FileText, Users, CheckCircle2, Building2, ArrowRight } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, PageHeader } from '../components/ui'

interface IntakeRow {
  intake_id: string; company_name: string; org_type: string; country: string | null; region: string
  status: string; contact_email: string; provisioned_org_id: string | null
  created_at: string | null; submitted_at: string | null; provisioned_at: string | null
  roster_count: number; document_count: number
}
interface RosterMember { roster_id: string; email: string; full_name: string | null; role: string; created_user_id: string | null }
interface DocRow { document_id: string; kind: string; title: string | null; filename: string | null; size_bytes: number; to_vault: boolean; contract_type: string | null }
interface IntakeDetail extends IntakeRow { legal_name: string | null; lei: string | null; filing_contact_email: string | null; modules: string[]; roster: RosterMember[]; documents: DocRow[]; notes: string | null }

const STATUS: Record<string, { label: string; cls: string }> = {
  draft: { label: 'Draft', cls: 'text-[var(--color-faint)] border-[var(--color-line-2)]' },
  invited: { label: 'Invited', cls: 'text-[var(--color-sky)] border-[var(--color-sky)]' },
  submitted: { label: 'Submitted', cls: 'text-[var(--color-warn)] border-[var(--color-warn)]' },
  in_review: { label: 'In review', cls: 'text-[var(--color-warn)] border-[var(--color-warn)]' },
  provisioned: { label: 'Provisioned', cls: 'text-[var(--color-good)] border-[var(--color-good)]' },
  rejected: { label: 'Rejected', cls: 'text-[var(--color-bad)] border-[var(--color-bad)]' },
}
function Pill({ status }: { status: string }) {
  const s = STATUS[status] ?? STATUS.draft
  return <span className={`mono text-[10px] uppercase tracking-wide border rounded px-1.5 py-0.5 ${s.cls}`}>{s.label}</span>
}
function msg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return (e.body as { error?: { message?: string } })?.error?.message ?? fallback
  return fallback
}

export default function IntakeReview() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['intakes'], queryFn: () => api.get<{ intakes: IntakeRow[] }>('/v1/onboarding/intakes') })
  const [showNew, setShowNew] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const refetch = () => qc.invalidateQueries({ queryKey: ['intakes'] })

  if (q.error) return <Center>Client intake is available to platform operators.</Center>
  const rows = q.data?.intakes ?? []

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Platform · onboarding" title="Client intake"
        lead="Every new client from signed contract to first login — capture their details, verify identity, and provision the tenant in one action."
        actions={<Button onClick={() => setShowNew(true)}><Plus size={15} /> New intake</Button>} />

      <Card className="p-0">
        {rows.length === 0 && <div className="p-8 text-center text-[var(--color-faint)] text-sm">No intakes yet. Start one with “New intake”.</div>}
        {rows.map((r, i) => (
          <button key={r.intake_id} onClick={() => setOpenId(r.intake_id)}
            className={`w-full text-left flex items-center gap-4 px-4 py-3 hover:bg-[var(--color-panel-2)] transition ${i > 0 ? 'border-t border-[var(--color-line)]' : ''}`}>
            <Building2 size={17} className="shrink-0 text-[var(--color-faint)]" />
            <div className="flex-1 min-w-0">
              <div className="text-[14px] text-[var(--color-ink)] truncate">{r.company_name}
                <span className="text-[var(--color-faint)] mono text-[11px]"> · {r.org_type.replace('_', ' ')} · {r.region}{r.country ? `/${r.country}` : ''}</span>
              </div>
              <div className="text-[12px] text-[var(--color-mute)]">{r.contact_email}</div>
            </div>
            <div className="shrink-0 mono text-[11px] text-[var(--color-faint)] hidden sm:flex items-center gap-3">
              <span className="inline-flex items-center gap-1"><Users size={12} />{r.roster_count}</span>
              <span className="inline-flex items-center gap-1"><FileText size={12} />{r.document_count}</span>
            </div>
            <Pill status={r.status} />
            <ArrowRight size={14} className="shrink-0 text-[var(--color-faint)]" />
          </button>
        ))}
      </Card>

      {showNew && <CreateIntakeModal onClose={() => setShowNew(false)} onCreated={refetch} />}
      {openId && <IntakeDrawer intakeId={openId} onClose={() => setOpenId(null)} onChanged={refetch} />}
    </div>
  )
}

function CreateIntakeModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [f, setF] = useState({ company_name: '', org_type: 'bank', contact_email: '', contact_name: '', region: 'EU' })
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<{ form_url: string } | null>(null)
  const set = (k: string, v: string) => setF(p => ({ ...p, [k]: v }))

  async function submit() {
    if (!f.company_name.trim() || !f.contact_email.trim()) { toast.error('Company name and contact email are required.'); return }
    setBusy(true)
    try {
      const r = await api.post<{ form_url: string }>('/v1/onboarding/intakes', f)
      setDone(r); onCreated()
    } catch (e) { toast.error(msg(e, 'Could not create the intake.')) } finally { setBusy(false) }
  }

  return (
    <Overlay onClose={onClose}>
      {done ? (
        <div>
          <div className="flex items-center gap-2 mb-2"><CheckCircle2 size={20} className="text-[var(--color-good)]" /><h2 className="display text-lg font-semibold m-0">Intake opened</h2></div>
          <p className="text-[13px] text-[var(--color-mute)] mb-4">Share this secure link with the client to complete their details and roster — or fill it in for them.</p>
          <CopyField value={done.form_url} />
          <div className="flex justify-end mt-5"><Button onClick={onClose}>Done</Button></div>
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between mb-4"><h2 className="display text-lg font-semibold m-0">New client intake</h2><button onClick={onClose}><X size={18} className="text-[var(--color-faint)]" /></button></div>
          <div className="space-y-3">
            <Field label="Company name"><input className={inp} value={f.company_name} onChange={e => set('company_name', e.target.value)} placeholder="Meridian Capital Partners" /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Sector"><select className={inp} value={f.org_type} onChange={e => set('org_type', e.target.value)}>
                {['bank', 'insurer', 'asset_manager', 'reit', 'manufacturer'].map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
              </select></Field>
              <Field label="Data residency"><select className={inp} value={f.region} onChange={e => set('region', e.target.value)}>
                <option value="EU">EU</option><option value="US">US</option>
              </select></Field>
            </div>
            <Field label="Client contact email"><input className={inp} value={f.contact_email} onChange={e => set('contact_email', e.target.value)} placeholder="cfo@company.com" /></Field>
            <Field label="Client contact name (optional)"><input className={inp} value={f.contact_name} onChange={e => set('contact_name', e.target.value)} placeholder="Dana Reyes" /></Field>
          </div>
          <div className="flex justify-end gap-2 mt-5">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={busy}>{busy ? 'Opening…' : 'Open intake →'}</Button>
          </div>
        </div>
      )}
    </Overlay>
  )
}

function IntakeDrawer({ intakeId, onClose, onChanged }: { intakeId: string; onClose: () => void; onChanged: () => void }) {
  const q = useQuery({ queryKey: ['intake', intakeId], queryFn: () => api.get<IntakeDetail>(`/v1/onboarding/intakes/${intakeId}`) })
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ org_name: string; region: string; users: { email: string; role: string; activation_url: string }[]; contracts_filed: number } | null>(null)
  const d = q.data

  async function provision() {
    setBusy(true)
    try {
      const r = await api.post<typeof result>(`/v1/onboarding/intakes/${intakeId}/provision`)
      setResult(r); onChanged(); toast.success('Tenant provisioned — activation links issued.')
    } catch (e) { toast.error(msg(e, 'Could not provision this intake.')) } finally { setBusy(false) }
  }

  return (
    <Overlay onClose={onClose} wide>
      {!d ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">loading…</div> : result ? (
        <div>
          <div className="flex items-center gap-2 mb-1"><Rocket size={20} className="text-[var(--color-good)]" /><h2 className="display text-lg font-semibold m-0">{result.org_name} is live</h2></div>
          <p className="text-[13px] text-[var(--color-mute)] mb-4">Region {result.region} · {result.contracts_filed} contract{result.contracts_filed !== 1 ? 's' : ''} filed to the vault · each user emailed a secure activation link.</p>
          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-2">Activation links</div>
          <div className="space-y-2">{result.users.map(u => (
            <div key={u.email} className="text-[12px]"><span className="text-[var(--color-ink)]">{u.email}</span> <span className="text-[var(--color-faint)]">· {u.role}</span><CopyField value={u.activation_url} small /></div>
          ))}</div>
          <div className="flex justify-end mt-5"><Button onClick={onClose}>Done</Button></div>
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between mb-1">
            <h2 className="display text-lg font-semibold m-0">{d.company_name}</h2>
            <button onClick={onClose}><X size={18} className="text-[var(--color-faint)]" /></button>
          </div>
          <div className="flex items-center gap-2 mb-4"><Pill status={d.status} /><span className="mono text-[11px] text-[var(--color-faint)]">{d.org_type.replace('_', ' ')} · {d.region}{d.country ? `/${d.country}` : ' · country pending'}</span></div>

          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[12px] mb-4">
            <KV k="Legal name" v={d.legal_name} /><KV k="LEI" v={d.lei} />
            <KV k="Contact" v={d.contact_email} /><KV k="Filing email" v={d.filing_contact_email} />
            <KV k="Modules" v={(d.modules || []).join(', ') || '—'} />
          </div>

          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-2 flex items-center gap-1"><Users size={12} /> Roster ({d.roster.length})</div>
          <Card className="p-0 mb-4">
            {d.roster.length === 0 && <div className="px-3 py-3 text-[12px] text-[var(--color-faint)]">No users yet — the client adds these on the intake form.</div>}
            {d.roster.map((m, i) => (
              <div key={m.roster_id} className={`flex items-center gap-3 px-3 py-2 text-[12px] ${i > 0 ? 'border-t border-[var(--color-line)]' : ''}`}>
                <span className="flex-1 text-[var(--color-ink)]">{m.full_name || m.email}</span>
                <span className="text-[var(--color-faint)]">{m.email}</span>
                <span className="mono text-[10px] uppercase border border-[var(--color-line-2)] rounded px-1.5 py-0.5 text-[var(--color-mute)]">{m.role}</span>
              </div>
            ))}
          </Card>

          {d.documents.length > 0 && <>
            <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-2 flex items-center gap-1"><FileText size={12} /> Documents ({d.documents.length})</div>
            <Card className="p-0 mb-4">{d.documents.map((doc, i) => (
              <div key={doc.document_id} className={`flex items-center gap-3 px-3 py-2 text-[12px] ${i > 0 ? 'border-t border-[var(--color-line)]' : ''}`}>
                <FileText size={13} className="text-[var(--color-faint)]" />
                <span className="flex-1 text-[var(--color-ink)] truncate">{doc.title || doc.filename}</span>
                {doc.to_vault && <span className="mono text-[10px] text-[var(--color-good)]">→ vault{doc.contract_type ? ` · ${doc.contract_type}` : ''}</span>}
                <span className="text-[var(--color-faint)]">{(doc.size_bytes / 1024).toFixed(0)} KB</span>
              </div>
            ))}</Card>
          </>}

          <div className="flex items-center justify-between mt-5 pt-4 border-t border-[var(--color-line)]">
            <p className="text-[12px] text-[var(--color-mute)] max-w-[60%]">
              {d.status === 'provisioned' ? 'This intake has been provisioned into a live tenant.'
                : !d.country ? 'Country is required before provisioning — ask the client to complete the intake form.'
                : d.roster.some(m => m.role === 'admin') ? 'Provisioning creates the tenant + all users and issues activation links.'
                : 'The roster needs at least one admin before provisioning.'}
            </p>
            <Button onClick={provision}
              disabled={busy || d.status === 'provisioned' || !d.country || !d.roster.some(m => m.role === 'admin')}>
              <Rocket size={15} /> {busy ? 'Provisioning…' : 'Provision tenant'}
            </Button>
          </div>
        </div>
      )}
    </Overlay>
  )
}

// ── small shared bits ────────────────────────────────────────────────────────
const inp = 'w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)]'
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">{label}</label>{children}</div>
}
function KV({ k, v }: { k: string; v: string | null }) {
  return <div><span className="text-[var(--color-faint)]">{k}: </span><span className="text-[var(--color-ink)]">{v || '—'}</span></div>
}
function CopyField({ value, small }: { value: string; small?: boolean }) {
  return (
    <div className={`flex items-center gap-2 ${small ? 'mt-1' : 'mt-1'}`}>
      <input readOnly value={value} className={`flex-1 bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 mono ${small ? 'text-[10px]' : 'text-[11px]'} text-[var(--color-mute)]`} />
      <button onClick={() => { navigator.clipboard?.writeText(value); toast.success('Copied') }} className="shrink-0 text-[var(--color-sky)] hover:text-[var(--color-blue)]"><Copy size={15} /></button>
    </div>
  )
}
function Overlay({ children, onClose, wide }: { children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4 bg-black/50" onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className={`w-full ${wide ? 'max-w-[560px]' : 'max-w-[440px]'} max-h-[88vh] overflow-y-auto`}>
        <Card className="p-5">{children}</Card>
      </div>
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[55vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
