import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CircleHelp, Minus, Send } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { money } from '../lib/money'
import { Button, Card, PageHeader, StatGrid } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import { CloseButton } from '../components/Dialog'
import { Drawer } from '../components/Drawer'
import { HEADING, InfoButton } from '../components/Details'
import { pressable } from '../lib/pressable'
import { Facts, Failed, Loading, Segmented, day, shows } from './supervisorDesk/common'
import { MandateRegistry } from './supervisorDesk/MandateRegistry'
import { Deadlines } from './supervisorDesk/Deadlines'

// Mandates and who they apply to (UI standard, 2026-10-16): the registry as cards (each act's text in its drawer), the
// population as a matrix of entity × mandate with the result as a chip (an entity's attributes and checks in its
// drawer), and the authority's deadlines. Criteria are configuration in the mandate registry; never a guess.
interface Check { label: string; attribute: string; result: boolean | null; tier?: string }
interface Cell { mandate_id: string; short: string; status: 'applies' | 'not_applicable' | 'cannot_determine'; status_label: string
  missing: string[]; tier: { label: string } | null; tier_frequency_label: string | null; checks: Check[]; due_date: string | null }
interface Ent { org_id: string; name: string; sector_label: string; country_name: string | null; mandates: Cell[]; n_applies: number; missing: string[]
  attributes: Record<string, { value: unknown; value_label: string | null; source_label: string | null; as_of: string | null }> }
interface PopResp { period_end: string; mandates: { id: string; short: string; title: string }[]; entities: Ent[]
  attributes: Record<string, { label: string; type: string; unit?: string }>; summary: { entities: number; cannot_determine: number; attributes_missing: number } }
type Tab = 'registry' | 'population' | 'deadlines'

const TONE: Record<Cell['status'], 'good' | 'warn' | 'neutral'> = { applies: 'good', cannot_determine: 'warn', not_applicable: 'neutral' }
const value = (v: unknown, unit?: string) => v == null ? '—' : typeof v === 'boolean' ? (v ? 'Yes' : 'No')
  : typeof v === 'number' ? (unit === 'eur' ? money(v, 'EUR') : v.toLocaleString()) : String(v)
const usePopulation = () => useQuery({ queryKey: ['sup-pop-mandates'], queryFn: () => api.get<PopResp>('/v1/supervisor/population/mandates') })

export default function SupervisorMandates() {
  const [params, setParams] = useSearchParams()
  const t = params.get('tab')
  const tab: Tab = t === 'population' || t === 'deadlines' ? t : 'registry'
  const pop = usePopulation()
  const applicability = useMemo(() => (pop.data?.entities ?? []).flatMap(e => e.mandates.map(c => ({ mandate_id: c.mandate_id, status: c.status }))), [pop.data])
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Regulations" title="Mandates and who they apply to" lead="Each act, who it applies to, and by when."
        about={[shows('The regulations your authority works under: the article, who it applies to, what must be delivered, through which channel and by when; then each entity in your population against those criteria, and your filing deadlines.')]} />
      <Segmented label="View" value={tab} onChange={k => { const p = new URLSearchParams(params); p.set('tab', k); setParams(p) }}
        options={[['registry', 'Registry'], ['population', 'Who is regulated'], ['deadlines', 'Deadlines']]} />
      {tab === 'registry' ? <MandateRegistry applicability={applicability} /> : tab === 'population' ? <Population /> : <Deadlines />}
    </div>
  )
}

