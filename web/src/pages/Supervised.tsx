import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Button, Card, PageHeader, StatGrid } from '../components/ui'
import StageStrip, { type Step } from '../components/StageStrip'

// The Population page is the supervisor's working list: every entity, where it stands in the process, the criteria
// a supervisor sorts on, and the one next action. Everything in a row is derived from what the platform holds.
interface Fw { framework: string; label: string; state: 'filed' | 'in_progress' | 'none'; status: string | null; period_label: string | null }
interface Row { org_id: string; name: string; type: string; sector_label: string; country: string; jurisdiction: string | null; in_profile: boolean
  frameworks: Fw[]; filed: number; expected: number; steps: Step[]; stage: string; stage_label?: string; next: { label: string; to: string }
  site_access: boolean; high_risk_share_pct: number | null; high_risk_flag: string | null; lens_gap_pct: number | null; n_questions: number | null }
interface Resp { regulator: string; visibility: { scope: 'assigned' | 'population'; assigned: number | null }; summary: { entities: number; frameworks_expected: number; frameworks_filed: number; coverage_pct: number | null }
  scenario: string; horizon: string; steps: { key: string; label: string }[]; entities: Row[] }
const STAGE_LABEL: Record<string, string> = { collect: 'Awaiting filings', submitted: 'Filings received', ingested: 'Data ingested', rebuilt: 'Rebuilt & projected', reviewed: 'Reviewed', out_of_profile: 'Outside profile' }
const STAGE_ORDER: Record<string, number> = { out_of_profile: -1, collect: 0, submitted: 1, ingested: 2, rebuilt: 3, reviewed: 4 }
const FLAGC: Record<string, string> = { act: 'var(--color-bad)', watch: 'var(--color-warn)', ok: 'var(--color-good)', na: 'var(--color-faint)' }
type SortKey = 'name' | 'sector_label' | 'jurisdiction' | 'stage' | 'submissions' | 'high_risk_share_pct' | 'lens_gap_pct' | 'n_questions'

