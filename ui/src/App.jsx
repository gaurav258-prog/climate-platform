import { useState, useMemo, useCallback, useEffect } from 'react'
import { ChevronRight, Clock } from 'lucide-react'
import { CATALOG, catalogForAuth, industryForOrg } from './data/catalog'
import { fetchMe, logout as apiLogout, hasToken } from './api/client'
import LineageBar from './components/software/LineageBar'
import CommandPalette from './components/CommandPalette'
import WelcomeNudge from './components/WelcomeNudge'
import CatalogNav from './components/software/CatalogNav'
import CatalogGrid from './components/software/CatalogGrid'
import CommandCenter from './pages/bank/CommandCenter'
import Portfolio from './pages/bank/Portfolio'
import RiskMapBank from './pages/bank/RiskMapBank'
import Signals from './pages/bank/Signals'
import Reports from './pages/bank/Reports'
import MethodologyPage from './pages/bank/MethodologyPage'
import ModelsPage from './pages/ModelsPage'
import PlatformOverviewPage from './pages/PlatformOverviewPage'
import CogsCommand from './pages/supply/CogsCommand'
import SourcingBook from './pages/supply/SourcingBook'
import RiskMapSupply from './pages/supply/RiskMapSupply'
import SupplySignals from './pages/supply/SupplySignals'
import SupplyDisclosure from './pages/supply/SupplyDisclosure'
import SupplyModels from './pages/supply/SupplyModels'
import LossCurvePricing from './pages/insurance/LossCurvePricing'
import ParametricTriggers from './pages/insurance/ParametricTriggers'
import RealEstatePortfolioImpact from './pages/realestate/PortfolioImpact'
import AssetMgmtPortfolioVaR from './pages/assetmgmt/PortfolioVaR'
import FundsOverview from './pages/assetmgmt/FundsOverview'
import FundOnboarding from './pages/assetmgmt/FundOnboarding'
import LandingPage from './pages/LandingPage'
import LookupScorePage from './pages/LookupScorePage'
import SolutionsPage from './pages/SolutionsPage'
import LoginPage from './pages/LoginPage'
import DocumentationPage from './pages/DocumentationPage'
import ServicePortalPage from './pages/ServicePortalPage'
import AdminPage from './pages/admin/AdminPage'

const WORKFLOWS = { CommandCenter, Portfolio, RiskMapBank, Signals, Reports, MethodologyPage, ModelsPage, PlatformOverviewPage, CogsCommand, SourcingBook, RiskMapSupply, SupplySignals, SupplyDisclosure, SupplyModels, LossCurvePricing, ParametricTriggers, RealEstatePortfolioImpact, AssetMgmtPortfolioVaR, FundsOverview, FundOnboarding }

// industries.js (marketing copy) and catalog.js (real nav tree) use different id
// conventions for the same two sectors — reconcile before looking up CATALOG.
const INDUSTRY_ID_MAP = { 'asset-management': 'assetmgmt', 'real-estate': 'realestate' }

// Land on the tenant's OWN first service (not a hardcoded banking route), so a
// bank lands on Command Center, a food maker on COGS-at-risk, an insurer on theirs.
function firstRoute(catalog) {
  const off = catalog?.offerings?.[0]
  const svc = off?.services?.find(s => s.workflow) || off?.services?.[0]
  return off && svc ? { offeringId: off.id, serviceId: svc.id } : {}
}

