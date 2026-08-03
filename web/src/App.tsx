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
import Platform from './pages/Platform'
import Cogs from './pages/Cogs'
import Portfolio from './pages/Portfolio'
import Compliance from './pages/Compliance'
import Tasks from './pages/Tasks'
import Exceptions from './pages/Exceptions'
import Calendar from './pages/Calendar'
import Kri from './pages/Kri'
import RConnect from './pages/RConnect'
import Models from './pages/Models'
import EarlyWarning from './pages/EarlyWarning'
import Sourcing from './pages/Sourcing'
import Operations from './pages/Operations'
import DataFoundation from './pages/DataFoundation'
import RiskMap from './pages/RiskMap'
import DetailView from './pages/DetailView'
import CommodityDetail from './pages/CommodityDetail'
import Support from './pages/Support'
import Docs from './pages/Docs'

export default function App() {
  const { profile, loading } = useAuth()

  if (loading) return <Splash />
  if (!profile) return <Login />

  // a platform operator (no customer workspace access) lands on the cross-tenant console
  const opsOnly = profile.permissions?.includes('platform.admin') && !profile.permissions?.includes('modules.view')

  return (
    <Routes>
      {/* the front door — full-screen Horizon globe (customer workspaces); operators skip to their console */}
      <Route path="/" element={opsOnly ? <Navigate to="/platform" replace /> : <Horizon />} />
      {/* everything else lives inside the operating Shell */}
      <Route element={<ShellLayout />}>
        <Route path="/home" element={<Home />} />
        <Route path="/disclosure" element={<Disclosure />} />
        <Route path="/csrd" element={<Csrd />} />
        <Route path="/esrs" element={<EsrsPack />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/exceptions" element={<Exceptions />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/kri" element={<Kri />} />
        <Route path="/rconnect" element={<RConnect />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/platform" element={<Platform />} />
        <Route path="/cogs" element={<Cogs />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/compliance" element={<Compliance />} />
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
        <Route path="*" element={<Navigate to="/home" replace />} />
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
