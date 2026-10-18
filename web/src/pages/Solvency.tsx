import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { BookOpen, Building2, ListChecks, ShieldCheck } from 'lucide-react'
import InsurerDocuments from '../components/InsurerDocuments'
import MethodGap from '../components/MethodGap'
import { api } from '../lib/api'
import { balance, flow } from '../lib/money'
import { Card, Button, SectionHead, PageHeader, StatGrid } from '../components/ui'
import { HBar } from '../components/Charts'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, MessageLine } from '../components/Details'
import Waterfall from './solvency/Waterfall'
import PerilDrawer from './solvency/PerilDrawer'
import Methods from './solvency/Methods'
import IncurredLosses from './solvency/IncurredLosses'
import { PERILS, PERIL_COLOR, PERIL_LABEL, type Incurred, type PerilBlock, type ReinResp, type ScrResp, type SF } from './solvency/types'

// Catastrophe capital, to the UI standard (2026-10-16): the main screen is figures and charts — the standard-formula
// capital as a bridge from the five perils to what you hold, each peril by region one click away, the modelled 1-in-200
// gross to net, the incurred losses as bars; the method, the legal basis and every reason sit in pop-ups, in customer
// words from the server's message catalogue (codes solvency.*).

const ABOUT = [
  { heading: HEADING.shows, body: 'The capital your natural-catastrophe risk requires under the Solvency II standard formula — windstorm, earthquake, flood, hail and subsidence — before and after your reinsurance. Beside it, the 1-in-200 loss our catastrophe model gives for your book.' },
  { heading: HEADING.read, body: 'The standard formula is the regulatory figure: fixed factors per region, for five perils only. The modelled 1-in-200 covers every climate hazard your book is scored on, at the severity your stated method sets; it is context, not an approved internal model. The two differ in scope and can differ a lot, and comparing them is itself a useful check.' },
  { heading: HEADING.sources, body: 'Your Statement of Values (each property’s sum insured, country and postal code), the reinsurance treaty and premiums you attest, and the factor, zone and correlation tables of the Regulation in the version in force on your reporting date.' },
  { heading: 'Legal basis', body: 'Delegated Regulation (EU) 2015/35, Articles 90b and 119 to 126; reported on template S.27.01.01 (Implementing Regulation (EU) 2023/894). Details under Methods and legal basis.' },
  { heading: HEADING.limits, body: 'A figure that needs an input you have not stated is shown as missing, never as zero. Man-made catastrophe is outside climate scope.' },
]
const Q = '?scenario=baseline&horizon=current'

export default function Solvency() {
  const scr = useQuery({ queryKey: ['ins-scr'], queryFn: () => api.get<ScrResp>(`/v1/insurance/solvency-scr${Q}`) })
  const reins = useQuery({ queryKey: ['ins-reins'], queryFn: () => api.get<ReinResp>(`/v1/insurance/reinsurance/attested${Q}`) })
  const incurred = useQuery({ queryKey: ['ins-incurred'], queryFn: () => api.get<Incurred>(`/v1/insurance/incurred-losses${Q}`) })
  const [methods, setMethods] = useState(false)
  const [peril, setPeril] = useState<PerilBlock | null>(null)
  const d = scr.data
  const sf = d?.standard_formula_natcat
  const header = (
    <PageHeader eyebrow="Assess · Solvency II" title="Catastrophe capital" lead="The capital your catastrophe risk needs, beside our modelled loss." about={ABOUT}
      actions={<Button variant="ghost" onClick={() => setMethods(true)}><BookOpen size={14} className="inline -mt-0.5 mr-1" />Methods and legal basis</Button>} />
  )
  const body = scr.isLoading ? <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div>
    : !d ? <div className="text-[12.5px] text-[var(--color-warn)]">The figures could not be loaded. Try again shortly.</div>
    : !d.available && !sf?.available ? (
      <Card className="p-5 text-[13px] text-[var(--color-mute)]">No insured properties are scored yet. <Link to="/data" className="text-[var(--color-sky)] hover:underline">Upload your Statement of Values</Link></Card>
    ) : (
      <>
        <Headline d={d} sf={sf} rein={reins.data} />
        <div className="grid gap-4 lg:grid-cols-2 items-start">
          <StandardFormula sf={sf} onPeril={setPeril} />
          <Modelled d={d} rein={reins.data} />
        </div>
      </>
    )
  return (
    <div className="fadeup space-y-6 max-w-5xl">
      {header}
      {body}
      <InsurerDocuments />
      <IncurredLosses data={incurred.data} loading={incurred.isLoading} onSaved={() => incurred.refetch()} />
      {methods && <Methods sf={sf} onClose={() => setMethods(false)} />}
      {peril && <PerilDrawer b={peril} onClose={() => setPeril(null)} />}
    </div>
  )
}

function Headline({ d, sf, rein }: { d: ScrResp; sf?: SF; rein?: ReinResp }) {
  const missing = sf?.missing?.length ?? 0
  const w = rein?.one_in_200
  return (
    <StatGrid cols={4} items={[
      { label: 'Capital required', value: sf?.available ? balance(sf.natcat_scr_eur) : '—', sub: 'standard formula, after reinsurance', accent: 'var(--color-sky)' },
      { label: 'Modelled 1-in-200 loss', value: d.available ? balance(d.modelled_1_in_200_loss_eur) : 'Needs input', sub: 'gross of reinsurance' },
      { label: 'Net of reinsurance', value: w ? balance(w.net_eur) : rein?.message ? 'No treaty' : '—', sub: 'modelled 1-in-200' },
      { label: 'Inputs still needed', value: !sf?.available ? '—' : missing ? String(missing) : 'None', sub: 'standard formula', accent: missing ? 'var(--color-warn)' : undefined },
    ]} />
  )
}

