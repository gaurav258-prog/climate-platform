import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, Trash2, CheckCircle2, Upload, FileText } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { BrandMark } from '../components/ui'

interface Loaded {
  intake_id: string; company_name: string; org_type: string; country: string | null; region: string
  legal_name: string | null; lei: string | null; filing_contact_email: string | null
  contact_name: string | null; modules: string[]; status: string
  roster: { email: string; full_name: string | null; role: string }[]
  documents: { document_id: string; title: string | null; filename: string | null; to_vault: boolean }[]
}
type Member = { email: string; full_name: string; role: string }
const ROLES = ['admin', 'analyst', 'approver', 'viewer']
function msg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return (e.body as { error?: { message?: string } })?.error?.message ?? fallback
  return fallback
}
const inp = 'w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)]'

export default function IntakeForm() {
  const { token = '' } = useParams()
  const [state, setState] = useState<'loading' | 'ready' | 'invalid' | 'done'>('loading')
  const [f, setF] = useState({ company_name: '', country: '', region: 'EU', legal_name: '', lei: '', filing_contact_email: '', aum_eur: '', employees: '' })
  const [roster, setRoster] = useState<Member[]>([{ email: '', full_name: '', role: 'admin' }])
  const [docs, setDocs] = useState<Loaded['documents']>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [orgType, setOrgType] = useState('')
  const set = (k: string, v: string) => setF(p => ({ ...p, [k]: v }))

  useEffect(() => {
    api.get<Loaded>(`/v1/onboarding/form/${token}`).then(d => {
      setOrgType(d.org_type)
      setF(p => ({
        ...p, company_name: d.company_name || '', country: d.country || '', region: d.region || 'EU',
        legal_name: d.legal_name || '', lei: d.lei || '', filing_contact_email: d.filing_contact_email || '',
      }))
      if (d.roster?.length) setRoster(d.roster.map(m => ({ email: m.email, full_name: m.full_name || '', role: m.role })))
      setDocs(d.documents || [])
      setState('ready')
    }).catch(() => setState('invalid'))
  }, [token])

  function addMember() { setRoster(r => [...r, { email: '', full_name: '', role: 'viewer' }]) }
  function setMember(i: number, k: keyof Member, v: string) { setRoster(r => r.map((m, j) => j === i ? { ...m, [k]: v } : m)) }
  function delMember(i: number) { setRoster(r => r.filter((_, j) => j !== i)) }

  async function uploadDoc(e: React.ChangeEvent<HTMLInputElement>, toVault: boolean) {
    const file = e.target.files?.[0]; if (!file) return
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('file', file); fd.append('kind', toVault ? 'contract' : 'other')
      fd.append('title', file.name); fd.append('to_vault', String(toVault))
      if (toVault) fd.append('contract_type', 'msa')
      const r = await api.post<{ document_id: string; filename: string }>(`/v1/onboarding/form/${token}/documents`, fd)
      setDocs(d => [...d, { document_id: r.document_id, title: file.name, filename: r.filename, to_vault: toVault }])
    } catch (er) { setErr(msg(er, 'Upload failed.')) } finally { setBusy(false); e.target.value = '' }
  }

  async function submit() {
    setErr(null)
    if (!f.country.trim()) { setErr('Country (ISO-2, e.g. IE) is required.'); return }
    const clean = roster.filter(m => m.email.includes('@'))
    if (!clean.some(m => m.role === 'admin')) { setErr('Add at least one admin user so your team can manage the account.'); return }
    setBusy(true)
    try {
      await api.put(`/v1/onboarding/form/${token}`, {
        ...f, aum_eur: f.aum_eur ? Number(f.aum_eur) : null, employees: f.employees ? Number(f.employees) : null,
        roster: clean, modules: undefined,
      })
      setState('done')
    } catch (e) { setErr(msg(e, 'Could not submit — please try again.')) } finally { setBusy(false) }
  }

  return (
    <Frame>
      {state === 'loading' && <p className="text-[var(--color-faint)] text-sm">Loading…</p>}
      {state === 'invalid' && <Panel title="This link is invalid or has expired"
        body="Onboarding links are valid for a limited time. Please ask your Tellumen contact to send a fresh one." />}
      {state === 'done' && <Panel icon title="Thank you — your details are in"
        body="Our team will review your submission and provision your workspace. Each user on your roster will receive a secure activation email to set their password and turn on two-factor authentication." />}
      {state === 'ready' && (
        <div className="space-y-6">
          <div>
            <div className="mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-blue)] mb-1">Client onboarding · {orgType.replace('_', ' ')}</div>
            <h1 className="display text-2xl font-semibold m-0">Tell us about {f.company_name || 'your organization'}</h1>
            <p className="text-[13px] text-[var(--color-mute)] mt-1">Complete your company details and the people who'll use Tellumen. It takes a couple of minutes.</p>
          </div>

          <Section title="Company">
            <Field label="Company name"><input className={inp} value={f.company_name} onChange={e => set('company_name', e.target.value)} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Country (ISO-2)"><input className={inp} value={f.country} onChange={e => set('country', e.target.value.toUpperCase().slice(0, 2))} placeholder="IE" /></Field>
              <Field label="Data residency"><select className={inp} value={f.region} onChange={e => set('region', e.target.value)}><option value="EU">EU</option><option value="US">US</option></select></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Legal name"><input className={inp} value={f.legal_name} onChange={e => set('legal_name', e.target.value)} /></Field>
              <Field label="LEI (optional)"><input className={inp} value={f.lei} onChange={e => set('lei', e.target.value)} placeholder="20-char LEI" /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Filing contact email"><input className={inp} value={f.filing_contact_email} onChange={e => set('filing_contact_email', e.target.value)} /></Field>
              <Field label="Employees (optional)"><input className={inp} value={f.employees} onChange={e => set('employees', e.target.value.replace(/\D/g, ''))} /></Field>
            </div>
          </Section>

          <Section title="Your team" hint="Everyone here gets an account when your workspace is provisioned.">
            <div className="space-y-2">
              {roster.map((m, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input className={inp + ' flex-1'} value={m.full_name} onChange={e => setMember(i, 'full_name', e.target.value)} placeholder="Full name" />
                  <input className={inp + ' flex-1'} value={m.email} onChange={e => setMember(i, 'email', e.target.value)} placeholder="email@company.com" />
                  <select className={inp + ' w-32'} value={m.role} onChange={e => setMember(i, 'role', e.target.value)}>{ROLES.map(r => <option key={r} value={r}>{r}</option>)}</select>
                  <button onClick={() => delMember(i)} className="shrink-0 text-[var(--color-faint)] hover:text-[var(--color-bad)] p-1"><Trash2 size={15} /></button>
                </div>
              ))}
            </div>
            <button onClick={addMember} className="mt-2 inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:text-[var(--color-blue)]"><Plus size={13} /> Add another person</button>
          </Section>

          <Section title="Documents" hint="Upload your signed contract and any required documents.">
            <div className="flex gap-2 flex-wrap">
              <label className="inline-flex items-center gap-1.5 text-[12px] cursor-pointer border border-[var(--color-line)] rounded-lg px-3 py-2 hover:border-[var(--color-sky)]">
                <FileText size={14} /> Signed contract<input type="file" className="hidden" onChange={e => uploadDoc(e, true)} />
              </label>
              <label className="inline-flex items-center gap-1.5 text-[12px] cursor-pointer border border-[var(--color-line)] rounded-lg px-3 py-2 hover:border-[var(--color-sky)]">
                <Upload size={14} /> Other document<input type="file" className="hidden" onChange={e => uploadDoc(e, false)} />
              </label>
            </div>
            {docs.length > 0 && <div className="mt-2 space-y-1">{docs.map(d => (
              <div key={d.document_id} className="text-[12px] text-[var(--color-mute)] flex items-center gap-2"><CheckCircle2 size={13} className="text-[var(--color-good)]" />{d.title || d.filename}{d.to_vault && <span className="mono text-[10px] text-[var(--color-good)]">· contract</span>}</div>
            ))}</div>}
          </Section>

          {err && <div className="text-[13px] text-[var(--color-bad)]">{err}</div>}
          <div className="flex justify-end">
            <button onClick={submit} disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium hover:bg-[var(--color-blue)] transition disabled:opacity-60">
              {busy ? 'Submitting…' : 'Submit for provisioning →'}
            </button>
          </div>
        </div>
      )}
    </Frame>
  )
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen px-6 py-10" style={{ background: 'radial-gradient(1200px 600px at 50% -10%, #0e1a30 0%, var(--color-bg) 60%)' }}>
      <div className="max-w-[620px] mx-auto">
        <div className="flex items-center gap-3 mb-8"><BrandMark size={34} />
          <div className="display text-xl font-semibold">Tel<span className="text-[var(--color-sky)]">lumen</span></div>
        </div>
        <div className="card p-6 fadeup">{children}</div>
      </div>
    </div>
  )
}
function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)] mb-0.5">{title}</div>
      {hint && <div className="text-[11px] text-[var(--color-faint)] mb-2.5">{hint}</div>}
      <div className="space-y-3">{children}</div>
    </div>
  )
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">{label}</label>{children}</div>
}
function Panel({ title, body, icon }: { title: string; body: string; icon?: boolean }) {
  return (
    <div className="text-center py-6">
      {icon && <CheckCircle2 size={36} className="text-[var(--color-good)] mx-auto mb-3" />}
      <h1 className="display text-xl font-semibold m-0">{title}</h1>
      <p className="text-[13px] text-[var(--color-mute)] mt-2 max-w-[42ch] mx-auto">{body}</p>
    </div>
  )
}
