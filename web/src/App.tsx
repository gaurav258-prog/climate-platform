import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './lib/auth'
import Login from './pages/Login'
import Shell from './components/Shell'
import Disclosure from './pages/Disclosure'
import Cogs from './pages/Cogs'
import Models from './pages/Models'
import EarlyWarning from './pages/EarlyWarning'
import Placeholder from './pages/Placeholder'

export default function App() {
  const { profile, loading } = useAuth()

  if (loading) return <Splash />
  if (!profile) return <Login />

  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Navigate to="/disclosure" replace />} />
        <Route path="/disclosure" element={<Disclosure />} />
        <Route path="/cogs" element={<Cogs />} />
        <Route path="/sourcing" element={<Placeholder title="Sourcing book" />} />
        <Route path="/riskmap" element={<Placeholder title="Risk map" />} />
        <Route path="/early-warning" element={<EarlyWarning />} />
        <Route path="/models" element={<Models />} />
        <Route path="/foundation" element={<Placeholder title="Data foundation" />} />
        <Route path="*" element={<Navigate to="/disclosure" replace />} />
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
