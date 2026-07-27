import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './lib/auth'
import Login from './pages/Login'
import Shell from './components/Shell'
import Disclosure from './pages/Disclosure'
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
        <Route path="/cogs" element={<Placeholder title="COGS-at-risk" />} />
        <Route path="/sourcing" element={<Placeholder title="Sourcing book" />} />
        <Route path="/riskmap" element={<Placeholder title="Risk map" />} />
        <Route path="/early-warning" element={<Placeholder title="Early warning" />} />
        <Route path="/models" element={<Placeholder title="Models & validation" />} />
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