export default function Supervised() {
  const { profile } = useAuth()
  const canExport = (profile?.permissions ?? []).includes('supervisor.export')
  const q = useQuery({ queryKey: ['supervisor-workflow'], queryFn: () => api.get<Resp>('/v1/supervisor/population/workflow') })
  const d = q.data
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'high_risk_share_pct', dir: -1 })
  const [fSector, setFSector] = useState(''); const [fJur, setFJur] = useState(''); const [fStage, setFStage] = useState(''); const [fFlag, setFFlag] = useState(''); const [search, setSearch] = useState('')
  const rows = useMemo(() => {
    if (!d) return []
    let r = d.entities.filter(e => (!fSector || e.sector_label === fSector) && (!fJur || e.jurisdiction === fJur) && (!fStage || e.stage === fStage)
      && (!fFlag || (fFlag === 'questions' ? (e.n_questions ?? 0) > 0 : fFlag === 'site_access' ? e.site_access : e.high_risk_flag === fFlag))
      && (!search || e.name.toLowerCase().includes(search.toLowerCase())))
    const val = (e: Row): number | string => sort.key === 'submissions' ? (e.expected ? e.filed / e.expected : -1)
      : sort.key === 'stage' ? STAGE_ORDER[e.stage] ?? 0 : sort.key === 'name' || sort.key === 'sector_label' || sort.key === 'jurisdiction' ? (e[sort.key] ?? '') : (e[sort.key] ?? -Infinity)
    r = [...r].sort((a, b) => { const va = val(a), vb = val(b); return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir })
    return r
  }, [d, sort, fSector, fJur, fStage, fFlag, search])
  const toggle = (key: SortKey) => setSort(s => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : (key === 'name' || key === 'sector_label' || key === 'jurisdiction' ? 1 : -1) }))
  const Th = ({ k, children, right }: { k: SortKey; children: React.ReactNode; right?: boolean }) => (
    <th className={`cursor-pointer select-none hover:text-[var(--color-sky)] ${right ? 'num' : ''}`} onClick={() => toggle(k)}>
      {children}{sort.key === k ? (sort.dir === 1 ? ' ↑' : ' ↓') : ''}</th>)
  const uniq = (f: (e: Row) => string | null) => Array.from(new Set((d?.entities ?? []).map(f).filter(Boolean))) as string[]
  const stageCounts = (d?.entities ?? []).reduce<Record<string, number>>((a, e) => { a[e.stage] = (a[e.stage] ?? 0) + 1; return a }, {})
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Population" title="Supervised population"
        lead="Every entity you supervise, where it stands in the supervisory process, and its next action. Sort and filter on the criteria that matter to you. Read-only: each entity is notified in its own audit trail when you open its file."
        actions={canExport ? <Button variant="ghost" onClick={() => download('/v1/supervisor/export/population.xlsx', 'supervised-population.xlsx')}>Export population (Excel)</Button> : undefined} />
      {q.isLoading ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">assessing every entity's position in the process…</div> : !d ? <div className="text-[13px] text-[var(--color-bad)]">Could not load the population.</div> : (<>
        {d.visibility?.scope === 'assigned' && (
          <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-panel-2)] px-4 py-2.5 text-[12.5px] text-[var(--color-mute)]">
            You see the {d.summary.entities} {d.summary.entities === 1 ? 'entity' : 'entities'} assigned to you. Other entities in your organisation's population are worked by colleagues; your head of division manages assignments in Settings.
          </div>)}
        <StatGrid cols={4} items={[
          { label: d.visibility?.scope === 'assigned' ? 'Your entities' : 'Supervised entities', value: String(d.summary.entities), sub: `${d.entities.filter(e => e.in_profile).length} in your profile` },
          { label: 'Submission coverage', value: d.summary.coverage_pct != null ? `${d.summary.coverage_pct}%` : '—', sub: `${d.summary.frameworks_filed}/${d.summary.frameworks_expected} framework-periods filed` },
          { label: 'Reviewed', value: `${stageCounts.reviewed ?? 0} / ${d.entities.filter(e => e.in_profile).length}`, sub: 'independent lens run', accent: (stageCounts.reviewed ?? 0) ? 'var(--color-good)' : undefined },
          { label: 'Open questions', value: String(d.entities.reduce((a, e) => a + (e.n_questions ?? 0), 0)), sub: 'flagged cells across the population', accent: d.entities.some(e => (e.n_questions ?? 0) > 0) ? 'var(--color-warn)' : undefined },
        ]} />
        <Card className="p-5">
          <div className="flex items-center gap-4 mb-3 flex-wrap">
            <div className="text-[13px] text-[var(--color-mute)]">The process, per entity:</div>
            <StageStrip steps={d.steps.map(s => ({ key: s.key, label: s.label, done: false, partial: false }))} />
            <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto flex items-center gap-3">
              <span className="inline-flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: 'var(--color-good)' }} /> complete</span>
              <span className="inline-flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full border-[1.5px]" style={{ borderColor: 'var(--color-warn)' }} /> partly</span>
              <span className="inline-flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full border-[1.5px]" style={{ borderColor: 'var(--color-line)' }} /> not yet</span>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search entities…" className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)] min-w-[180px]" />
            {[['Sector', fSector, setFSector, uniq(e => e.sector_label)], ['Jurisdiction', fJur, setFJur, uniq(e => e.jurisdiction)],
              ['Stage', fStage, setFStage, Object.keys(STAGE_ORDER).filter(k => stageCounts[k])]].map(([label, val, set, opts]) => (
              <select key={label as string} value={val as string} onChange={e => (set as (v: string) => void)(e.target.value)} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-mute)] outline-none">
                <option value="">All {(label as string).toLowerCase()}s</option>
                {(opts as string[]).map(o => <option key={o} value={o}>{label === 'Stage' ? STAGE_LABEL[o] ?? o : o}</option>)}
              </select>))}
            <select value={fFlag} onChange={e => setFFlag(e.target.value)} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-mute)] outline-none">
              <option value="">Any flag</option><option value="act">Act (high-risk share)</option><option value="watch">Watch (high-risk share)</option><option value="questions">Has open questions</option><option value="site_access">Site access granted</option>
            </select>
            {(fSector || fJur || fStage || fFlag || search) && <button onClick={() => { setFSector(''); setFJur(''); setFStage(''); setFFlag(''); setSearch('') }} className="mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-sky)]">clear</button>}
            <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">{rows.length} of {d.entities.length} · basis {d.scenario} · {d.horizon} · click a column to sort</span>
          </div>
          <div className="overflow-x-auto">
            <table className="data-table w-full text-[12.5px]">
              <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <Th k="name">Entity</Th><Th k="sector_label">Sector</Th><Th k="jurisdiction">Jurisdiction</Th><Th k="stage">Process</Th>
                <Th k="submissions" right>Filings</Th><Th k="high_risk_share_pct" right>Book at high risk</Th><Th k="lens_gap_pct" right>Lens gap</Th><Th k="n_questions" right>Questions</Th>
                <th className="">Next action</th></tr></thead>
              <tbody>{rows.map(e => (
                <tr key={e.org_id} className={`border-t border-[var(--color-line)] ${e.in_profile ? '' : 'opacity-60'}`}>
                  <td><Link to={`/supervised/${e.org_id}`} className="text-[var(--color-ink)] hover:text-[var(--color-sky)] hover:underline font-medium">{e.name}</Link>
                    {e.site_access && <span className="mono text-[9.5px] uppercase ml-2 px-1 rounded bg-[var(--color-good)]/15 text-[var(--color-good)]">sites</span>}</td>
                  <td className="text-[var(--color-mute)]">{e.sector_label}</td>
                  <td className="mono text-[11px] text-[var(--color-faint)]">{e.jurisdiction ?? '—'}</td>
                  <td className="pr-3"><div className="flex items-center gap-2"><StageStrip steps={e.steps} compact /><span className="text-[11px] text-[var(--color-mute)]">{e.stage_label ?? STAGE_LABEL[e.stage] ?? e.stage}</span></div></td>
                  <td className="num mono text-[var(--color-mute)]">{e.filed}/{e.expected}</td>
                  <td className="num mono" style={{ color: FLAGC[e.high_risk_flag ?? 'na'] }}>{e.high_risk_share_pct != null ? `${e.high_risk_share_pct}%` : '—'}</td>
                  <td className="num mono" style={{ color: e.lens_gap_pct != null && Math.abs(e.lens_gap_pct) >= 10 ? 'var(--color-warn)' : 'var(--color-mute)' }}>{e.lens_gap_pct != null ? `${e.lens_gap_pct}%` : '—'}</td>
                  <td className="num mono text-[var(--color-mute)]">{e.n_questions ?? '—'}</td>
                  <td><Link to={e.next.to} className="text-[12px] text-[var(--color-sky)] hover:underline">{e.next.label} →</Link></td>
                </tr>))}</tbody>
            </table>
            {rows.length === 0 && <div className="py-8 text-center text-[13px] text-[var(--color-faint)]">No entities match these filters.</div>}
          </div>
        </Card>
      </>)}
    </div>
  )
}
