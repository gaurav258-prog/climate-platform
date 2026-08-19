import { ICON } from './catalogIcons'

// Left drill-nav — the customer's entitled industry → offerings → services.
// Offering headers open the offering's catalog; services open their workflow.
export default function CatalogNav({ catalog, route, onNavigate }) {
  if (!catalog) return <nav className="w-60 shrink-0 border-r border-gray-200 bg-white" />
  return (
    <nav className="w-60 shrink-0 flex flex-col overflow-y-auto bg-white border-r border-gray-200 text-[#1d1d1f]">
      <button onClick={() => onNavigate({})}
        className="px-5 pt-5 pb-3 text-left">
        <div className="text-[15px] font-semibold tracking-tight">{catalog.label}</div>
        <div className="mt-0.5 text-[10px] uppercase tracking-[0.14em] text-gray-400">your workspace</div>
      </button>

      <div className="px-2.5 pb-4">
        {catalog.offerings.map(off => {
          const OffIcon = ICON[off.icon] || Layers2
          const offOpen = route.offeringId === off.id
          return (
            <div key={off.id} className="mb-1">
              <button onClick={() => onNavigate({ offeringId: off.id })}
                className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition ${
                  offOpen && !route.serviceId ? 'bg-gray-100' : 'hover:bg-gray-50'}`}>
                <OffIcon size={15} strokeWidth={1.7} className="text-gray-500" />
                <span className="text-[13px] font-medium">{off.label}</span>
              </button>
              <div className="ml-4 border-l border-gray-200 pl-2">
                {off.services.map(svc => {
                  const SvcIcon = ICON[svc.icon] || OffIcon
                  const active = route.serviceId === svc.id
                  return (
                    <button key={svc.id} onClick={() => onNavigate({ offeringId: off.id, serviceId: svc.id })}
                      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] transition ${
                        active ? 'bg-[#0071e3]/10 text-[#0071e3] font-medium'
                        : svc.workflow ? 'text-gray-600 hover:bg-gray-50 hover:text-[#1d1d1f]'
                        : 'text-gray-400'}`}>
                      <SvcIcon size={13} strokeWidth={1.7} />
                      <span className="flex-1 truncate">{svc.label}</span>
                      {!svc.workflow && <span className="text-[9px] text-gray-400">soon</span>}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-auto px-5 py-3 border-t border-gray-200">
        <p className="text-[9px] uppercase tracking-[0.14em] text-gray-400">Live feed</p>
        <p className="mt-0.5 flex items-center gap-1.5 text-xs text-emerald-600">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> USGS seismic · streaming
        </p>
      </div>
    </nav>
  )
}

function Layers2(props) { return <span {...props} /> }
