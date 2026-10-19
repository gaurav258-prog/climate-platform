import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pencil, ShieldCheck } from 'lucide-react'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button, Card, SectionHead } from '../../components/ui'
import { Dialog } from '../../components/Dialog'
import { HEADING, InfoButton } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { useCurrencies } from '../../components/MoneyDeclaration'
import { Field, inp, refused } from './parts'
import { savedWords } from './words'

// The reporting basis every report is computed on. The scenarios and horizons offered are the platform's own, named
// by the server (services/governance/admin_view.basis_options) — the screen never types its own list.

type Option = { value: string; label: string }
interface Settings { scenario: string; horizon: string; reporting_period_end: string; presentation_currency: string; is_override: boolean
  options: { scenario: Option[]; horizon: Option[] } }

const ABOUT = {
  title: 'Reporting basis', sections: [
    { heading: HEADING.shows, body: 'The basis every report is computed on: the period end, the climate scenario, the time horizon and the currency group figures are presented in.' },
    { heading: HEADING.read, body: 'What counts as material physical risk is not set here: it is your stated at-risk threshold for the year, set under Methodology and attested by a second person. The minimum fit a crop model needs before it is published is fixed and cannot be changed.' },
    { heading: HEADING.limits, body: 'Each legal entity files in its own currency, set on the Entities tab. A change may wait for a second person, as set in the approval matrix.' },
  ],
}
// a value stored before the choices were checked, and not one the platform models, says so rather than printing a code
const nameOf = (opts: Option[], v: string) => opts.find(o => o.value === v)?.label ?? 'Not one the platform models'

export function Basis() {
  const q = useQuery({ queryKey: ['reporting-settings'], queryFn: () => api.get<Settings>('/v1/admin/reporting-settings') })
  const [open, setOpen] = useState(false)
  const d = q.data
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <SectionHead icon={ShieldCheck} className="gap-1.5">Reporting basis <InfoButton compact details={ABOUT} /></SectionHead>
        {d && <button onClick={() => setOpen(true)} className="ml-auto inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Pencil size={13} /> Edit</button>}
      </div>
      {!d ? <div className="text-[13px] text-[var(--color-faint)] py-2">Loading…</div> : (<>
        <div className="grid grid-cols-2 gap-3">
          <Value label="Period end" value={d.reporting_period_end} />
          <Value label="Presentation currency" value={d.presentation_currency} />
          <Value label="Scenario" value={nameOf(d.options.scenario, d.scenario)} />
          <Value label="Horizon" value={nameOf(d.options.horizon, d.horizon)} />
        </div>
        <div className="mt-3"><StatusChip tone={d.is_override ? 'good' : 'neutral'} label={d.is_override ? 'Set for your organisation' : 'Platform defaults'} /></div>
      </>)}
      {open && d && <BasisDialog d={d} onClose={() => setOpen(false)} onSaved={async () => {
        setOpen(false)
        const r = await q.refetch()
        // the screens read the presentation currency once at sign-in: reload so every amount shows in the new one
        if (r.data && r.data.presentation_currency !== d.presentation_currency) window.location.reload()
      }} />}
    </Card>
  )
}

function Value({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-line)] px-3 py-2.5">
      <div className="text-[11.5px] text-[var(--color-mute)]">{label}</div>
      <div className="text-[14px] text-[var(--color-ink)] mt-0.5 tabular-nums">{value}</div>
    </div>
  )
}

function BasisDialog({ d, onClose, onSaved }: { d: Settings; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ scenario: d.scenario, horizon: d.horizon, reporting_period_end: d.reporting_period_end, presentation_currency: d.presentation_currency })
  const [busy, setBusy] = useState(false)
  const currencies = useCurrencies()
  const save = async () => {
    setBusy(true)
    try {
      const r = await api.patch<{ status?: string }>('/v1/admin/reporting-settings', f)
      toast.success(savedWords(r?.status, 'Reporting basis saved — new reports use it.'))
      onSaved()
    } catch (e) { refused(e, 'The reporting basis could not be saved.') } finally { setBusy(false) }
  }
  return (
    <Dialog title="Reporting basis" onClose={onClose}>
      <div className="space-y-4">
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Period end"><input type="date" className={inp} value={f.reporting_period_end} onChange={e => setF({ ...f, reporting_period_end: e.target.value })} /></Field>
          <Field label="Presentation currency">
            <select className={inp} value={f.presentation_currency} onChange={e => setF({ ...f, presentation_currency: e.target.value })}>{currencies.map(c => <option key={c} value={c}>{c}</option>)}</select>
          </Field>
          <Field label="Scenario">
            <select className={inp} value={f.scenario} onChange={e => setF({ ...f, scenario: e.target.value })}>{d.options.scenario.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          </Field>
          <Field label="Horizon">
            <select className={inp} value={f.horizon} onChange={e => setF({ ...f, horizon: e.target.value })}>{d.options.horizon.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          </Field>
        </div>
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save basis'}</Button>
        </div>
      </div>
    </Dialog>
  )
}
