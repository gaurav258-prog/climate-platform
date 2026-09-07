import { useState } from 'react'
import ExposureMap, { type Region, type Site } from '../components/ExposureMap'
import { useQuery } from '@tanstack/react-query'
import { Scale, ChevronRight } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, StatGrid } from '../components/ui'

// Regulator portal — Phase 1. The supervised population and each entity's latest submission status per
// framework. Read-only, released-only, scoped server-side to this regulator's supervision_scope.
interface Fw { framework: string; label: string; state: 'filed' | 'in_progress' | 'none'; status: string | null; period_label: string | null }
interface Entity { org_id: string; name: string; type: string; country: string; jurisdiction: string | null; frameworks: Fw[]; filed: number; expected: number }
interface Population { regulator: string; entities: Entity[]; summary: { entities: number; frameworks_expected: number; frameworks_filed: number; coverage_pct: number | null } }
interface Filing { filing_id: string; framework: string; status: string; period_label: string | null; submission_ref: string | null; created_at: string | null }
interface EntityDetail { entity: { org_id: string; name: string; type: string; country: string }; filings: Filing[] }

const SECTOR: Record<string, string> = { bank: 'Bank', insurer: 'Insurer', asset_manager: 'Asset manager', reit: 'REIT', manufacturer: 'Agriculture' }
const CHIP: Record<Fw['state'], string> = {
  filed: 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]',
  in_progress: 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_14%,transparent)]',
  none: 'text-[var(--color-faint)] bg-[color-mix(in_oklab,var(--color-faint)_12%,transparent)]',
}
const CHIP_LABEL: Record<Fw['state'], string> = { filed: 'Filed', in_progress: 'In progress', none: 'Not filed' }

export default function Supervised() {
  const [open, setOpen] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['supervisor-population'], queryFn: () => api.get<Population>('/v1/supervisor/population') })
  const d = q.data

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Supervision · cross-entity" title="Supervised population"
        lead="Every entity you supervise and where each stands on its climate-risk submissions. Read-only, released filings only — each entity is notified in its own audit trail when you open its filings." />

      {q.isLoading ? <Center>loading…</Center> : !d ? <Center>Could not load the population.</Center> : (
        <>
          <StatGrid cols={3} items={[
            { label: 'Supervised entities', value: String(d.summary.entities) },
            { label: 'Submission coverage', value: d.summary.coverage_pct != null ? `${d.summary.coverage_pct}%` : '—',
              sub: `${d.summary.frameworks_filed}/${d.summary.frameworks_expected} framework-periods filed` },
            { label: 'Open gaps', value: String(d.summary.frameworks_expected - d.summary.frameworks_filed),
              accent: d.summary.frameworks_filed < d.summary.frameworks_expected ? 'var(--color-warn)' : 'var(--color-good)' },
          ]} />

          <ExposureCard />

          <div className="space-y-3">
            {d.entities.map(e => (
              <Card key={e.org_id} className="p-5">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-3">
                    <Scale size={16} className="text-[var(--color-sky)]" />
                    <span className="text-[15px] font-semibold">{e.name}</span>
                    <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">{SECTOR[e.type] ?? e.type}</span>
                    {e.jurisdiction && <span className="mono text-[10px] text-[var(--color-faint)]">· {e.jurisdiction}</span>}
                  </div>
                  <span className="mono text-[11px] text-[var(--color-mute)]">{e.filed}/{e.expected} filed</span>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {e.frameworks.map(f => (
                    <span key={f.framework} title={f.status ? `${f.status}${f.period_label ? ' · ' + f.period_label : ''}` : 'no filing on record'}
                      className={`mono text-[10.5px] px-2 py-1 rounded ${CHIP[f.state]}`}>
                      {f.label}: {CHIP_LABEL[f.state]}
                    </span>
                  ))}
                </div>

                <button onClick={() => setOpen(open === e.org_id ? null : e.org_id)}
                  className="mt-3 inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline">
                  <ChevronRight size={13} className={open === e.org_id ? 'rotate-90 transition' : 'transition'} />
                  {open === e.org_id ? 'Hide' : 'View'} released filings
                </button>
                {open === e.org_id && <EntityFilings orgId={e.org_id} />}
              </Card>
            ))}
            {d.entities.length === 0 && <Card className="p-8 text-center text-[var(--color-faint)] text-sm">No entities in your supervised population.</Card>}
          </div>
        </>
      )}
    </div>
  )
}

