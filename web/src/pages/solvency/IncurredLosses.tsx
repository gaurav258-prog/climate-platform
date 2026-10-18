import { useState } from 'react'
import { FileClock, Plus } from 'lucide-react'
import MoneyDeclaration from '../../components/MoneyDeclaration'
import { Card, Button, SectionHead, StatGrid } from '../../components/ui'
import { HBar } from '../../components/Charts'
import { Dialog } from '../../components/Dialog'
import { HEADING, InfoButton, MessageLine, type Message } from '../../components/Details'
import { api, apiDetail, apiMessage } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { flow } from '../../lib/money'
import { toast } from '../../lib/toast'
import { actionLabel, hazardLabel } from '../../lib/labels'
import { HAZARD_LABEL } from '../../lib/hazards'
import type { Incurred } from './types'

// Actual catastrophe losses for a past period (IFRS S2 paragraph 16(a)), beside the modelled figures above: the claims
// come from the insurer, so the card says plainly when none are on file; every split is a bar.
const ABOUT = [
  { heading: HEADING.shows, body: 'The catastrophe claims your book actually incurred in a past reporting period, before and after reinsurance, by peril, by region and by whether the catastrophe was modelled.' },
  { heading: HEADING.read, body: 'These are actual losses. The capital and the modelled 1-in-200 loss above look forward; the two are shown side by side and are not meant to match.' },
  { heading: HEADING.sources, body: 'Your own claims records, submitted here. The platform cannot see your claims ledger.' },
  { heading: 'Legal basis', body: 'IFRS S2, paragraph 16(a), current financial effects; the split by region and by modelled catastrophe follows the SASB insurance standard FN-IN-450a.2, to which IFRS S2 paragraph 29 points.' },
]
const EAL = [
  { heading: HEADING.shows, body: 'The expected yearly catastrophe loss of your book from the pricing model: each policy’s expected loss, added up.' },
  { heading: HEADING.read, body: 'It is worked out per policy, so it differs a little from the mean yearly loss of the catastrophe simulation in the modelled card. Both look forward (IFRS S2 paragraph 16(c) and (d)).' },
]

const month = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
// a period in a few words: '2025' for a calendar year, else 'Apr 2025 – Mar 2026'
const periodText = (a: string, b: string) => a.slice(5) === '01-01' && b.slice(5) === '12-31' && a.slice(0, 4) === b.slice(0, 4) ? a.slice(0, 4) : `${month(a)} – ${month(b)}`

export default function IncurredLosses({ data, loading, onSaved }: { data?: Incurred; loading: boolean; onSaved: () => void }) {
  const { profile } = useAuth()
  const canSubmit = (profile?.permissions ?? []).includes('pricing.approve')
  const [adding, setAdding] = useState(false)
  const supplied = data?.status === 'supplied'
  const periods = data?.by_period ?? []
  const span = periods.length === 1 ? periodText(periods[0].period_start, periods[0].period_end) : `${periods.length} periods`
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <SectionHead icon={FileClock}>Incurred catastrophe losses</SectionHead>
          <InfoButton compact details={{ title: 'Incurred catastrophe losses', sections: ABOUT }} />
        </div>
        {canSubmit ? <Button variant="ghost" onClick={() => setAdding(true)}><Plus size={14} />Add incurred loss</Button> : (
          <span className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-faint)]">Your role cannot add losses
            <InfoButton compact details={{ title: 'Who can add losses', sections: [{ heading: HEADING.shows,
              body: `Adding an incurred loss needs the permission “${actionLabel('pricing.approve')}”. By default the Admin, Analyst and Approver roles hold it; your administrator can give it to another role.` }] }} />
          </span>
        )}
      </div>
      {loading ? <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div>
        : !supplied ? (data?.message ? <MessageLine m={data.message} className="text-[12.5px] text-[var(--color-mute)]" /> : null) : (
          <div className="space-y-5">
            <StatGrid cols={3} items={[
              { label: 'Gross incurred', value: flow(data!.total_gross_incurred_loss_eur), accent: 'var(--color-warn)', sub: span },
              { label: 'Net of reinsurance', value: data!.total_net_incurred_loss_eur != null ? flow(data!.total_net_incurred_loss_eur) : 'Not given' },
              { label: <span className="inline-flex items-center gap-1">Expected yearly loss<InfoButton compact details={{ title: 'Expected yearly loss', sections: EAL }} /></span>,
                value: flow(data!.modeled?.total_expected_annual_loss_eur), sub: 'modelled' },
            ]} />
            {data!.comparison && <MessageLine m={data!.comparison} className="text-[12px] text-[var(--color-mute)]" />}
            <div className="grid gap-5 md:grid-cols-3">
              <Split title="By peril" bars={data!.by_peril.map(p => ({ label: hazardLabel(p.peril), value: p.gross_incurred_loss_eur, color: 'var(--color-warn)' }))} />
              {!!(data!.by_region?.length || data!.region_coverage) && (
                <Split title="By region" bars={(data!.by_region ?? []).map(r => ({ label: r.region, value: r.gross_incurred_loss_eur, color: 'var(--color-sky)' }))} gap={data!.region_coverage} />
              )}
              {!!(data!.by_modelled?.length || data!.modelled_coverage) && (
                <Split title="Modelled or not" bars={(data!.by_modelled ?? []).map(m => ({ label: m.modelled === 'modelled' ? 'Modelled' : 'Not modelled', value: m.gross_incurred_loss_eur, color: 'var(--color-slate)' }))} gap={data!.modelled_coverage} />
              )}
            </div>
          </div>
        )}
      {adding && <AddLoss onClose={() => setAdding(false)} onSaved={() => { setAdding(false); onSaved() }} />}
    </Card>
  )
}