function StandardFormula({ sf, onPeril }: { sf?: SF; onPeril: (b: PerilBlock) => void }) {
  if (!sf?.available) return (
    <Card className="p-5"><SectionHead icon={ShieldCheck}>Standard formula</SectionHead>
      <div className="mt-3 text-[12.5px] text-[var(--color-mute)]">None of your properties is in a region the standard formula charges.</div></Card>
  )
  const on = PERILS.map(k => sf.perils?.[k]).filter((b): b is PerilBlock => !!b?.available)
  const added = on.reduce((a, b) => a + (b.before_eur ?? 0), 0)
  const before = sf.natcat_scr_before_mitigation_eur ?? 0, after = sf.natcat_scr_eur ?? 0
  const bars = on.filter(b => (b.after_eur ?? 0) > 0).sort((a, b) => (b.after_eur ?? 0) - (a.after_eur ?? 0))
  return (
    <Card className="p-5 space-y-5">
      <div className="flex items-center justify-between gap-2">
        <SectionHead icon={ShieldCheck}>Standard formula</SectionHead>
        <StatusChip label={sf.complete ? 'Complete' : 'Inputs missing'} tone={sf.complete ? 'good' : 'warn'} />
      </div>
      <Waterfall label="From the five perils to the capital required" steps={[
        { label: 'Perils, added up', value: added, total: true },
        { label: 'Diversification between perils', value: -(sf.diversification_between_perils_before_eur ?? 0) },
        { label: 'Before reinsurance', value: before, total: true },
        { label: 'Reinsurance', value: after - before, below: sf.treaty_message ? <MessageLine m={sf.treaty_message} /> : undefined },
        { label: 'Capital required', value: after, total: true },
      ]} />
      <div>
        <div className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] mb-2">By peril, after reinsurance
          <InfoButton compact details={{ title: 'Capital by peril', sections: [{ heading: HEADING.read, body: 'Each peril’s capital after diversification between its regions. Open a peril to see its regions and how each was charged.' }] }} /></div>
        <HBar data={bars.map(b => ({ label: PERIL_LABEL[b.peril], value: b.after_eur ?? 0, color: PERIL_COLOR[b.peril] }))} format={v => balance(v)} onBar={i => onPeril(bars[i])} labelWidth="w-24" />
      </div>
      {!!sf.missing?.length && (
        <div>
          <div className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] mb-2"><ListChecks size={13} />Still needed</div>
          <ul className="m-0 p-0 list-none space-y-1.5">
            {sf.missing.map((m, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-x-3 text-[12.5px]">
                <MessageLine m={m} className="text-[var(--color-warn)]" />
                <span className="text-[11.5px] text-[var(--color-faint)] tabular-nums">{balance(m.uncharged_eur)} not charged</span>
              </li>
            ))}
          </ul>
          <Link to="/data" className="inline-block mt-2 text-[12px] text-[var(--color-sky)] hover:underline">Add them under Your data</Link>
        </div>
      )}
    </Card>
  )
}

function Modelled({ d, rein }: { d: ScrResp; rein?: ReinResp }) {
  const w = rein?.one_in_200
  const about = [
    { heading: HEADING.shows, body: 'The loss of the worst year in 200 (99.5 %) from our catastrophe simulation of your book, on the damage ratios and event probabilities your organisation states, before and after your attested treaty.' },
    { heading: HEADING.read, body: 'It covers every climate hazard your book is scored on, not only the five perils of the standard formula. It is context, not an approved internal model.' },
    ...(rein?.gross_pml_eur != null && rein.net?.net_pml_eur != null ? [{ heading: 'Largest single event', body: `In the worst year in ${rein.pml_return_period ?? 200}, the largest single event costs ${balance(rein.gross_pml_eur)} gross and ${balance(rein.net.net_pml_eur)} net of reinsurance.` }] : []),
    { heading: HEADING.limits, body: 'Reinsurance is applied event by event: the quota share on every loss, the excess of loss on each event. Reinstatements are taken as unlimited; their premiums and any aggregate cover are not modelled here.' },
  ]
  return (
    <Card className="p-5 space-y-5">
      <div className="flex items-center gap-2">
        <SectionHead icon={Building2}>Modelled 1-in-200</SectionHead>
        <InfoButton compact details={{ title: 'Modelled 1-in-200 loss', sections: about }} />
      </div>
      {!d.available ? <MethodGap gap={d.gap ?? d.reason} what="Modelled 1-in-200" /> : <>
        {w ? <Waterfall label="The 1-in-200 loss, gross to net of reinsurance" steps={[
          { label: 'Gross loss', value: w.gross_eur, total: true },
          { label: 'Reinsurance', value: -w.reinsurance_eur },
          { label: 'Net loss', value: w.net_eur, total: true },
        ]} /> : (
          <div>
            <div className="display text-[26px] tabular-nums">{balance(d.modelled_1_in_200_loss_eur)}</div>
            <div className="text-[11.5px] text-[var(--color-faint)] mt-1">gross of reinsurance</div>
            {rein?.message && <MessageLine m={rein.message} className="mt-2 text-[12.5px] text-[var(--color-warn)]" />}
          </div>
        )}
        <StatGrid cols={3} items={[
          { label: 'Mean yearly loss', value: flow(d.mean_annual_loss_eur) },
          { label: 'Risk load', value: d.risk_load_eur != null ? balance(d.risk_load_eur) : '—', sub: '1-in-200 less the mean' },
          { label: 'Of sum insured', value: d.scr_pct_of_sum_insured != null ? `${d.scr_pct_of_sum_insured.toFixed(1)}%` : '—', sub: '1-in-200, gross' },
        ]} />
      </>}
    </Card>
  )
}