function EntityFilings({ orgId }: { orgId: string }) {
  const q = useQuery({ queryKey: ['supervisor-entity', orgId], queryFn: () => api.get<EntityDetail>(`/v1/supervisor/entity/${orgId}`) })
  if (q.isLoading) return <div className="mt-3 text-[12px] text-[var(--color-faint)]">loading…</div>
  const rows = q.data?.filings ?? []
  if (!rows.length) return <div className="mt-3 text-[12px] text-[var(--color-faint)]">No released filings on record.</div>
  return (
    <div className="mt-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-3">
      <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-[var(--color-faint)] mb-2">Released filings</div>
      <div className="flex flex-col gap-1.5">
        {rows.map(f => (
          <div key={f.filing_id} className="flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[12.5px]">
            <span className="font-medium min-w-[220px]">{f.framework}</span>
            <span className="mono text-[11px] text-[var(--color-good)]">{f.status}</span>
            {f.period_label && <span className="text-[var(--color-mute)]">{f.period_label}</span>}
            {f.submission_ref && <span className="mono text-[10.5px] text-[var(--color-faint)]">ref {f.submission_ref}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => (
  <div className="h-[40vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
)


// ── Where the supervised exposure sits ─────────────────────────────────────────────────────────────────────
// Regional by default (NUTS-3 / hexagons — what filings carry). Individual sites only for an entity that has
// granted site-level access; the switch is on the entity's side, the regulator can only ask.
interface MapResp { scenario: string; horizon: string; level: string; n_sites: number; value_eur: number; n_regions: number
  entities: { org_id: string; name: string; type: string; n_sites: number; value_eur: number; site_access: boolean }[]; regions: Region[] }
interface SitesResp { entity: { org_id: string; name: string }; n_sites: number; sites: Site[] }
const eurS = (v: number) => v >= 1e9 ? `€${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${(v / 1e3).toFixed(0)}k`

function ExposureCard() {
  const [entity, setEntity] = useState('all')
  const [showSites, setShowSites] = useState(false)
  const m = useQuery({ queryKey: ['supervisor-map', entity], queryFn: () => api.get<MapResp>(`/v1/supervisor/map?entity=${entity}`) })
  const sel = m.data?.entities.find(e => e.org_id === entity)
  const canSites = !!sel?.site_access
  const sites = useQuery({ queryKey: ['supervisor-sites', entity], enabled: entity !== 'all' && canSites && showSites,
    queryFn: () => api.get<SitesResp>(`/v1/supervisor/sites?entity=${entity}`) })
  const d = m.data
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between flex-wrap gap-3 mb-3">
        <div>
          <div className="text-[15px] font-semibold">Where the supervised exposure sits</div>
          <div className="text-[12px] text-[var(--color-mute)] mt-0.5">
            Regional by default — {d?.level ?? 'NUTS-3 / hexagons'}, the unit your filings use. Individual sites appear only for an entity that has granted you site-level access.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select value={entity} onChange={e => { setEntity(e.target.value); setShowSites(false) }}
            className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-mute)] outline-none">
            <option value="all">Whole population</option>
            {(d?.entities ?? []).map(e => <option key={e.org_id} value={e.org_id}>{e.name}{e.site_access ? ' · sites granted' : ''}</option>)}
          </select>
          <label className={`inline-flex items-center gap-1.5 text-[12px] ${entity === 'all' || !canSites ? 'text-[var(--color-faint)]' : 'text-[var(--color-ink)] cursor-pointer'}`}
            title={entity === 'all' ? 'Pick one entity to show its sites' : canSites ? 'Site-level access granted by this entity' : 'This entity has not granted site-level access — ask them; the switch is in their Control center'}>
            <input type="checkbox" disabled={entity === 'all' || !canSites} checked={showSites && canSites} onChange={e => setShowSites(e.target.checked)} />
            Individual sites{entity !== 'all' && !canSites ? ' (not granted)' : ''}
          </label>
        </div>
      </div>
      {d && (
        <div className="mono text-[11px] text-[var(--color-faint)] mb-2">
          {d.n_sites.toLocaleString()} sites · {eurS(d.value_eur)} · {d.n_regions} regions · {d.scenario} · {d.horizon}
          {' · '}{d.entities.filter(e => e.site_access).length} of {d.entities.length} entities grant site access
        </div>
      )}
      {m.isLoading ? <div className="h-[480px] grid place-items-center text-[var(--color-faint)] text-sm">loading the population map…</div>
        : d ? <ExposureMap regions={d.regions} sites={showSites && canSites ? sites.data?.sites : undefined} />
        : <div className="text-[13px] text-[var(--color-bad)]">Could not load the exposure map.</div>}
      {sites.isError && <div className="mt-2 text-[12px] text-[var(--color-bad)]">Site-level access is not granted (or was revoked) — regional view only.</div>}
    </Card>
  )
}
