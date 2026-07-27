import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './lib/auth'
import Login from './pages/Login'
import Shell from './components/Shell'
import Home from './pages/Home'
import Disclosure from './pages/Disclosure'
import Cogs from './pages/Cogs'
import Models from './pages/Models'
import EarlyWarning from './pages/EarlyWarning'
import Sourcing from './pages/Sourcing'
import DataFoundation from './pages/DataFoundation'
import RiskMap from './pages/RiskMap'

export default function App() {
  const { profile, loading } = useAuth()

  if (loading) return <Splash />
  if (!profile) return <Login />

  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/disclosure" element={<Disclosure />} />
        <Route path="/cogs" element={<Cogs />} />
        <Route path="/sourcing" element={<Sourcing />} />
        <Route path="/riskmap" element={<RiskMap />} />
        <Route path="/early-warning" element={<EarlyWarning />} />
        <Route path="/models" element={<Models />} />
        <Route path="/foundation" element={<DataFoundation />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  )
}

function Splash() {
  return (
    <div className="h-screen grid place-items-center text-[var(--color-faint)] mono text-sm">
      loading…
    </div>
  )
}