function Population() {
  const q = usePopulation()
  const [sel, setSel] = useState<string | null>(null)
  const d = q.data
  if (q.isLoading) return <Loading what="who is regulated" />
  if (!d) return <Failed what="who is regulated" />
  const e = d.entities.find(x => x.org_id === sel)
  return (<>
    <StatGrid cols={3} items={[
      { label: 'Entities judged', value: String(d.summary.entities), sub: `year ending ${day(d.period_end)}` },
      { label: 'Cannot be determined', value: String(d.summary.cannot_determine), sub: 'an attribute is missing', accent: d.summary.cannot_determine ? 'var(--color-warn)' : undefined },
      { label: 'Attributes to ask for', value: String(d.summary.attributes_missing), sub: 'one request per entity' },
    ]} />
    <Card className="p-5">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <StatusChip label="Applies" tone="good" /><StatusChip label="Cannot be determined" tone="warn" /><StatusChip label="Does not apply" tone="neutral" />
        <InfoButton compact className="ml-1" details={{ title: 'How to read it', sections: [{ heading: HEADING.read,
          body: "Each cell is one mandate's criteria judged on the entity's regulatory attributes. Where an attribute is missing the result cannot be determined until the entity states it; an entity opens its attributes and every check." }] }} />
      </div>
      <div className="overflow-x-auto">
        <table className="data-table w-full text-[12.5px]">
          <thead><tr className="text-left"><th>Entity</th>{d.mandates.map(m => <th key={m.id} className="text-center" title={m.title}>{m.short}</th>)}<th>Missing</th></tr></thead>
          <tbody>{d.entities.map(x => (
            <tr key={x.org_id} {...pressable(() => setSel(x.org_id), { row: true })} className="border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)]">
              <td className="whitespace-nowrap"><span className="block text-[var(--color-ink)]">{x.name}</span>
                <span className="block text-[11px] text-[var(--color-faint)]">{x.sector_label}{x.country_name ? ` · ${x.country_name}` : ''}</span></td>
              {d.mandates.map(m => { const c = x.mandates.find(y => y.mandate_id === m.id); return (
                <td key={m.id} className="text-center">{c ? <StatusChip tone={TONE[c.status]}
                  label={c.status === 'applies' ? (c.tier_frequency_label ?? 'Applies') : c.status === 'cannot_determine' ? 'Unknown' : 'No'} /> : <span className="text-[var(--color-faint)]">·</span>}</td>) })}
              <td>{x.missing.length ? <StatusChip label={`${x.missing.length} to ask`} tone="warn" /> : <span className="text-[var(--color-faint)]">—</span>}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </Card>
    {e && <EntityDrawer e={e} d={d} onClose={() => setSel(null)} />}
  </>)
}

function EntityDrawer({ e, d, onClose }: { e: Ent; d: PopResp; onClose: () => void }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canAsk = (profile?.permissions ?? []).includes('supervisor.requests.manage')
  const [busy, setBusy] = useState(false)
  const ask = async () => {
    setBusy(true)
    try { await api.post('/v1/supervisor/population/mandates/ask', { supervised_org_id: e.org_id, attributes: e.missing }); toast.success(`Asked ${e.name} for the missing attributes.`); await qc.invalidateQueries({ queryKey: ['supervisor-requests'] }) }
    catch (err) { toast.error(apiMessage(err, 'Could not send the request.')) } finally { setBusy(false) }
  }
  const icon = (r: boolean | null) => r == null ? <CircleHelp size={13} className="text-[var(--color-warn)] shrink-0" /> : r ? <Check size={13} className="text-[var(--color-good)] shrink-0" /> : <Minus size={13} className="text-[var(--color-faint)] shrink-0" />
  return (
    <Drawer label={e.name} onClose={onClose} className="w-full max-w-xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0"><div className="text-[12px] text-[var(--color-mute)]">{e.sector_label}{e.country_name ? ` · ${e.country_name}` : ''}</div>
          <Link to={`/supervised/${e.org_id}`} className="text-[16px] font-semibold text-[var(--color-ink)] hover:text-[var(--color-sky)] hover:underline">{e.name}</Link></div>
        <CloseButton onClick={onClose} />
      </div>
      {e.missing.length > 0 && <div className="flex items-center gap-3 flex-wrap mb-5 text-[12.5px]">
        <StatusChip label={`${e.missing.length} attributes missing`} tone="warn" />
        {canAsk && <Button disabled={busy} onClick={ask}><Send size={14} />Ask the entity</Button>}</div>}
      <div className="text-[12px] text-[var(--color-mute)] mb-2">Mandate by mandate</div>
      <div className="space-y-3 mb-6">{e.mandates.map(c => (
        <div key={c.mandate_id} className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg)] px-3 py-2.5">
          <div className="flex items-center gap-2 flex-wrap text-[12.5px]"><span className="text-[var(--color-ink)] font-medium mr-auto">{c.short}</span>
            <StatusChip label={c.status_label} tone={TONE[c.status]} />{c.tier && <StatusChip label={c.tier.label} tone="neutral" />}
            {c.due_date && <span className="text-[11.5px] text-[var(--color-faint)]">due {day(c.due_date)}</span>}</div>
          <ul className="mt-1.5 space-y-1 list-none p-0 m-0">{c.checks.map((k, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[12px] text-[var(--color-mute)]">{icon(k.result)}<span>{k.label}{k.tier ? <span className="text-[var(--color-faint)]"> · {k.tier}</span> : null}</span></li>))}</ul>
        </div>))}</div>
      <div className="text-[12px] text-[var(--color-mute)] mb-2">Its regulatory attributes</div>
      <Facts rows={Object.entries(d.attributes).map(([k, def]) => { const a = e.attributes[k]; return [def.label, a
        ? <span>{a.value_label ?? value(a.value, def.unit)}<span className="text-[var(--color-faint)]">{a.source_label ? ` · ${a.source_label}` : ''}{a.as_of ? ` · ${day(a.as_of)}` : ''}</span></span>
        : <span className="text-[var(--color-warn)]">Not stated</span>] as [string, React.ReactNode] })} />
    </Drawer>
  )
}