function Split({ title, bars, gap }: { title: string; bars: { label: string; value: number; color: string }[]; gap?: Incurred['region_coverage'] }) {
  return (
    <div>
      <div className="text-[12px] text-[var(--color-mute)] mb-2">{title} · gross</div>
      {bars.length > 0 && <HBar data={bars} format={v => flow(v)} labelWidth="w-28" />}
      {gap && <MessageLine m={gap} className="mt-2 text-[11.5px] text-[var(--color-faint)]" />}
    </div>
  )
}

const field = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
const L = ({ t, children }: { t: string; children: React.ReactNode }) => <label className="block text-[12px] text-[var(--color-mute)]">{t}<div className="mt-1">{children}</div></label>

function AddLoss({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const perils = Object.keys(HAZARD_LABEL)
  const last = new Date().getFullYear() - 1          // the last full calendar year: a period must have ended
  const [peril, setPeril] = useState(perils.includes('flood') ? 'flood' : perils[0])
  const [periodStart, setPeriodStart] = useState(`${last}-01-01`)
  const [periodEnd, setPeriodEnd] = useState(`${last}-12-31`)
  const [ccy, setCcy] = useState('')
  const [gross, setGross] = useState('')
  const [net, setNet] = useState('')
  const [region, setRegion] = useState('')
  const [modelled, setModelled] = useState('')       // '' not said · 'true' · 'false'
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Message | null>(null)       // a refusal: its label, its detail behind ⓘ
  const submit = async () => {
    setErr(null)
    if (!gross || Number(gross) < 0) return setErr({ label: 'Enter the gross incurred loss.' })
    if (!ccy) return setErr({ label: 'Choose the currency of the losses.' })
    if (periodEnd < periodStart) return setErr({ label: 'The period ends before it starts.' })
    setBusy(true)
    try {
      await api.post('/v1/insurance/incurred-losses', {
        period_start: periodStart, period_end: periodEnd, peril, currency: ccy, source: 'client',
        gross_incurred_loss_eur: Number(gross), net_incurred_loss_eur: net ? Number(net) : undefined,
        region: region || undefined, modelled: modelled === '' ? undefined : modelled === 'true',
      })
      toast.success('Incurred loss saved.')
      onSaved()
    } catch (e) { setErr({ label: apiMessage(e, 'Could not save the incurred loss.'), detail: apiDetail(e) }) } finally { setBusy(false) }
  }
  return (
    <Dialog title="Add an incurred loss" onClose={onClose} className="max-w-xl">
      <div className="space-y-3">
        {err && <MessageLine m={err} className="text-[12.5px] text-[var(--color-bad)]" />}
        <div className="grid grid-cols-2 gap-3">
          <L t="Peril"><select value={peril} onChange={e => setPeril(e.target.value)} className={field}>{perils.map(p => <option key={p} value={p}>{HAZARD_LABEL[p]}</option>)}</select></L>
          <L t="Modelled catastrophe?"><select value={modelled} onChange={e => setModelled(e.target.value)} className={field}>
            <option value="">Not said</option><option value="true">Modelled</option><option value="false">Not modelled</option></select></L>
          <L t="Period from"><input type="date" value={periodStart} onChange={e => setPeriodStart(e.target.value)} className={field} /></L>
          <L t="Period to"><input type="date" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)} className={field} /></L>
          <L t="Gross loss"><input type="number" min={0} value={gross} onChange={e => setGross(e.target.value)} className={field} /></L>
          <L t="Net of reinsurance (optional)"><input type="number" min={0} value={net} onChange={e => setNet(e.target.value)} className={field} /></L>
          <L t="Region (optional)"><input type="text" placeholder="e.g. Germany" value={region} onChange={e => setRegion(e.target.value)} className={field} /></L>
        </div>
        <MoneyDeclaration currency={ccy} setCurrency={setCcy} withDate={false} note="Converted to euros at the average rate over the period." />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Save loss'}</Button>
        </div>
      </div>
    </Dialog>
  )
}
