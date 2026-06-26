import { useState, useMemo, useCallback } from 'react'
import { latLngToCell } from 'h3-js'
import Topbar from './components/Topbar'
import Sidebar from './components/Sidebar'
import StatsBar from './components/StatsBar'
import RiskMap from './components/RiskMap'
import AlertFeed from './components/AlertFeed'
import ScoreLegend from './components/ScoreLegend'
import CellDetail from './components/CellDetail'
import TimeSlider from './components/TimeSlider'
import DashboardPage from './pages/DashboardPage'
import AppleDashboard from './pages/AppleDashboard'
import CompliancePage from './pages/CompliancePage'
import AppleCompliancePage from './pages/AppleCompliancePage'
import ParametricPage from './pages/ParametricPage'
import AppleParametricPage from './pages/AppleParametricPage'
import OperationsPage from './pages/OperationsPage'
import AppleOperationsPage from './pages/AppleOperationsPage'
import SeismicPage from './pages/SeismicPage'
import EnhancedSeismicPage from './pages/EnhancedSeismicPage'
import AppleSeismicPage from './pages/AppleSeismicPage'
import AppleFloodPage from './pages/AppleFloodPage'
import AppleWildfirePage from './pages/AppleWildfirePage'
import AppleHeatPage from './pages/AppleHeatPage'
import { generateMockScores, generateAlerts, getDates } from './mockData'
import { ACTION_TEMPLATES } from './mockRegions'

const POLICIES_COUNT = 5 // matches ParametricPage

export default function App() {
  const [view, setView]         = useState('dashboard')
  const [hazard, setHazard]     = useState('flood')
  const [dayIndex, setDayIndex] = useState(10)
  const [selected, setSelected] = useState(null)

  const dates  = useMemo(() => getDates(hazard), [hazard])
  const scores = useMemo(() => generateMockScores(hazard, dayIndex), [hazard, dayIndex])
  const alerts = useMemo(() => generateAlerts(hazard), [hazard])

  const urgentCount = useMemo(() =>
    (ACTION_TEMPLATES[hazard] ?? []).filter(a => a.priority === 'URGENT').length,
    [hazard]
  )

  // Count triggered parametric policies for badge
  const triggeredCount = useMemo(() => {
    const POLICIES = [
      { lat: 50.529, lng: 6.993, threshold: 60 },
      { lat: 50.938, lng: 6.960, threshold: 55 },
      { lat: 50.733, lng: 7.100, threshold: 50 },
      { lat: 50.937, lng: 6.961, threshold: 65 },
      { lat: 50.356, lng: 7.591, threshold: 58 },
    ]
    const scoreMap = new Map(scores.map(s => [s.h3_cell, s.score]))
    return POLICIES.filter(p => {
      const cell = latLngToCell(p.lat, p.lng, 8)
      return (scoreMap.get(cell) ?? 0) >= p.threshold
    }).length
  }, [scores])

  const handleHazardChange = useCallback(h => {
    setHazard(h)
    setSelected(null)
    setDayIndex(10)
  }, [])

  const handleDayChange = useCallback(v => {
    setDayIndex(typeof v === 'function' ? v : Number(v))
  }, [])

  return (
    <div className="flex flex-col h-screen bg-slate-950">
      <Topbar alertCount={urgentCount} />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activeView={view}
          onViewChange={v => { setView(v); setSelected(null) }}
          activeHazard={hazard}
          onHazardChange={handleHazardChange}
          urgentCount={urgentCount}
          triggeredCount={triggeredCount}
        />

        {/* Content */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {view === 'dashboard' ? (
            <AppleDashboard
              onViewChange={setView}
              onHazardChange={handleHazardChange}
            />
          ) : view === 'map' && hazard === 'flood' ? (
            <AppleFloodPage />
          ) : view === 'map' && hazard === 'wildfire' ? (
            <AppleWildfirePage />
          ) : view === 'map' && hazard === 'heat' ? (
            <AppleHeatPage />
          ) : view === 'map' && hazard === 'seismic' ? (
            <AppleSeismicPage />
          ) : view === 'operations' ? (
            <AppleOperationsPage />
          ) : view === 'parametric' ? (
            <AppleParametricPage />
          ) : (
            <AppleCompliancePage />
          )}
        </div>
      </div>
    </div>
  )
}
