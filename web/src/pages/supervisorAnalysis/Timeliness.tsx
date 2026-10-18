import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '../../components/ui'
import { Dialog } from '../../components/Dialog'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton, messageDetails, type Message } from '../../components/Details'

// Filing timeliness across the population as one status bar per entity: a block per filing owed, coloured by where
// it stands against its due date, the worst first. A block opens the filing's dates.
type State = 'outstanding_overdue' | 'filed_late' | 'not_yet_due' | 'filed_on_time' | 'filed' | 'no_due_date'
type Filing = { org_id: string; name: string; framework_label: string; period_label: string; due_date: string | null; filed_at: string | null; state: State; days: number | null; intake_received_at: string | null; intake_lag_days: number | null }
export interface TimelinessResp { rows: Filing[]; summary: Record<State, number>; note: Message }

const STATE: Record<State, { label: string; color: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  outstanding_overdue: { label: 'Overdue', color: 'var(--color-bad)', tone: 'bad' },
  filed_late: { label: 'Filed late', color: 'var(--color-warn)', tone: 'warn' },
  not_yet_due: { label: 'Not yet due', color: 'var(--color-slate)', tone: 'neutral' },
  filed_on_time: { label: 'Filed on time', color: 'var(--color-good)', tone: 'good' },
  filed: { label: 'Filed', color: 'var(--color-good)', tone: 'good' },
  no_due_date: { label: 'No due date', color: 'var(--color-line-2)', tone: 'neutral' },
}
const ORDER = Object.keys(STATE) as State[]
const day = (iso: string | null) => iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

export function Timeliness({ data, csv }: { data?: TimelinessResp; csv?: React.ReactNode }) {
  const [open, setOpen] = useState<Filing | null>(null)
  const entities = useMemo(() => {
    const by = new Map<string, { org_id: string; name: string; filings: Filing[] }>()
    for (const r of data?.rows ?? []) {
      const e = by.get(r.org_id) ?? { org_id: r.org_id, name: r.name, filings: [] }
      e.filings.push(r); by.set(r.org_id, e)
    }
    const rank = (f: Filing) => ORDER.indexOf(f.state)
    return [...by.values()].map(e => ({ ...e, filings: e.filings.sort((a, b) => rank(a) - rank(b)) }))
      .sort((a, b) => rank(a.filings[0]) - rank(b.filings[0]) || a.name.localeCompare(b.name))
  }, [data])
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <div className="text-[14px] font-semibold">Filings against their due dates</div>
        {data && <InfoButton compact details={{ title: 'Filings against their due dates', sections: [
          ...messageDetails(data.note).sections,
          { heading: HEADING.read, body: 'One bar per entity, one block per filing it owes, the most pressing first. Select a block for its dates.' },
        ] }} />}
        <span className="ml-auto">{csv}</span>
      </div>
      {!data ? <div className="text-[12px] text-[var(--color-faint)]">Loading…</div>
        : data.rows.length === 0 ? <div className="text-[12px] text-[var(--color-faint)]">No obligations or filings on record for the population.</div> : (<>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3 text-[11.5px] text-[var(--color-mute)] tabular-nums">
          {ORDER.filter(s => data.summary[s]).map(s => <span key={s} className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: STATE[s].color }} />{STATE[s].label} {data.summary[s]}</span>)}
        </div>
        <div className="space-y-1.5 max-h-[320px] overflow-y-auto pr-1">
          {entities.map(e => (
            <div key={e.org_id} className="grid grid-cols-[minmax(0,10rem)_1fr] items-center gap-3">
              <Link to={`/supervised/${e.org_id}`} className="text-[12.5px] text-[var(--color-ink)] truncate hover:text-[var(--color-sky)] hover:underline" title={e.name}>{e.name.replace(' (demo)', '')}</Link>
              <div className="flex h-5 gap-[3px]">
                {e.filings.map((f, i) => (
                  <button key={i} type="button" onClick={() => setOpen(f)} aria-label={`${e.name}, ${f.framework_label} ${f.period_label}: ${STATE[f.state].label}`}
                    title={`${f.framework_label} · ${f.period_label} · ${STATE[f.state].label}`}
                    className="flex-1 min-w-[10px] rounded-sm transition hover:opacity-80 hover:ring-2 hover:ring-[var(--color-sky)]" style={{ background: STATE[f.state].color }} />))}
              </div>
            </div>))}
        </div>
      </>)}
      {open && <FilingDialog f={open} onClose={() => setOpen(null)} />}
    </Card>
  )
}

function FilingDialog({ f, onClose }: { f: Filing; onClose: () => void }) {
  const fact = (label: string, value: React.ReactNode) => (
    <div className="flex justify-between gap-4 py-1.5 border-b border-[var(--color-line)] text-[12.5px]">
      <span className="text-[var(--color-mute)]">{label}</span><span className="text-right text-[var(--color-ink)] tabular-nums">{value}</span>
    </div>)
  const days = f.days == null ? null : f.state === 'filed_late' ? `${f.days} days late` : f.state === 'outstanding_overdue' ? `${f.days} days overdue`
    : f.state === 'not_yet_due' ? `due in ${f.days} days` : f.state === 'filed_on_time' ? `${f.days} days early` : null
  return (
    <Dialog title={`${f.framework_label} · ${f.period_label}`} onClose={onClose} className="max-w-md">
      <div className="mb-3"><Link to={`/supervised/${f.org_id}`} className="text-[12.5px] text-[var(--color-sky)] hover:underline">{f.name}</Link></div>
      {fact('Status', <StatusChip tone={STATE[f.state].tone} label={STATE[f.state].label} />)}
      {fact('Due', day(f.due_date))}
      {fact('Filed', day(f.filed_at))}
      {days && fact('Against the due date', days)}
      {fact('Template reached your intake', f.intake_lag_days != null ? `${day(f.intake_received_at)} · ${f.intake_lag_days} days after the year end` : 'Not yet')}
    </Dialog>
  )
}
