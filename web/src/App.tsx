import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from './lib/auth'
import { api } from './lib/api'
import Login from './pages/Login'
import Shell from './components/Shell'

// Route-level code-splitting: each page ships as its own chunk, loaded on demand, so the initial
// bundle stays small. Login + Shell are eager (first paint / layout); everything else is lazy.
const Horizon = lazy(() => import('./pages/Horizon'))
const Home = lazy(() => import('./pages/Home'))
const Disclosure = lazy(() => import('./pages/Disclosure'))
const Csrd = lazy(() => import('./pages/Csrd'))
const EsrsPack = lazy(() => import('./pages/EsrsPack'))
const Approvals = lazy(() => import('./pages/Approvals'))
const Audit = lazy(() => import('./pages/Audit'))
const Admin = lazy(() => import('./pages/Admin'))
const Contracts = lazy(() => import('./pages/Contracts'))
const Onboarding = lazy(() => import('./pages/Onboarding'))
const IntakeReview = lazy(() => import('./pages/IntakeReview'))
const IntakeForm = lazy(() => import('./pages/IntakeForm'))
const Activate = lazy(() => import('./pages/Activate'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))
const Signup = lazy(() => import('./pages/Signup'))
const Billing = lazy(() => import('./pages/Billing'))
const AccountSecurity = lazy(() => import('./pages/AccountSecurity'))
const SingleSignOn = lazy(() => import('./pages/SingleSignOn'))
const Platform = lazy(() => import('./pages/Platform'))
const Cogs = lazy(() => import('./pages/Cogs'))
const Portfolio = lazy(() => import('./pages/Portfolio'))
const Compliance = lazy(() => import('./pages/Compliance'))
const PriorFilings = lazy(() => import('./pages/PriorFilings'))
const DataHub = lazy(() => import('./pages/DataHub'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Decisions = lazy(() => import('./pages/Decisions'))
const Tasks = lazy(() => import('./pages/Tasks'))
const Exceptions = lazy(() => import('./pages/Exceptions'))
const Oversight = lazy(() => import('./pages/Oversight'))
const Calendar = lazy(() => import('./pages/Calendar'))
const Kri = lazy(() => import('./pages/Kri'))
const Transmission = lazy(() => import('./pages/Transmission'))
const RegChanges = lazy(() => import('./pages/RegChanges'))
const RegPipeline = lazy(() => import('./pages/RegPipeline'))
const DataDictionary = lazy(() => import('./pages/DataDictionary'))
const Filings = lazy(() => import('./pages/Filings'))
const Funds = lazy(() => import('./pages/Funds'))
const FundDetail = lazy(() => import('./pages/FundDetail'))
const Models = lazy(() => import('./pages/Models'))
const EarlyWarning = lazy(() => import('./pages/EarlyWarning'))
const Sourcing = lazy(() => import('./pages/Sourcing'))
const Operations = lazy(() => import('./pages/Operations'))
const DataFoundation = lazy(() => import('./pages/DataFoundation'))
const RiskMap = lazy(() => import('./pages/RiskMap'))
const TrackRecord = lazy(() => import('./pages/TrackRecord'))
const UnderwritingReview = lazy(() => import('./pages/UnderwritingReview'))
const ModelValidation = lazy(() => import('./pages/ModelValidation'))
const Coverage = lazy(() => import('./pages/Coverage'))
const DetailView = lazy(() => import('./pages/DetailView'))
const CommodityDetail = lazy(() => import('./pages/CommodityDetail'))
const Support = lazy(() => import('./pages/Support'))
const Docs = lazy(() => import('./pages/Docs'))

export default function App() {
  // Public, pre-authentication surfaces — a client fills their intake and each user activates their
  // account BEFORE any tenant/session exists, so these must render outside the auth gate.
  return (
    <Suspense fallback={<Splash />}>
      <Routes>
        <Route path="/onboarding/form/:token" element={<IntakeForm />} />
        <Route path="/activate/:token" element={<Activate />} />
        <Route path="/reset/:token" element={<ResetPassword />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="*" element={<Workspace />} />
      </Routes>
    </Suspense>
  )
}

function Workspace() {
  const { profile, loading } = useAuth()

  if (loading) return <Splash />
  if (!profile) return <Login />

  // a platform operator (no customer workspace access) lands on the cross-tenant console
  const opsOnly = profile.permissions?.includes('platform.admin') && !profile.permissions?.includes('modules.view')

  return (
    <Routes>
      {/* everything lives inside the operating Shell — the Horizon front door too, so the nav is consistent.
          Horizon renders full-bleed inside the content area (Shell drops the padded <main> for '/'). */}
      <Route element={<ShellLayout />}>
        {/* the front door — Horizon globe (customer workspaces); operators skip to their console;
            a first-run admin whose org isn't Live yet is funnelled to Get started until it is */}
        <Route path="/" element={opsOnly ? <Navigate to="/platform" replace /> : <FirstRunGate />} />
        {/* the Horizon globe as an explicit destination — the sidebar's "Horizon" item points here, so it
            always opens the earth even for a first-run admin (whose front door "/" still funnels to Get started) */}
        <Route path="/horizon" element={<Horizon />} />
        <Route path="/home" element={<Home />} />
        <Route path="/disclosure" element={<Disclosure />} />
        <Route path="/csrd" element={<Csrd />} />
        <Route path="/esrs" element={<EsrsPack />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/exceptions" element={<Exceptions />} />
        <Route path="/oversight" element={<Oversight />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/kri" element={<Kri />} />
        <Route path="/transmission" element={<Transmission />} />
        <Route path="/reg-changes" element={<RegChanges />} />
        <Route path="/reg-pipeline" element={<RegPipeline />} />
        <Route path="/data-dictionary" element={<DataDictionary />} />
        <Route path="/filings" element={<Filings />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/contracts" element={<Contracts />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/sso" element={<SingleSignOn />} />
        <Route path="/billing" element={<Billing />} />
        <Route path="/account-security" element={<AccountSecurity />} />
        <Route path="/intake" element={<IntakeReview />} />
        <Route path="/platform" element={<Platform />} />
        <Route path="/cogs" element={<Cogs />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/track-record" element={<TrackRecord />} />
        <Route path="/underwriting" element={<UnderwritingReview />} />
        <Route path="/model-validation" element={<ModelValidation />} />
        <Route path="/coverage" element={<Coverage />} />
        <Route path="/funds" element={<Funds />} />
        <Route path="/funds/:id" element={<FundDetail />} />
        <Route path="/compliance" element={<Compliance />} />
        <Route path="/prior-filings" element={<PriorFilings />} />
        <Route path="/data" element={<DataHub />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/decisions" element={<Decisions />} />
        <Route path="/sourcing" element={<Sourcing />} />
        <Route path="/operations" element={<Operations />} />
        <Route path="/detail/site/:id" element={<DetailView kind="site" />} />
        <Route path="/detail/plot/:id" element={<DetailView kind="plot" />} />
        <Route path="/detail/commodity/:id" element={<CommodityDetail />} />
        <Route path="/riskmap" element={<RiskMap />} />
        <Route path="/early-warning" element={<EarlyWarning />} />
        <Route path="/models" element={<Models />} />
        <Route path="/foundation" element={<DataFoundation />} />
        <Route path="/support" element={<Support />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

function ShellLayout() {
  return <Shell><Suspense fallback={<Splash />}><Outlet /></Suspense></Shell>
}

// First-run funnel: an admin whose organisation hasn't reached "Live" lands on Get started (the derived
// onboarding checklist) instead of the globe — until every required step is done. Non-admins and Live orgs
// go straight to Horizon. The rest of the app stays reachable via the nav; only the front door is funnelled.
function FirstRunGate() {
  const { profile } = useAuth()
  const isAdmin = profile?.permissions?.includes('admin.users.manage')
  const q = useQuery({
    queryKey: ['onboarding-gate'],
    queryFn: () => api.get<{ available: boolean; live: boolean }>('/v1/admin/onboarding'),
    enabled: !!isAdmin,
  })
  if (isAdmin && q.isLoading) return <Splash />
  if (isAdmin && q.data?.available && !q.data.live) return <Navigate to="/onboarding" replace />
  return <Horizon />
}

function Splash() {
  return (
    <div className="h-screen grid place-items-center text-[var(--color-faint)] mono text-sm">
      loading…
    </div>
  )
}
