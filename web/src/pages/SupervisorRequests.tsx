import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Plus } from 'lucide-react'
import { api } from '../lib/api'
import { Button, Card, PageHeader, StatGrid } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import type { Message } from '../components/Details'
import { pressable } from '../lib/pressable'
import { Failed, Loading, Segmented, aboutOf, day, field } from './supervisorDesk/common'
import { RequestDrawer, SEV_TONE, statusTone } from './supervisorDesk/RequestThread'
import { NewRequestDialog } from './supervisorDesk/NewRequest'
import { ServiceLevels } from './supervisorDesk/ServiceLevels'
import { AuthorityCalendar } from './supervisorDesk/AuthorityCalendar'

// Requests & findings (UI standard, 2026-10-16): the supervisor's engagement with each entity, tracked to closure on one
// thread both sides read. Figures and service levels first, the list with chips; a request opens in a side drawer, a new
// one in a dialog. The calendar by authority is the second view. Kinds and status flows come from the supervision profile.
export interface Req {
  request_id: string; supervised_org_id: string; entity: string; regulator: string; kind: string; kind_label: string; title: string; body: string | null
  status: string; status_label: string; severity: string | null; severity_label: string | null; due_date: string | null; overdue: boolean
  raised_at: string; raised_by: string | null; automatic?: boolean; n_messages?: number; reference?: string | null
  source: { type?: string; label?: string | null; geography?: string; sector?: string; geography_label?: string; sector_label?: string } | null
}
export interface Kind { label: string; statuses: { key: string; label: string }[]; supervisor_sets: string[]; severities: string[]; severity_labels: Record<string, string> }
export interface ListResp {
  requests: Req[]; entities: { org_id: string; name: string }[]; kinds: Record<string, Kind>; about: Message
  summary: { open: number; overdue: number; findings_open: number }
}
type Show = 'open' | 'closed' | 'all'

export default function SupervisorRequests() {
  const [params, setParams] = useSearchParams()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['supervisor-requests'], queryFn: () => api.get<ListResp>('/v1/supervisor/requests') })
  const [sel, setSel] = useState<string | null>(null)
  const creating = params.get('new') === '1'
  const view = params.get('view') === 'calendar' ? 'calendar' : 'requests'
  const fEntity = params.get('entity') ?? '', fKind = params.get('kind') ?? ''
  const show = (params.get('show') as Show | null) ?? 'open'
  const setF = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p) }
  const d = q.data
  const rows = useMemo(() => (d?.requests ?? []).filter(r => (!fEntity || r.supervised_org_id === fEntity) && (!fKind || r.kind === fKind)
    && (show === 'all' || (show === 'closed') === (r.status === 'closed'))), [d, fEntity, fKind, show])
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ['supervisor-requests'] }), qc.invalidateQueries({ queryKey: ['supervisor-workflow'] }),
    qc.invalidateQueries({ queryKey: ['supervisor-sla'] })])
  const closeNew = () => { const p = new URLSearchParams(params); for (const k of ['new', 'title', 'body', 'geography', 'sector']) p.delete(k); setParams(p) }
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Requests & findings" title="Engage and follow up" lead="Raise, follow and close with each entity." about={aboutOf(d?.about)}
        actions={<Button onClick={() => setF('new', '1')}><Plus size={15} />New request or finding</Button>} />
      <Segmented label="View" value={view} onChange={v => setF('view', v === 'requests' ? '' : v)} options={[['requests', 'Requests'], ['calendar', 'Calendar by authority']]} />
      {view === 'calendar' ? <AuthorityCalendar /> : q.isLoading ? <Loading what="the requests" /> : !d ? <Failed what="the requests" /> : (<>
        <StatGrid cols={3} items={[
          { label: 'Open', value: String(d.summary.open), sub: 'awaiting the entity or you', accent: d.summary.open ? 'var(--color-warn)' : undefined },
          { label: 'Overdue', value: String(d.summary.overdue), sub: 'past their due date', accent: d.summary.overdue ? 'var(--color-bad)' : undefined },
          { label: 'Findings open', value: String(d.summary.findings_open), sub: 'remediation not yet closed' },
        ]} />
        <ServiceLevels />
        <Card className="p-5 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <select aria-label="Entity" value={fEntity} onChange={e => setF('entity', e.target.value)} className={field}>
              <option value="">All entities</option>{d.entities.map(e => <option key={e.org_id} value={e.org_id}>{e.name}</option>)}</select>
            <select aria-label="Kind" value={fKind} onChange={e => setF('kind', e.target.value)} className={field}>
              <option value="">All kinds</option>{Object.entries(d.kinds).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select>
            <span className="ml-auto"><Segmented label="Show" value={show} onChange={v => setF('show', v === 'open' ? '' : v)}
              options={[['open', 'Open'], ['closed', 'Closed'], ['all', 'All']]} /></span>
          </div>
          <div className="overflow-x-auto">
            <table className="data-table w-full text-[12.5px]">
              <thead><tr className="text-left"><th>Reference</th><th>Entity</th><th>Request</th><th>Severity</th><th>Status</th><th>Due</th><th className="num">Thread</th></tr></thead>
              <tbody>{rows.map(r => (
                <tr key={r.request_id} {...pressable(() => setSel(r.request_id), { row: true })} className="border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)]">
                  <td className="tabular-nums text-[var(--color-mute)] whitespace-nowrap">{r.reference ?? '—'}</td>
                  <td className="text-[var(--color-ink)] whitespace-nowrap">{r.entity}</td>
                  <td className="min-w-[16rem]">
                    <span className="block text-[var(--color-ink)]">{r.title}</span>
                    <span className="flex flex-wrap items-center gap-1.5 mt-0.5 text-[11.5px] text-[var(--color-faint)]">{r.kind_label}
                      {r.source?.label && <StatusChip label={r.source.label} tone="neutral" />}</span>
                  </td>
                  <td>{r.severity_label ? <StatusChip label={r.severity_label} tone={SEV_TONE[r.severity ?? ''] ?? 'neutral'} /> : <span className="text-[var(--color-faint)]">—</span>}</td>
                  <td><StatusChip label={r.status_label} tone={statusTone(r.status)} /></td>
                  <td className="whitespace-nowrap tabular-nums">{r.overdue ? <StatusChip label={`Overdue · ${day(r.due_date)}`} tone="bad" /> : <span className="text-[var(--color-mute)]">{day(r.due_date)}</span>}</td>
                  <td className="num text-[var(--color-faint)]"><span className="inline-flex items-center gap-1"><MessageSquare size={12} />{r.n_messages ?? 0}</span></td>
                </tr>))}</tbody>
            </table>
            {rows.length === 0 && <div className="py-8 text-center text-[13px] text-[var(--color-faint)]">{d.requests.length ? 'Nothing matches these filters.' : 'Nothing raised yet.'}</div>}
          </div>
        </Card>
        {sel && <RequestDrawer id={sel} onChange={refresh} onClose={() => setSel(null)} />}
        {creating && <NewRequestDialog d={d} params={params} onClose={closeNew} onDone={async id => { closeNew(); await refresh(); if (id) setSel(id) }} />}
      </>)}
    </div>
  )
}
