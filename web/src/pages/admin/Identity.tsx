import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Building2, Pencil, Search } from 'lucide-react'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button, Card, SectionHead } from '../../components/ui'
import { Dialog } from '../../components/Dialog'
import { HEADING, InfoButton } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { Field, inp, refused } from './parts'
import type { Org } from './Overview'

// The reporting identity printed on filings. The card shows what is set and what is missing; Edit opens a dialog that
// can fill the name, identifier and address from the global LEI registry. A link to /admin?setup=identity (the
// readiness check "Complete your reporting identity") opens the dialog on the missing fields.

const ABOUT = {
  title: 'Reporting identity', sections: [
    { heading: HEADING.shows, body: 'The identity printed on your filings: legal name, legal entity identifier, customs number, filing contact and registered address.' },
    { heading: HEADING.read, body: 'A legal entity identifier is checked against the global LEI registry before it is saved, so a filing never carries an identifier the registry does not hold.' },
    { heading: HEADING.sources, body: 'The registry fills the legal name, identifier and registered address. The customs number and the filing contact are not in it and are typed in.' },
  ],
}
const FIELDS: [keyof Org, string][] = [['legal_name', 'Legal name'], ['lei', 'Legal entity identifier'], ['eori', 'Customs number (EORI)'],
  ['filing_contact_email', 'Filing contact'], ['operator_address', 'Registered address']]
type Form = Record<'legal_name' | 'lei' | 'eori' | 'filing_contact_email' | 'operator_address', string>

export function Identity({ org, onSaved }: { org: Org; onSaved: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const [params, setParams] = useSearchParams()
  const linked = params.get('setup') === 'identity'
  // the readiness check's link (/admin?setup=identity): open on what is missing — from another page or from this one
  useEffect(() => {
    if (!linked) return
    if (!(org.eori && org.filing_contact_email)) setOpen(true)
    setTimeout(() => ref.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 120)
  }, [linked])   // eslint-disable-line react-hooks/exhaustive-deps
  const close = () => {                  // the link has done its job: closing does not reopen on the next render
    setOpen(false)
    if (linked) { const next = new URLSearchParams(params); next.delete('setup'); setParams(next, { replace: true }) }
  }
  const set = FIELDS.filter(([k]) => org[k]).length

  return (
    <div ref={ref} className="scroll-mt-24">
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <SectionHead icon={Building2} className="gap-1.5">Reporting identity <InfoButton compact details={ABOUT} /></SectionHead>
          <button onClick={() => setOpen(true)} className="ml-auto inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Pencil size={13} /> Edit</button>
        </div>
        <div className="flex items-baseline gap-2 mb-3">
          <span className="text-[15px] font-semibold text-[var(--color-ink)]">{org.name}</span>
          <span className="text-[12px] text-[var(--color-faint)]">{[org.type_label, org.country].filter(Boolean).join(' · ')}</span>
        </div>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[13px] m-0">
          {FIELDS.map(([k, label]) => (
            <div key={k} className="contents">
              <dt className="text-[var(--color-mute)] whitespace-nowrap">{label}</dt>
              <dd className="m-0 text-right min-w-0 truncate" title={org[k] ?? undefined}>{org[k] ? <span className="text-[var(--color-ink)]">{org[k]}</span> : <StatusChip tone="warn" label="Not set" />}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-3 text-[12px] text-[var(--color-faint)] tabular-nums">{set} of {FIELDS.length} set</div>
      </Card>
      {open && <IdentityDialog org={org} onClose={close} onSaved={() => { close(); onSaved() }} />}
    </div>
  )
}

function IdentityDialog({ org, onClose, onSaved }: { org: Org; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<Form>({ legal_name: org.legal_name ?? '', lei: org.lei ?? '', eori: org.eori ?? '',
    filing_contact_email: org.filing_contact_email ?? '', operator_address: org.operator_address ?? '' })
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try { await api.patch('/v1/admin/organization', f); toast.success('Reporting identity saved.'); onSaved() }
    catch (e) { refused(e, 'The reporting identity could not be saved.') }
    finally { setBusy(false) }
  }
  return (
    <Dialog title="Reporting identity" onClose={onClose} className="max-w-xl">
      <div className="space-y-4">
        <RegistryLookup onPick={h => setF(x => ({ ...x, legal_name: h.legal_name, lei: h.lei, operator_address: h.address ?? x.operator_address }))} />
        <div className="grid sm:grid-cols-2 gap-3">
          {FIELDS.map(([k, label]) => (
            <Field key={k} label={label} className={k === 'operator_address' ? 'sm:col-span-2' : undefined}>
              <input className={inp} value={f[k as keyof Form]} onChange={e => setF({ ...f, [k]: e.target.value })} />
            </Field>
          ))}
        </div>
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
        </div>
      </div>
    </Dialog>
  )
}

interface Hit { lei: string; legal_name: string; country?: string; jurisdiction?: string; status?: string; address?: string }

// Fill the identity from the global LEI registry: search by legal name or a pasted identifier, pick the entity.
function RegistryLookup({ onPick }: { onPick: (h: Hit) => void }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<Hit[] | null>(null)
  const [busy, setBusy] = useState(false)
  const search = async () => {
    if (q.trim().length < 2) return
    setBusy(true)
    try { setHits((await api.get<{ results: Hit[] }>(`/v1/admin/registry/search?q=${encodeURIComponent(q.trim())}`)).results) }
    catch (e) { setHits(null); refused(e, 'The LEI registry could not be reached.') }
    finally { setBusy(false) }
  }
  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-3">
      <div className="text-[12.5px] text-[var(--color-ink)] mb-2 inline-flex items-center gap-1.5"><Search size={13} className="text-[var(--color-sky)]" /> Fill from the LEI registry</div>
      <div className="flex gap-2">
        <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()} aria-label="Legal name or identifier"
          placeholder="Legal name, or paste an identifier" className={inp} />
        <Button onClick={search} disabled={busy || q.trim().length < 2}>{busy ? 'Searching…' : 'Search'}</Button>
      </div>
      {hits && hits.length === 0 && <div className="text-[12px] text-[var(--color-faint)] mt-2">No match in the registry. Check the spelling, or type the details below.</div>}
      {hits && hits.length > 0 && (
        <div className="mt-2 flex flex-col gap-1 max-h-56 overflow-y-auto">
          {hits.map(h => (
            <button key={h.lei} onClick={() => onPick(h)} className="text-left rounded-lg border border-[var(--color-line)] px-3 py-2 hover:border-[var(--color-sky)] transition">
              <div className="text-[13px] text-[var(--color-ink)]">{h.legal_name}</div>
              <div className="text-[11.5px] text-[var(--color-faint)] truncate">{[h.lei, h.country || h.jurisdiction, h.address].filter(Boolean).join(' · ')}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
