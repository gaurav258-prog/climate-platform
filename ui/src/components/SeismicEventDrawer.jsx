import { ExternalLink } from 'lucide-react'
import { DrawerShell, Facts } from './EntityDrawerParts'

/** One seismic event, down to the raw USGS-catalog row -- the lowest level this
 * platform has. No scoring/valuation here (unlike the other drawers): this is
 * pure provenance for a feed row, not an entity with risk. */
export default function SeismicEventDrawer({ event, nearestAsset, distanceKm, onClose }) {
  if (!event) return null
  // event_id carries our own "usgs_" catalog prefix (see seismic_events ingestion) --
  // strip it to get USGS's own event id back for the public eventpage URL.
  const usgsUrl = event.source_catalog?.toLowerCase() === 'usgs'
    ? `https://earthquake.usgs.gov/earthquakes/eventpage/${event.event_id.replace(/^usgs_/, '')}`
    : null
  return (
    <DrawerShell title={`M${event.magnitude.toFixed(1)} · ${event.region_name}`}
      subtitle={`${event.origin_time?.slice(0, 19).replace('T', ' ')} UTC · ${event.source_catalog}`}
      loading={false} onClose={onClose}>
      <Facts title="Event" rows={[
        ['Magnitude', `${event.magnitude.toFixed(1)} (${event.mag_type || '—'})`],
        ['Depth', event.depth_km != null ? `${event.depth_km.toFixed(1)} km` : '—'],
        ['Epicentre', `${event.lat.toFixed(3)}, ${event.lon.toFixed(3)}`],
        ['Origin time (UTC)', event.origin_time?.slice(0, 19).replace('T', ' ') || '—'],
        ['Source catalog', event.source_catalog || '—'],
        ['Event ID', event.event_id],
      ]} />
      {nearestAsset && (
        <Facts title="Nearest portfolio asset" rows={[
          ['Asset', nearestAsset.asset_name],
          ['Distance', `${Math.round(distanceKm)} km`],
          ['Sector', nearestAsset.sector || '—'],
          ['Country', nearestAsset.country || '—'],
        ]} />
      )}
      {usgsUrl && (
        <a href={usgsUrl} target="_blank" rel="noreferrer"
          className="flex items-center justify-center gap-1.5 rounded-xl border border-gray-200 px-3 py-2 text-[12px] font-medium text-[#0071e3] hover:border-gray-300">
          View on USGS <ExternalLink size={13} />
        </a>
      )}
    </DrawerShell>
  )
}
