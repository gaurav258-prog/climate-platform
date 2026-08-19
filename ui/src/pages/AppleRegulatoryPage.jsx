import SimpleIcon from '../components/SimpleIcon'
import { useState, useEffect, useMemo } from 'react'
import { AlertCircle, CheckCircle, Clock, TrendingUp, ChevronRight, RefreshCw, ExternalLink } from 'lucide-react'

/**
 * Apple Store-inspired Regulatory Alerts Dashboard
 * Real-time regulatory change detection and compliance tracking
 * With animated backgrounds by urgency level
 */
export default function AppleRegulatoryPage() {
  const API_BASE = 'http://localhost:8000'
  const ORG_ID = 'demo-org'

  const [loading, setLoading] = useState(true)
  const [dashboard, setDashboard] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [peerContext, setPeerContext] = useState(null)
  const [error, setError] = useState(null)

  // Load dashboard summary
  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true)
        const res = await fetch(`${API_BASE}/api/v1/alerts/dashboard/summary?org_id=${ORG_ID}`)
        const data = await res.json()
        setDashboard(data)
        setError(null)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    const fetchAlerts = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/alerts/dashboard/alerts?org_id=${ORG_ID}&limit=10`)
        const data = await res.json()
        setAlerts(data || [])
      } catch (err) {
        console.error('Failed to fetch alerts:', err)
      }
    }

    fetchDashboard()
    fetchAlerts()
    const interval = setInterval(() => {
      fetchDashboard()
      fetchAlerts()
    }, 30000)

    return () => clearInterval(interval)
  }, [])

  // Load peer context when alert is selected
  useEffect(() => {
    if (!selectedAlert) {
      setPeerContext(null)
      return
    }

    const fetchPeerContext = async () => {
      try {
        const res = await fetch(
          `${API_BASE}/api/v1/alerts/dashboard/alerts/${selectedAlert.alert_id}/peer-context?org_id=${ORG_ID}`
        )
        const data = await res.json()
        setPeerContext(data)
      } catch (err) {
        console.error('Failed to fetch peer context:', err)
      }
    }

    fetchPeerContext()
  }, [selectedAlert])

  const urgencyColor = (level) => {
    switch (level) {
      case 'critical':
        return 'from-red-400 to-red-600'
      case 'high':
        return 'from-orange-400 to-orange-600'
      case 'medium':
        return 'from-yellow-400 to-yellow-600'
      default:
        return 'from-green-400 to-green-600'
    }
  }

  const urgencyBg = (level) => {
    switch (level) {
      case 'critical':
        return 'bg-red-50 text-red-700'
      case 'high':
        return 'bg-orange-50 text-orange-700'
      case 'medium':
        return 'bg-yellow-50 text-yellow-700'
      default:
        return 'bg-green-50 text-green-700'
    }
  }

  // Background animation by max urgency
  const maxUrgency = useMemo(() => {
    if (!dashboard || !dashboard.critical_alerts) return 'low'
    if (dashboard.critical_alerts > 0) return 'critical'
    if (dashboard.high_priority_alerts > 0) return 'high'
    return 'low'
  }, [dashboard])

  const bgStyle = {
    critical: 'radial-gradient(circle at 30% 50%, rgba(239, 68, 68, 0.15), transparent 50%)',
    high: 'radial-gradient(circle at 30% 50%, rgba(249, 115, 22, 0.12), transparent 50%)',
    medium: 'radial-gradient(circle at 30% 50%, rgba(251, 191, 36, 0.1), transparent 50%)',
    low: 'radial-gradient(circle at 30% 50%, rgba(34, 197, 94, 0.08), transparent 50%)',
  }

  return (
    <div className="w-full h-full overflow-y-auto bg-white">
      {/* Animated Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-100"
          style={{
            background: bgStyle[maxUrgency],
            animation: 'float 8s ease-in-out infinite'
          }}
        />
      </div>

      {/* Main Content - Scrollable */}
      <div className="relative z-10 w-full">
        {/* Hero Section */}
        <section className="min-h-screen flex items-center justify-center overflow-hidden pt-12 pb-20">
          <div className="text-center px-6 max-w-4xl mx-auto w-full">
            <div className="text-7xl mb-4">⚠️</div>
            <h1 className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight">
              Regulatory
              <span className="block text-transparent bg-clip-text bg-gradient-to-r from-red-500 to-orange-500">
                Intelligence
              </span>
            </h1>

            <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
              Real-time regulatory change detection, impact analysis, and compliance tracking
            </p>

            {/* Live metrics */}
            {dashboard && !loading && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-8 pt-8 border-t border-gray-200">
                <div className="text-center">
                  <div className="text-3xl md:text-4xl font-light text-gray-900">
                    {dashboard.total_alerts || 0}
                  </div>
                  <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Total Alerts</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl md:text-4xl font-light text-red-600">
                    {dashboard.critical_alerts || 0}
                  </div>
                  <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Critical</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl md:text-4xl font-light text-orange-600">
                    {dashboard.high_priority_alerts || 0}
                  </div>
                  <div className="text-xs md:text-sm text-gray-600 font-light mt-2">High</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl md:text-3xl font-light text-blue-600">
                    {dashboard.next_deadline ? dashboard.next_deadline.substring(0, 10) : '—'}
                  </div>
                  <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Next Deadline</div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Alerts Section */}
        <section className="px-6 md:px-12 py-20 max-w-7xl mx-auto w-full">
          <h2 className="text-5xl md:text-6xl font-light text-gray-900 mb-4">Active Alerts</h2>
          <p className="text-lg text-gray-600 font-light mb-12 max-w-2xl">
            Real-time regulatory changes affecting your organization
          </p>

          {error && (
            <div className="mb-8 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 flex items-center gap-2">
              <div><SimpleIcon type="alert" /></div>
              {error}
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center py-20">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-gray-300 border-t-gray-900 rounded-full animate-spin mx-auto mb-4"></div>
                <p className="text-gray-600">Loading regulatory alerts...</p>
              </div>
            </div>
          )}

          {!loading && alerts.length === 0 && (
            <div className="text-center py-20">
              <div><SimpleIcon type="alert" /></div>
              <p className="text-gray-500 text-lg">No alerts detected</p>
              <p className="text-gray-400">Regulatory changes will appear here</p>
            </div>
          )}

          {/* Alerts Grid */}
          {!loading && alerts.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-20">
              {alerts.map((alert) => (
                <div
                  key={alert.alert_id}
                  onClick={() => setSelectedAlert(alert)}
                  className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-gray-300 hover:shadow-lg transition-all cursor-pointer"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <h3 className="text-xl font-semibold text-gray-900 mb-1">
                        {alert.framework_name}
                      </h3>
                      <p className={`text-xs font-semibold px-2 py-1 rounded inline-block ${urgencyBg(alert.urgency_level)}`}>
                        {alert.urgency_level.toUpperCase()}
                      </p>
                    </div>
                    <ChevronRight size={20} className="text-gray-400" />
                  </div>

                  <div className="space-y-2 mb-4">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Affected Assets</span>
                      <span className="font-semibold text-gray-900">{alert.affected_assets}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Portfolio Risk</span>
                      <span className="font-semibold text-gray-900">
                        €{(alert.portfolio_value_affected_eur / 1000000).toFixed(1)}M
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Dev Effort</span>
                      <span className="font-semibold text-gray-900">{alert.dev_hours}h</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Deadline</span>
                      <span className="font-semibold text-gray-900">{alert.deadline.substring(0, 10)}</span>
                    </div>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setSelectedAlert(alert)
                    }}
                    className="w-full px-4 py-2 bg-gray-900 hover:bg-gray-800 text-white rounded-lg font-medium text-sm transition-colors"
                  >
                    View Details →
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Detail Section */}
        {selectedAlert && (
          <section className="px-6 md:px-12 py-20 max-w-7xl mx-auto w-full bg-gray-50 rounded-3xl">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-5xl md:text-6xl font-light text-gray-900">
                {selectedAlert.framework_name}
              </h2>
              <button
                onClick={() => setSelectedAlert(null)}
                className="text-gray-400 hover:text-gray-600 text-2xl"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
              {/* Left Column */}
              <div className="space-y-6">
                <div>
                  <p className="text-sm text-gray-600 font-medium mb-2">AFFECTED ASSETS</p>
                  <p className="text-4xl font-light text-gray-900">
                    {selectedAlert.affected_assets}
                    <span className="text-lg text-gray-500 ml-2">of {selectedAlert.total_assets}</span>
                  </p>
                  <p className="text-sm text-gray-600 mt-2">
                    {Math.round((selectedAlert.affected_assets / selectedAlert.total_assets) * 100)}% of your portfolio
                  </p>
                </div>

                <div>
                  <p className="text-sm text-gray-600 font-medium mb-2">PORTFOLIO AT RISK</p>
                  <p className="text-4xl font-light text-gray-900">
                    €{(selectedAlert.portfolio_value_affected_eur / 1000000).toFixed(1)}M
                  </p>
                </div>

                <div>
                  <p className="text-sm text-gray-600 font-medium mb-2">DEVELOPMENT EFFORT</p>
                  <p className="text-4xl font-light text-gray-900">
                    {selectedAlert.estimated_dev_hours}h
                  </p>
                  <p className="text-sm text-gray-600 mt-2">+{selectedAlert.estimated_test_hours}h testing</p>
                </div>

                <div>
                  <p className="text-sm text-gray-600 font-medium mb-2">DEADLINE</p>
                  <p className="text-4xl font-light text-gray-900">
                    {selectedAlert.deadline.substring(0, 10)}
                  </p>
                </div>
              </div>

              {/* Right Column - Peer Context */}
              {peerContext && (
                <div className="space-y-6 bg-white rounded-2xl p-8 border border-gray-200">
                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-2">PEERS AFFECTED</p>
                    <p className="text-4xl font-light text-gray-900">{peerContext.peer_count || 0}</p>
                    <p className="text-sm text-gray-600 mt-2">Similar organizations</p>
                  </div>

                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-2">ADOPTION RATE</p>
                    <p className="text-4xl font-light text-gray-900">{peerContext.peer_adoption_rate_pct || 0}%</p>
                  </div>

                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-2">AVG IMPLEMENTATION</p>
                    <p className="text-4xl font-light text-gray-900">{peerContext.avg_implementation_weeks || 0}w</p>
                  </div>

                  <div className="pt-6 border-t border-gray-200">
                    <p className="text-sm text-gray-600 font-medium mb-2">YOUR SPEED</p>
                    <p className="text-3xl font-light text-blue-600">{peerContext.your_speed_percentile || 0}%</p>
                    <p className="text-sm text-gray-600 mt-2">{peerContext.speed_assessment || 'unknown'}</p>
                  </div>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <button
                onClick={() => {
                  fetch(
                    `${API_BASE}/api/v1/alerts/dashboard/alerts/${selectedAlert.alert_id}/acknowledge?org_id=${ORG_ID}`,
                    { method: 'POST' }
                  )
                  setSelectedAlert(null)
                }}
                className="px-6 py-3 bg-gray-900 hover:bg-gray-800 text-white rounded-lg font-medium transition-colors"
              >
                Acknowledge Alert
              </button>
              <button
                onClick={() => {
                  window.open(
                    `${API_BASE}/api/v1/alerts/dashboard/alerts/${selectedAlert.alert_id}/create-task?org_id=${ORG_ID}&system=jira`,
                    '_blank'
                  )
                }}
                className="px-6 py-3 bg-gray-100 hover:bg-gray-200 text-gray-900 rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
              >
                <ExternalLink size={16} />
                Create JIRA Ticket (Week 3)
              </button>
            </div>
          </section>
        )}

        {/* Footer spacing */}
        <div className="h-20" />
      </div>

      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(20px); }
        }
      `}</style>
    </div>
  )
}
