import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, Info } from 'lucide-react'
import { api } from '../lib/api'
import { balance, flow } from '../lib/money'
import { pressable } from '../lib/pressable'
import { Card, CountUp } from './ui'
import AssetDrawer, { type DrawerCfg } from './AssetDrawer'
import { DetailsBody } from './Details'
import { Dialog } from './Dialog'
import { EventDialog, EventList, EventRow, withSources } from './observed/Observed'
import type { Definition, Message, ObservedEvent, Source } from './observed/types'

// Realised exposure, to the UI standard (2026-10-16): the observed events that have already crossed this book — named
// storms and dated earthquakes matched to the organisation's own assets, or falls in national production of the crops it
// sources — never modelled. A number, a few figures and the list; each event opens its facts, each located event its
// assets, each asset the same drawer Portfolio opens. The explanation is the server's catalogue words (realized.book.*).
// Used on Portfolio and Disclosure; it takes no props.

interface Realized {
  available: boolean; sector?: string; message?: Message
  n_events?: number; n_storms?: number; n_earthquakes?: number; n_assets?: number; n_assets_crossed?: number
  value_crossed_eur?: number; peak_value_exposed_eur?: number; since_year?: number | null; spend_exposed_eur?: number
  events?: ObservedEvent[]; sources?: Source[]; definition?: Definition
}

// org type -> the per-asset detail drawer (the same drawers Portfolio uses); production shocks drill at crop level
const SECTOR_CFG: Record<string, DrawerCfg> = {
  bank: { prefix: 'bank', itemKey: 'asset', nameKey: 'asset_name', valueKey: 'value_eur', typeKey: 'asset_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
  insurer: { prefix: 'insurance', itemKey: 'policy', nameKey: 'policy_name', valueKey: 'sum_insured_eur', typeKey: 'policy_type', auditKey: 'audit', overrideMode: 'trigger' },
  reit: { prefix: 'realestate', itemKey: 'property', nameKey: 'property_name', valueKey: 'property_value_eur', typeKey: 'property_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
  asset_manager: { prefix: 'assetmgmt', itemKey: 'holding', nameKey: 'holding_name', valueKey: 'position_value_eur', typeKey: 'sector', valuationKey: 'climate_var', auditKey: 'valuation_audit', overrideMode: 'valuation' },
}
const SHELL = { borderColor: 'var(--color-blued)', background: 'linear-gradient(180deg,#0e2338,var(--color-panel))' }

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="min-w-0">
      <div className="display text-[19px] font-semibold tabular-nums text-[#F4EFE6] leading-none">{value}</div>
      <div className="text-[11.5px] text-[var(--color-mute)] mt-1">{label}</div>
    </div>
  )
}

export default function RealizedExposure() {
  const q = useQuery({ queryKey: ['realized-exposure'], queryFn: () => api.get<Realized>('/v1/realized-exposure') })
  const d = q.data
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  const [drawerId, setDrawerId] = useState<string | null>(null)
  const [event, setEvent] = useState<ObservedEvent | null>(null)
  const [about, setAbout] = useState(false)
  // While the request is in flight, hold the card's height rather than collapsing to nothing — otherwise the card pops
  // in a second later and shoves every section below it down the page. Only empty or unavailable data collapses it.
  if (q.isLoading) return (
    <div data-theme="dark">
      <Card className="p-5 min-h-[240px] flex items-center justify-center" style={SHELL}>
        <span className="text-[12px] text-[var(--color-sky)] opacity-70">Observed record · loading…</span>
      </Card>
    </div>
  )
  if (!d || !d.available || !d.events || d.events.length === 0 || !d.message) return null
  const crops = d.sector === 'manufacturer'
  const cfg = d.sector ? SECTOR_CFG[d.sector] : undefined
  const events = d.events

  return (
    <>
    {/* the card is permanently dark, so its subtree reads dark tokens — otherwise the muted text tokens resolve to their
        light values and read dark-on-dark */}
    <div data-theme="dark">
    <Card className="p-5" style={SHELL}>
      <div className="flex items-center gap-2 mb-3">
        <History size={16} className="text-[var(--color-sky)]" />
        <span className="text-[12.5px] font-medium text-[var(--color-sky)]">Observed record</span>
        <button type="button" onClick={() => setAbout(true)} aria-label={`More about ${d.message.label}`}
          className="text-[var(--color-faint)] hover:text-[var(--color-sky)] transition"><Info size={14} /></button>
      </div>
      <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
        <div>
          <div className="display text-[40px] leading-none font-semibold tabular-nums text-[#F4EFE6]"><CountUp value={d.n_events ?? events.length} /></div>
          <div className="text-[13px] text-[var(--color-mute)] mt-1.5 max-w-xs">{d.message.label}{d.since_year ? ` since ${d.since_year}` : ''}</div>
        </div>
        {crops ? (
          <Figure value={flow(d.spend_exposed_eur)} label="your yearly spend in those origins" />
        ) : (
          <>
            <Figure value={`${d.n_storms ?? 0} · ${d.n_earthquakes ?? 0}`} label="storms · earthquakes" />
            <Figure value={`${d.n_assets_crossed ?? 0} of ${d.n_assets ?? 0}`} label="assets within reach" />
            <Figure value={balance(d.value_crossed_eur)} label="value at those assets" />
          </>
        )}
      </div>

      <div className="mt-4">
        <EventList events={events} d={d.definition} total={d.n_events} row={e => {
          const i = events.indexOf(e)
          const drillable = !crops && !!e.assets?.length
          return (
            <EventRow e={e} d={d.definition} onOpen={() => setEvent(e)}
              trailing={crops ? <span className="text-[12px] text-[var(--color-mute)] tabular-nums">{flow(e.spend_eur)} spend</span>
                : <span className="text-[12px] text-[var(--color-mute)] tabular-nums">{e.n_assets} asset{e.n_assets === 1 ? '' : 's'} · {balance(e.value_exposed_eur)}</span>}
              expanded={openIdx === i} onToggle={drillable ? () => setOpenIdx(openIdx === i ? null : i) : undefined}>
              <div className="pl-11 pb-2 space-y-0.5">
                {e.assets?.map(a => (
                  <div key={a.id} {...pressable(cfg && (() => setDrawerId(a.id)))}
                    className={`flex items-center gap-2 text-[12px] py-0.5 ${cfg ? 'cursor-pointer hover:text-[var(--color-sky)]' : ''}`}>
                    <span className="text-[var(--color-mute)] min-w-0 truncate">{a.name}</span>
                    <span className="flex-1" />
                    <span className="text-[11.5px] text-[var(--color-faint)] tabular-nums">{balance(a.value_eur)} · {a.closest_km} km</span>
                  </div>
                ))}
              </div>
            </EventRow>
          )
        }} />
      </div>
    </Card>
    </div>
    {/* the drawer and the pop-ups stay outside the forced-dark wrapper so they follow the app theme */}
    {drawerId && cfg && <AssetDrawer cfg={cfg} id={drawerId} onClose={() => setDrawerId(null)} onChanged={() => q.refetch()} />}
    {event && <EventDialog e={event} d={d.definition} onClose={() => setEvent(null)} />}
    {about && <Dialog title={d.message.label} onClose={() => setAbout(false)} className="max-w-xl"><DetailsBody sections={withSources(d.message, d.sources)} /></Dialog>}
    </>
  )
}
