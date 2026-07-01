import { useState, useMemo, useCallback } from 'react'
import { ChevronRight, Clock } from 'lucide-react'
import { PERSONAS, catalogFor } from './data/catalog'
import LineageBar from './components/software/LineageBar'
import CatalogNav from './components/software/CatalogNav'
import CatalogGrid from './components/software/CatalogGrid'
import CommandCenter from './pages/bank/CommandCenter'
import Portfolio from './pages/bank/Portfolio'
import RiskMapBank from './pages/bank/RiskMapBank'
import Signals from './pages/bank/Signals'
import Reports from './pages/bank/Reports'
import ModelsPage from './pages/ModelsPage'
import PlatformOverviewPage from './pages/PlatformOverviewPage'
import LandingPage from './pages/LandingPage'
import SolutionsPage from './pages/SolutionsPage'

const WORKFLOWS = { CommandCenter, Portfolio, RiskMapBank, Signals, Reports, ModelsPage, PlatformOverviewPage }
const DEFAULT_ROUTE = { offeringId: 'physical-risk', serviceId: 'command' }

export default function App() {
  const [view, setView] = useState('landing')   // 'landing' | 'solutions' | 'app'
  const [personaId, setPersonaId] = useState('meridian')
  const [route, setRoute] = useState(DEFAULT_ROUTE)

  const persona = useMemo(() => PERSONAS.find(p => p.id === personaId) || PERSONAS[0], [personaId])
  const catalog = useMemo(() => catalogFor(persona), [persona])

  const onPersona = useCallback(id => {
    setPersonaId(id)
    setRoute({})   // land on the new customer's catalog home
  }, [])

  // internal cross-links (e.g. Command Center's "view full portfolio")
  const onGoto = useCallback(v => {
    if (v === 'bank-portfolio') setRoute({ offeringId: 'physical-risk', serviceId: 'portfolio' })
  }, [])

  // All hooks must run before any early return (Rules of Hooks).
  if (view === 'landing')
    return <LandingPage onEnter={() => setView('app')} onExplore={() => setView('solutions')} />
  if (view === 'solutions')
    return <SolutionsPage onHome={() => setView('landing')} onEnter={() => setView('app')} />

  const offering = route.offeringId && catalog?.offerings.find(o => o.id === route.offeringId)
  const service = offering && route.serviceId && offering.services.find(s => s.id === route.serviceId)
  const Workflow = service?.workflow && WORKFLOWS[service.workflow]

  return (
    <div className="flex h-screen flex-col bg-[#f5f5f7]">
      <LineageBar personas={PERSONAS} personaId={personaId} onPersona={onPersona} />
      <div className="flex flex-1 overflow-hidden">
        <CatalogNav catalog={catalog} route={route} onNavigate={setRoute} />
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* breadcrumb + process stages */}
          <div className="flex items-center justify-between gap-4 border-b border-gray-200 bg-white/70 px-6 py-2 backdrop-blur">
            <div className="flex items-center gap-1.5 text-[12px] text-gray-500">
              <button onClick={() => setRoute({})} className="hover:text-[#1d1d1f]">{catalog?.label || 'Home'}</button>
              {offering && <><ChevronRight size={13} className="text-gray-300" />
                <button onClick={() => setRoute({ offeringId: offering.id })}
                  className={service ? 'hover:text-[#1d1d1f]' : 'font-medium text-[#1d1d1f]'}>{offering.label}</button></>}
              {service && <><ChevronRight size={13} className="text-gray-300" />
                <span className="font-medium text-[#1d1d1f]">{service.label}</span></>}
            </div>
            {service?.processes && (
              <div className="hidden items-center gap-1 text-[10px] text-gray-400 lg:flex">
                <span className="mr-1 uppercase tracking-wide">process</span>
                {service.processes.map((p, i) => (
                  <span key={p} className="flex items-center gap-1">
                    {i > 0 && <span className="text-gray-300">›</span>}{p}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="flex-1 overflow-hidden">
            {service
              ? (Workflow
                  ? <Workflow onGoto={onGoto} onSelectIndustry={() => {}} />
                  : <ComingSoon service={service} />)
              : <CatalogGrid catalog={catalog} route={route} onNavigate={setRoute} />}
          </div>
        </div>
      </div>
    </div>
  )
}

function ComingSoon({ service }) {
  return (
    <div className="flex h-full items-center justify-center bg-[#f5f5f7]">
      <div className="max-w-sm rounded-2xl border border-gray-200/70 bg-white p-8 text-center shadow-sm">
        <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-gray-100 text-gray-500">
          <Clock size={20} />
        </span>
        <h2 className="mt-3 text-lg font-semibold text-[#1d1d1f]">{service.label}</h2>
        <p className="mt-1 text-[13px] text-gray-500">{service.blurb}</p>
        <p className="mt-3 text-[11px] text-gray-400">
          Same golden source, different output maths — workflow on the roadmap.
          Process: {service.processes?.join(' › ')}
        </p>
      </div>
    </div>
  )
}
