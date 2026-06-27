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
import AppleSeismicPageTabbed from './pages/AppleSeismicPageTabbed'
import AppleFloodPageTabbed from './pages/AppleFloodPageTabbed'
import AppleWildfirePageTabbed from './pages/AppleWildfirePageTabbed'
import AppleHeatPageTabbed from './pages/AppleHeatPageTabbed'
import AppleRegulatoryPage from './pages/AppleRegulatoryPage'
import RegulatoryReportingHome from './pages/RegulatoryReportingHome'
import DataIngestionPage from './pages/DataIngestionPage'
import ScenarioFinancialImpactPage from './pages/ScenarioFinancialImpactPage'
import ComplianceGapAnalysisPage from './pages/ComplianceGapAnalysisPage'
import RiskMaterialityPage from './pages/RiskMaterialityPage'
import TimelineTrackingPage from './pages/TimelineTrackingPage'
import PortfolioAggregationPage from './pages/PortfolioAggregationPage'
import RegulatoryChangeDetectionPage from './pages/RegulatoryChangeDetectionPage'
import BenchmarkingPage from './pages/BenchmarkingPage'
import AuditTrailPage from './pages/AuditTrailPage'
import TCFDReportPage from './pages/TCFDReportPage'
import EUTaxonomyReportPage from './pages/EUTaxonomyReportPage'
import RegulatoryRiskDashboardPage from './pages/RegulatoryRiskDashboardPage'
import RiskMapHome from './pages/RiskMapHome'
import PlatformOverviewPage from './pages/PlatformOverviewPage'
import IndustryModulePage from './pages/IndustryModulePage'
import ModelsPage from './pages/ModelsPage'
import LiveEventsPage from './pages/LiveEventsPage'
import { generateMockScores, generateAlerts, getDates } from './mockData'
import { ACTION_TEMPLATES } from './mockRegions'

const POLICIES_COUNT = 5 // matches ParametricPage

export default function App() {
  const [view, setView]                = useState('platform')
  const [hazard, setHazard]            = useState(null)
  const [regulatoryModule, setRegulatoryModule] = useState(null)
  const [industryId, setIndustryId] = useState(null)
  const [showDataIngestion, setShowDataIngestion] = useState(false)
  const [dayIndex, setDayIndex]        = useState(10)
  const [selected, setSelected]        = useState(null)

  const dates  = useMemo(() => hazard ? getDates(hazard) : [], [hazard])
  const scores = useMemo(() => hazard ? generateMockScores(hazard, dayIndex) : [], [hazard, dayIndex])
  const alerts = useMemo(() => hazard ? generateAlerts(hazard) : [], [hazard])

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
          activeIndustry={industryId}
          onSelectIndustry={id => { setIndustryId(id); setView('industry') }}
          urgentCount={urgentCount}
          triggeredCount={triggeredCount}
        />

        {/* Content */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {view === 'platform' ? (
            <PlatformOverviewPage onSelectIndustry={id => { setIndustryId(id); setView('industry') }} />
          ) : view === 'models' ? (
            <ModelsPage />
          ) : view === 'live' ? (
            <LiveEventsPage />
          ) : view === 'industry' ? (
            <IndustryModulePage industryId={industryId} />
          ) : view === 'data-ingestion' ? (
            <DataIngestionPage />
          ) : view === 'dashboard' ? (
            <AppleDashboard
              onViewChange={setView}
              onHazardChange={handleHazardChange}
            />
          ) : view === 'map' ? (
            hazard === 'flood' ? (
              <AppleFloodPageTabbed />
            ) : hazard === 'wildfire' ? (
              <AppleWildfirePageTabbed />
            ) : hazard === 'heat' ? (
              <AppleHeatPageTabbed />
            ) : hazard === 'seismic' ? (
              <AppleSeismicPageTabbed />
            ) : (
              <RiskMapHome onHazardSelect={h => { setView('map'); handleHazardChange(h) }} />
            )
          ) : view === 'operations' ? (
            <AppleOperationsPage />
          ) : view === 'parametric' ? (
            <AppleParametricPage />
          ) : view === 'regulatory' ? (
            regulatoryModule === 'scenario-impact' ? <ScenarioFinancialImpactPage /> :
            regulatoryModule === 'compliance-gap' ? <ComplianceGapAnalysisPage /> :
            regulatoryModule === 'risk-materiality' ? <RiskMaterialityPage /> :
            regulatoryModule === 'timeline-tracking' ? <TimelineTrackingPage /> :
            regulatoryModule === 'portfolio-aggregation' ? <PortfolioAggregationPage /> :
            regulatoryModule === 'regulatory-changes' ? <RegulatoryChangeDetectionPage /> :
            regulatoryModule === 'benchmarking' ? <BenchmarkingPage /> :
            regulatoryModule === 'audit-trail' ? <AuditTrailPage /> :
            regulatoryModule === 'tcfd-report' ? <TCFDReportPage /> :
            regulatoryModule === 'taxonomy-report' ? <EUTaxonomyReportPage /> :
            regulatoryModule === 'risk-dashboard' ? <RegulatoryRiskDashboardPage /> :
            regulatoryModule === 'alerts' ? <AppleRegulatoryPage /> :
            <RegulatoryReportingHome onModuleSelect={m => setRegulatoryModule(m)} />
          ) : (
            <AppleCompliancePage />
          )}
        </div>
      </div>
    </div>
  )
}