export default function App() {
  const [view, setView] = useState('landing')     // 'landing' | 'solutions' | 'login' | 'lookup' | 'app'
  const [auth, setAuth] = useState(null)           // /me payload once logged in
  const [authLoading, setAuthLoading] = useState(hasToken())
  const [area, setArea] = useState('modules')      // 'modules' | 'docs' | 'portal' | 'admin'
  const [route, setRoute] = useState({})
  const [solutionsSector, setSolutionsSector] = useState(null)
  const [docsSection, setDocsSection] = useState('start')
  const [paletteOpen, setPaletteOpen] = useState(false)

  // Rehydrate the session on load so a refresh keeps you logged in.
  useEffect(() => {
    if (!hasToken()) return
    fetchMe().then(a => { setAuth(a); setRoute(firstRoute(catalogForAuth(a))) })
      .catch(() => {}).finally(() => setAuthLoading(false))
  }, [])

  const catalog = useMemo(() => catalogForAuth(auth), [auth])

  // Cmd/Ctrl+K opens the command palette from anywhere in the app; "?" is the
  // familiar SaaS shorthand for the same, but only when not typing into a field.
  useEffect(() => {
    if (view !== 'app' || !auth) return
    const handler = (e) => {
      const typing = ['INPUT', 'TEXTAREA'].includes(e.target.tagName) || e.target.isContentEditable
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen(o => !o) }
      else if (e.key === '?' && !typing) { e.preventDefault(); setPaletteOpen(true) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [view, auth])

  const onLoginSuccess = useCallback((a) => {
    setAuth(a); setArea('modules'); setRoute(firstRoute(catalogForAuth(a))); setView('app')
  }, [])
  const onLogout = useCallback(async () => {
    await apiLogout(); setAuth(null); setView('landing')
  }, [])
  // `wantIndustry` is set when entering from a specific Solutions sector. If you're signed in
  // as a different industry's account, drop to login so you can pick the matching demo account
  // (otherwise you'd silently land in your own — e.g. clicking Agriculture while a bank user).
  const enterApp = useCallback((wantIndustry) => {
    // only a string is a real industry hint (generic onClick handlers pass the event object)
    const want = typeof wantIndustry === 'string' ? wantIndustry : null
    if (auth && want && industryForOrg(auth.org) !== want) {
      apiLogout().catch(() => {}); setAuth(null); setView('login'); return
    }
    setView(auth ? 'app' : 'login')
  }, [auth])

  const onGoto = useCallback(v => {
    if (v === 'bank-portfolio') { setArea('modules'); setRoute({ offeringId: 'physical-risk', serviceId: 'portfolio' }); return }
    if (v === 'assetmgmt-funds') { setArea('modules'); setRoute({ offeringId: 'securities', serviceId: 'funds' }); return }
    // 'docs:<section>' -- contextual help links from any workflow page jump straight
    // to the relevant Documentation section, instead of dumping the user on 'Getting
    // started' regardless of what they clicked "?" on.
    if (typeof v === 'string' && v.startsWith('docs:')) { setDocsSection(v.slice(5)); setArea('docs') }
  }, [])

  // Industry-modules marketing grid (PlatformOverviewPage) → real navigation.
  // A built sector you're already licensed for jumps in-app; a different licensed
  // sector routes through the same cross-industry login switch used elsewhere.
  const onSelectIndustry = useCallback((indId) => {
    const catId = INDUSTRY_ID_MAP[indId] || indId
    if (!CATALOG[catId]) return // roadmap sector — nothing built to open yet
    if (auth && industryForOrg(auth.org) === catId) {
      setArea('modules'); setRoute(firstRoute(catalogForAuth(auth)))
    } else {
      enterApp(catId)
    }
  }, [auth, enterApp])

  // `sectorId` lets a specific "For banks"-style card jump straight into that
  // sector's detail page on Solutions, instead of always landing on the index.
  const onExplore = useCallback((sectorId) => {
    setSolutionsSector(typeof sectorId === 'string' ? sectorId : null)
    setView('solutions')
  }, [])

  // ── Marketing / auth views (all hooks above run first) ──
  if (view === 'landing')
    return <LandingPage onEnter={enterApp} onExplore={onExplore} onLookup={() => setView('lookup')} />
  if (view === 'lookup')
    return <LookupScorePage onHome={() => setView('landing')} />
  if (view === 'solutions')
    return <SolutionsPage onHome={() => setView('landing')} onEnter={enterApp} initialSector={solutionsSector} />
  if (view === 'login')
    return <LoginPage onSuccess={onLoginSuccess} onHome={() => setView('landing')} />

  // view === 'app' — requires a session
  if (!auth) {
    if (authLoading) return <div className="flex h-screen items-center justify-center bg-[#f5f5f7] text-gray-400">Loading…</div>
    return <LoginPage onSuccess={onLoginSuccess} onHome={() => setView('landing')} />
  }

  const offering = route.offeringId && catalog?.offerings.find(o => o.id === route.offeringId)
  const service = offering && route.serviceId && offering.services.find(s => s.id === route.serviceId)
  const Workflow = service?.workflow && WORKFLOWS[service.workflow]
  const perms = new Set(auth?.permissions || [])
  const canSeePortal = perms.has('portal.use')
  const canSeeAdmin = ['admin.users.manage', 'admin.roles.manage', 'admin.audit.view', 'approvals.view', 'approvals.decide'].some(p => perms.has(p))

  return (
    <div className="flex h-screen flex-col bg-[#f5f5f7]">
      <LineageBar auth={auth} area={area} onArea={setArea} onLogout={onLogout} onSearch={() => setPaletteOpen(true)} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} catalog={catalog}
        onNavigate={(offeringId, serviceId) => { setArea('modules'); setRoute({ offeringId, serviceId }) }}
        onDocs={section => { setDocsSection(section); setArea('docs') }}
        onArea={setArea} canSeePortal={canSeePortal} canSeeAdmin={canSeeAdmin} />
      <WelcomeNudge email={auth?.user?.email} orgLabel={auth?.org?.name || 'your'} onOpenSearch={() => setPaletteOpen(true)} />

      {area === 'modules' && (
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
                    ? <Workflow onGoto={onGoto} onSelectIndustry={onSelectIndustry} auth={auth} />
                    : <ComingSoon service={service} />)
                : <CatalogGrid catalog={catalog} route={route} onNavigate={setRoute} />}
            </div>
          </div>
        </div>
      )}

      {area === 'docs'   && <div className="flex-1 overflow-hidden"><DocumentationPage auth={auth} initialSection={docsSection} /></div>}
      {area === 'portal' && <div className="flex-1 overflow-hidden"><ServicePortalPage /></div>}
      {area === 'admin'  && <div className="flex-1 overflow-hidden"><AdminPage auth={auth} /></div>}
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
