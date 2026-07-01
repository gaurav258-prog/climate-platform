import { ArrowRight } from 'lucide-react'
import { ICON } from './catalogIcons'

// The browse surface — cards at each catalog level. Home shows offerings;
// an offering shows its services (with their process stages), which open workflows.
export default function CatalogGrid({ catalog, route, onNavigate }) {
  if (!catalog) return null
  const offering = route.offeringId && catalog.offerings.find(o => o.id === route.offeringId)

  const items = offering ? offering.services : catalog.offerings
  const title = offering ? offering.label : `${catalog.label} — your offerings`
  const blurb = offering ? offering.blurb
    : 'Live data → cleaned by the AI engine → one golden source → your licensed offerings.'

  return (
    <div className="h-full overflow-y-auto bg-[#f5f5f7]">
      <div className="mx-auto max-w-4xl px-8 py-10">
        <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
          {offering ? 'Offering' : 'Workspace'}
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">{title}</h1>
        <p className="mt-2 max-w-2xl text-[15px] text-gray-500">{blurb}</p>

        <div className="mt-7 grid grid-cols-2 gap-4">
          {items.map(item => {
            const Icon = ICON[item.icon] || ArrowRight
            const open = offering ? { offeringId: offering.id, serviceId: item.id } : { offeringId: item.id }
            const locked = offering && !item.workflow
            return (
              <button key={item.id} onClick={() => !locked && onNavigate(open)}
                disabled={locked}
                className={`group rounded-2xl border border-gray-200/70 bg-white p-5 text-left shadow-sm transition ${
                  locked ? 'cursor-default opacity-60' : 'hover:border-gray-300 hover:shadow'}`}>
                <div className="flex items-start justify-between">
                  <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gray-100 text-gray-600">
                    <Icon size={17} strokeWidth={1.7} />
                  </span>
                  {locked
                    ? <span className="text-[10px] uppercase tracking-wide text-gray-400">coming soon</span>
                    : <ArrowRight size={16} className="text-gray-300 transition group-hover:text-[#0071e3]" />}
                </div>
                <h3 className="mt-3 text-[15px] font-semibold text-[#1d1d1f]">{item.label}</h3>
                <p className="mt-1 text-[13px] leading-snug text-gray-500">{item.blurb}</p>
                {offering && item.processes && (
                  <div className="mt-3 flex flex-wrap items-center gap-1 text-[10px] text-gray-400">
                    {item.processes.map((p, i) => (
                      <span key={p} className="flex items-center gap-1">
                        {i > 0 && <span className="text-gray-300">›</span>}{p}
                      </span>
                    ))}
                  </div>
                )}
                {!offering && (() => {
                  const n = catalog.offerings.find(o => o.id === item.id)?.services.length || 0
                  return <div className="mt-3 text-[11px] text-gray-400">{n} service{n === 1 ? '' : 's'}</div>
                })()}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
