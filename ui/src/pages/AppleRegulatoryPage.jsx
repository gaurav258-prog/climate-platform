import { useState, useEffect, useMemo } from 'react'
import { AlertCircle, CheckCircle, Clock, TrendingUp, ChevronRight, RefreshCw } from 'lucide-react'

/**
 * Apple Store-inspired Regulatory Alerts Dashboard
 * Real-time regulatory change detection and compliance tracking
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
    }, 30000) // Refresh every 30 seconds

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

  return (
    <div className="flex-1 overflow-auto bg-slate-950 p-8">
      {/* Header */}
      <div className="mb-12">
        <h1 className="text-4xl font-bold text-white mb-2">Regulatory Intelligence</h1>
        <p className="text-slate-400">Real-time regulatory change detection and compliance tracking</p>
      </div>

      {/* Error State */}
      {error && (
        <div className="mb-8 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400">
          <AlertCircle className="inline mr-2" size={16} />
          {error}
        </div>
      )}

      {/* Metrics Grid */}
      {dashboard && !loading && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-12">
          {/* Total Alerts */}
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-6 border border-slate-700/50 hover:border-slate-600 transition-colors">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-slate-400 text-sm font-medium mb-1">Total Alerts</p>
                <p className="text-3xl font-bold text-white">{dashboard.total_alerts || 0}</p>
                <p className="text-slate-500 text-xs mt-2">Regulatory changes</p>
              </div>
              <AlertCircle className="text-slate-600" size={24} />
            </div>
          </div>

          {/* Critical Alerts */}
          <div className="bg-gradient-to-br from-red-900/20 to-red-950/20 rounded-2xl p-6 border border-red-500/20 hover:border-red-500/30 transition-colors">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-red-400 text-sm font-medium mb-1">Critical</p>
                <p className="text-3xl font-bold text-red-300">{dashboard.critical_alerts || 0}</p>
                <p className="text-red-500/70 text-xs mt-2">Require immediate action</p>
              </div>
              <AlertCircle className="text-red-500" size={24} />
            </div>
          </div>

          {/* High Priority */}
          <div className="bg-gradient-to-br from-orange-900/20 to-orange-950/20 rounded-2xl p-6 border border-orange-500/20 hover:border-orange-500/30 transition-colors">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-orange-400 text-sm font-medium mb-1">High Priority</p>
                <p className="text-3xl font-bold text-orange-300">{dashboard.high_priority_alerts || 0}</p>
                <p className="text-orange-500/70 text-xs mt-2">This week</p>
              </div>
              <Clock className="text-orange-500" size={24} />
            </div>
          </div>

          {/* Next Deadline */}
          <div className="bg-gradient-to-br from-blue-900/20 to-blue-950/20 rounded-2xl p-6 border border-blue-500/20 hover:border-blue-500/30 transition-colors">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-blue-400 text-sm font-medium mb-1">Next Deadline</p>
                <p className="text-2xl font-bold text-blue-300">
                  {dashboard.next_deadline ? dashboard.next_deadline.substring(0, 10) : 'No deadline'}
                </p>
                <p className="text-blue-500/70 text-xs mt-2">Earliest deadline</p>
              </div>
              <TrendingUp className="text-blue-500" size={24} />
            </div>
          </div>
        </div>
      )}

      {/* Alerts Table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Recent Alerts */}
        <div className="lg:col-span-2">
          <div className="bg-slate-900/50 backdrop-blur rounded-2xl border border-slate-700/50 overflow-hidden">
            <div className="p-6 border-b border-slate-700/50 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-white">Recent Alerts</h2>
              <RefreshCw size={18} className="text-slate-400 cursor-pointer hover:text-slate-300" />
            </div>

            {/* Empty State */}
            {alerts.length === 0 && (
              <div className="p-8 text-center">
                <AlertCircle size={32} className="mx-auto text-slate-600 mb-3" />
                <p className="text-slate-400">No alerts detected</p>
                <p className="text-slate-500 text-sm mt-1">Regulatory changes will appear here</p>
              </div>
            )}

            {/* Alert List */}
            {alerts.map((alert) => (
              <div
                key={alert.alert_id}
                onClick={() => setSelectedAlert(alert)}
                className={`p-4 border-b border-slate-700/50 cursor-pointer hover:bg-slate-800/50 transition-colors ${
                  selectedAlert?.alert_id === alert.alert_id ? 'bg-slate-800/50' : ''
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <h3 className="font-semibold text-white flex items-center gap-2">
                      {alert.framework_name}
                      <span className={`px-2 py-1 rounded text-xs font-medium ${urgencyBg(alert.urgency_level)}`}>
                        {alert.urgency_level.toUpperCase()}
                      </span>
                    </h3>
                    <p className="text-slate-400 text-sm mt-1">
                      {alert.affected_assets} assets affected • €{(alert.portfolio_value_affected_eur / 1000000).toFixed(1)}M risk
                    </p>
                  </div>
                  <ChevronRight
                    size={20}
                    className={`text-slate-500 flex-shrink-0 transition-transform ${
                      selectedAlert?.alert_id === alert.alert_id ? 'rotate-90' : ''
                    }`}
                  />
                </div>
                <div className="flex gap-4 text-xs text-slate-500 mt-2">
                  <span>⏱️ {alert.dev_hours}h effort</span>
                  <span>📅 {alert.deadline.substring(0, 10)}</span>
                  <span className="text-slate-600 capitalize">→ {alert.alert_status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Detail Panel */}
        {selectedAlert && (
          <div className="bg-gradient-to-br from-slate-800/50 to-slate-900/50 backdrop-blur rounded-2xl border border-slate-700/50 p-6">
            <h2 className="text-lg font-semibold text-white mb-4">{selectedAlert.framework_name}</h2>

            <div className="space-y-4 mb-6">
              <div className="bg-slate-900/50 rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-1">Affected Assets</p>
                <p className="text-2xl font-bold text-white">{selectedAlert.affected_assets}/{selectedAlert.total_assets}</p>
                <p className="text-xs text-slate-500 mt-1">
                  {Math.round((selectedAlert.affected_assets / selectedAlert.total_assets) * 100)}% of portfolio
                </p>
              </div>

              <div className="bg-slate-900/50 rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-1">Portfolio Value at Risk</p>
                <p className="text-2xl font-bold text-white">€{(selectedAlert.portfolio_value_affected_eur / 1000000).toFixed(1)}M</p>
              </div>

              <div className="bg-slate-900/50 rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-1">Development Effort</p>
                <p className="text-2xl font-bold text-white">{selectedAlert.estimated_dev_hours}h</p>
                <p className="text-xs text-slate-500 mt-1">+{selectedAlert.estimated_test_hours}h testing</p>
              </div>

              <div className="bg-slate-900/50 rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-1">Deadline</p>
                <p className="text-2xl font-bold text-white">{selectedAlert.deadline.substring(0, 10)}</p>
              </div>
            </div>

            {/* Peer Context */}
            {peerContext && (
              <div className="pt-6 border-t border-slate-700/50">
                <h3 className="text-sm font-semibold text-white mb-3">Peer Context</h3>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Banks affected</span>
                    <span className="text-white font-medium">{peerContext.peer_count || 0}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Adoption rate</span>
                    <span className="text-white font-medium">{peerContext.peer_adoption_rate_pct || 0}%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Avg implementation</span>
                    <span className="text-white font-medium">{peerContext.avg_implementation_weeks || 0}w</span>
                  </div>
                  <div className="flex justify-between text-sm pt-2 border-t border-slate-700/50">
                    <span className="text-slate-400">Your speed percentile</span>
                    <span className="text-blue-400 font-medium">{peerContext.your_speed_percentile || 0}%</span>
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="mt-6 pt-6 border-t border-slate-700/50 space-y-2">
              <button className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium text-sm transition-colors">
                View Details →
              </button>
              <button className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium text-sm transition-colors">
                Create Task (Week 3)
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-slate-600 border-t-slate-300 rounded-full animate-spin mx-auto mb-4"></div>
            <p className="text-slate-400">Loading regulatory alerts...</p>
          </div>
        </div>
      )}
    </div>
  )
}
