import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { Card, PageHeader } from '../components/ui'
import ExposureMap, { type Region, type Site } from '../components/ExposureMap'
import { balance } from '../lib/money'
import { HEADING, InfoButton } from '../components/Details'
import { hazardLabel, horizonLabel, scenarioLabel } from '../lib/labels'
import { countryName } from '../lib/codeWords'

// how the map is drawn — one click away (UI standard)
const ABOUT = [
  { heading: HEADING.read, body: 'Inside the EU each area is a statistical region (NUTS level 3); elsewhere it is a hexagonal grid cell, clipped to the coastline. These are the units your filings use. Individual sites appear only for an entity that has granted you access to them — the switch is on the entity’s side.' },
  { heading: HEADING.sources, body: 'Regions: Eurostat GISCO, NUTS 2021. Coastline: Eurostat GISCO countries, 2020. Map tiles: Esri.' },
]
// ── Where the supervised exposure sits ─────────────────────────────────────────────────────────────────────
// Regional by default (NUTS-3 / hexagons — what filings carry). Individual sites only for an entity that has
// granted site-level access; the switch is on the entity's side, the regulator can only ask.
interface MapResp { scenario: string; horizon: string; n_sites: number; value_eur: number; n_regions: number
  entities: { org_id: string; name: string; type: string; n_sites: number; value_eur: number; site_access: boolean }[]; regions: Region[] }
interface SitesResp { entity: { org_id: string; name: string }; n_sites: number; sites: Site[] }

function ExposureCard() {
  const [params] = useSearchParams()
  const focusKey = params.get('region')
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
          <div className="text-[15px] font-semibold inline-flex items-center gap-1.5">Where the supervised exposure sits <InfoButton compact details={{ title: 'How the map is drawn', sections: ABOUT }} /></div>
          <div className="text-[12px] text-[var(--color-mute)] mt-0.5">By region; individual sites only where access is granted.</div>
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
      {focusKey && d && (() => { const r = d.regions.find(x => x.key === focusKey); return r ? (
        <div className="mb-2 text-[12.5px] text-[var(--color-ink)]">Focused on <b>{r.name}</b>{countryName(r.country) && !r.name.includes(countryName(r.country)!) ? ` · ${countryName(r.country)}` : ''}: {r.n_sites} sites · {balance(r.value_eur)} · worst {r.max_score != null ? Math.round(r.max_score) : '—'}/100{r.worst_hazard ? ` (${hazardLabel(r.worst_hazard)})` : ''} · {r.entities.join(', ')}</div>) : null })()}
      {d && (
        <div className="text-[11.5px] text-[var(--color-faint)] mb-2">
          {d.n_sites.toLocaleString()} sites · {balance(d.value_eur)} · {d.n_regions} areas · {scenarioLabel(d.scenario)} · {horizonLabel(d.horizon)}
          {' · '}{d.entities.filter(e => e.site_access).length} of {d.entities.length} entities grant site access
        </div>
      )}
      {m.isLoading ? <div className="h-[480px] grid place-items-center text-[var(--color-faint)] text-sm">loading the population map…</div>
        : d ? <ExposureMap regions={d.regions} sites={showSites && canSites ? sites.data?.sites : undefined} focusKey={focusKey} />
        : <div className="text-[13px] text-[var(--color-bad)]">Could not load the exposure map.</div>}
      {sites.isError && <div className="mt-2 text-[12px] text-[var(--color-bad)]">Site-level access is not granted (or was revoked) — regional view only.</div>}
    </Card>
  )
}




export default function SupervisorMap() {
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Exposure map" title="Where the supervised exposure sits"
        lead="The supervised population's exposure, region by region." about={ABOUT} />
      <ExposureCard />
    </div>
  )
}
