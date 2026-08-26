import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './lib/auth'
import Login from './pages/Login'
import Shell from './components/Shell'
import Horizon from './pages/Horizon'
import Home from './pages/Home'
import Disclosure from './pages/Disclosure'
import Csrd from './pages/Csrd'
import EsrsPack from './pages/EsrsPack'
import Approvals from './pages/Approvals'
import Audit from './pages/Audit'
import Admin from './pages/Admin'
import Contracts from './pages/Contracts'
import Onboarding from './pages/Onboarding'
import IntakeReview from './pages/IntakeReview'
import IntakeForm from './pages/IntakeForm'
import Activate from './pages/Activate'
import Platform from './pages/Platform'
import Cogs from './pages/Cogs'
import Portfolio from './pages/Portfolio'
import Compliance from './pages/Compliance'
import PriorFilings from './pages/PriorFilings'
import DataHub from './pages/DataHub'
import Analytics from './pages/Analytics'
import Decisions from './pages/Decisions'
import Tasks from './pages/Tasks'
import Exceptions from './pages/Exceptions'
import Oversight from './pages/Oversight'
import Calendar from './pages/Calendar'
import Kri from './pages/Kri'
import Transmission from './pages/Transmission'
import RegChanges from './pages/RegChanges'
import DataDictionary from './pages/DataDictionary'
import Filings from './pages/Filings'
import Funds from './pages/Funds'
import FundDetail from './pages/FundDetail'
import Models from './pages/Models'
import EarlyWarning from './pages/EarlyWarning'
import Sourcing from './pages/Sourcing'
import Operations from './pages/Operations'
import DataFoundation from './pages/DataFoundation'
import RiskMap from './pages/RiskMap'
import TrackRecord from './pages/TrackRecord'
import UnderwritingReview from './pages/UnderwritingReview'
import ModelValidation from './pages/ModelValidation'
import DetailView from './pages/DetailView'
import CommodityDetail from './pages/CommodityDetail'
import Support from './pages/Support'
import Docs from './pages/Docs'

export default function App() {
  // Public, pre-authentication surfaces — a client fills their intake and each user activates their
  // account BEFORE any tenant/session exists, so these must render outside the auth gate.
  return (
    <Routes>
      <Route path="/onboarding/form/:token" element={<IntakeForm />} />
      <Route path="/activate/:token" element={<Activate />} />
      <Route path="*" element={<Workspace />} />
    </Routes>
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
        {/* the front door — Horizon globe (customer workspaces); operators skip to their console */}
        <Route path="/" element={opsOnly ? <Navigate to="/platform" replace /> : <Horizon />} />
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
        <Route path="/data-dictionary" element={<DataDictionary />} />
        <Route path="/filings" element={<Filings />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/contracts" element={<Contracts />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/intake" element={<IntakeReview />} />
        <Route path="/platform" element={<Platform />} />
        <Route path="/cogs" element={<Cogs />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/track-record" element={<TrackRecord />} />
        <Route path="/underwriting" element={<UnderwritingReview />} />
        <Route path="/model-validation" element={<ModelValidation />} />
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
  return <Shell><Outlet /></Shell>
}

function Splash() {
  return (
    <div className="h-screen grid place-items-center text-[var(--color-faint)] mono text-sm">
      loading…
    </div>
  )
}
