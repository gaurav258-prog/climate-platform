import { useState, useEffect } from 'react'
import { AlertCircle, CheckCircle, Clock, Users, MapPin, Activity } from 'lucide-react'

/**
 * Apple-style Operations & Response Management Page
 */
export default function AppleOperationsPage() {
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [stats, setStats] = useState({
    activeAlerts: 0,
    responders: 0,
    resolved: 0
  })

  useEffect(() => {
    const interval = setInterval(() => {
      setStats({
        activeAlerts: Math.floor(Math.random() * 15) + 3,
        responders: Math.floor(Math.random() * 500) + 100,
        resolved: Math.floor(Math.random() * 200) + 50
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const activeAlerts = [
    {
      id: 1,
      type: 'Flood',
      location: 'Rhine Basin, Germany',
      severity: 'critical',
      status: 'active',
      responders: 45,
      affectedPopulation: 250000,
      timeElapsed: '2h 15min',
      coordinates: { lat: 51.2, lon: 6.8 }
    },
    {
      id: 2,
      type: 'Wildfire',
      location: 'Andalusia, Spain',
      severity: 'high',
      status: 'active',
      responders: 128,
      affectedPopulation: 80000,
      timeElapsed: '4h 32min',
      coordinates: { lat: 37.5, lon: -3.5 }
    },
    {
      id: 3,
      type: 'Heat Wave',
      location: 'Southern Italy',
      severity: 'high',
      status: 'monitoring',
      responders: 67,
      affectedPopulation: 1200000,
      timeElapsed: '6h 10min',
      coordinates: { lat: 40.8, lon: 14.2 }
    },
    {
      id: 4,
      type: 'Seismic',
      location: 'Greece',
      severity: 'critical',
      status: 'response',
      responders: 234,
      affectedPopulation: 450000,
      timeElapsed: '1h 45min',
      coordinates: { lat: 39.0, lon: 22.0 }
    },
  ]

  const getSeverityColor = (severity) => {
    switch(severity) {
      case 'critical': return { bg: 'bg-red-100', text: 'text-red-700', badge: 'bg-red-100 text-red-700' }
      case 'high': return { bg: 'bg-orange-100', text: 'text-orange-700', badge: 'bg-orange-100 text-orange-700' }
      case 'moderate': return { bg: 'bg-yellow-100', text: 'text-yellow-700', badge: 'bg-yellow-100 text-yellow-700' }
      default: return { bg: 'bg-green-100', text: 'text-green-700', badge: 'bg-green-100 text-green-700' }
    }
  }

  const getStatusIcon = (status) => {
    switch(status) {
      case 'active': return <Activity size={20} className="text-red-600 animate-pulse" />
      case 'response': return <CheckCircle size={20} className="text-blue-600" />
      case 'monitoring': return <Clock size={20} className="text-yellow-600" />
      default: return <AlertCircle size={20} className="text-gray-600" />
    }
  }

  return (
    <div className="w-full bg-white">
      {/* Hero Section */}
      <section className="relative h-96 flex items-center justify-center overflow-hidden pt-12">
        {/* Background gradient */}
        <div className="absolute inset-0">
          <div
            className="absolute inset-0 opacity-20"
            style={{
              background: 'radial-gradient(circle at 50% 50%, rgba(59, 130, 246, 0.3), transparent 60%)',
              animation: 'float 8s ease-in-out infinite'
            }}
          />
        </div>

        {/* Content */}
        <div className="relative z-10 text-center px-6 max-w-4xl mx-auto">
          <h1 className="text-6xl md:text-7xl font-light text-gray-900 mb-4 leading-tight">
            Operations
          </h1>
          <p className="text-xl text-gray-600 font-light">
            Coordinate emergency response and hazard mitigation across all active events
          </p>

          {/* Live metrics */}
          <div className="grid grid-cols-3 gap-8 mt-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-3xl font-light text-red-600">{stats.activeAlerts}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Active Alerts</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-light text-blue-600">{stats.responders}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Responders Deployed</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-light text-green-600">{stats.resolved}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Resolved Today</div>
            </div>
          </div>
        </div>
      </section>

      {/* Active Alerts Section */}
      <section className="py-24 px-6 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-5xl font-light text-gray-900 mb-4">Active Response Operations</h2>
          <p className="text-xl text-gray-600 font-light mb-16">
            Real-time monitoring of all emergency response activities
          </p>

          {/* Alerts grid */}
          <div className="space-y-4">
            {activeAlerts.map((alert) => {
              const colors = getSeverityColor(alert.severity)
              return (
                <div
                  key={alert.id}
                  onClick={() => setSelectedAlert(alert)}
                  className="group cursor-pointer"
                >
                  <div className="bg-white p-6 rounded-2xl shadow-sm hover:shadow-lg transition-all duration-300 border border-gray-200 hover:border-gray-300">
                    <div className="flex items-start justify-between">
                      {/* Left: Alert info */}
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-3">
                          {getStatusIcon(alert.status)}
                          <h3 className="text-2xl font-light text-gray-900">
                            {alert.type} — {alert.location}
                          </h3>
                        </div>

                        <div className="grid grid-cols-4 gap-6 text-sm font-light text-gray-600">
                          <div>
                            <span className="text-xs text-gray-500 uppercase tracking-wider">Responders</span>
                            <div className="text-lg text-gray-900 font-light mt-1">{alert.responders}</div>
                          </div>
                          <div>
                            <span className="text-xs text-gray-500 uppercase tracking-wider">Population</span>
                            <div className="text-lg text-gray-900 font-light mt-1">
                              {(alert.affectedPopulation / 1000).toFixed(0)}K
                            </div>
                          </div>
                          <div>
                            <span className="text-xs text-gray-500 uppercase tracking-wider">Duration</span>
                            <div className="text-lg text-gray-900 font-light mt-1">{alert.timeElapsed}</div>
                          </div>
                          <div>
                            <span className="text-xs text-gray-500 uppercase tracking-wider">Status</span>
                            <div className={`text-lg font-light mt-1 ${colors.text}`}>
                              {alert.status.charAt(0).toUpperCase() + alert.status.slice(1)}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Right: Severity badge */}
                      <div className={`px-4 py-2 rounded-full text-sm font-light ${colors.badge} ml-6 whitespace-nowrap`}>
                        {alert.severity.charAt(0).toUpperCase() + alert.severity.slice(1)} Severity
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* Response Tools Section */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-5xl font-light text-gray-900 mb-16 text-center">
            Response Management Tools
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                icon: '📍',
                title: 'Incident Mapping',
                description: 'Real-time geospatial visualization of all active incidents and responder locations'
              },
              {
                icon: '👥',
                title: 'Team Coordination',
                description: 'Manage response teams, assign resources, and track deployment status'
              },
              {
                icon: '📊',
                title: 'Impact Assessment',
                description: 'Estimate affected population, economic loss, and critical infrastructure at risk'
              }
            ].map((tool, i) => (
              <div key={i} className="p-8 rounded-2xl bg-gray-50 border border-gray-200 hover:border-gray-300 transition-all">
                <div className="text-5xl mb-4">{tool.icon}</div>
                <h3 className="text-2xl font-light text-gray-900 mb-3">{tool.title}</h3>
                <p className="text-gray-600 font-light">{tool.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Selected Alert Detail */}
      {selectedAlert && (
        <section className="py-24 px-6 bg-gradient-to-br from-gray-50 to-blue-50">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-4xl font-light text-gray-900">
                {selectedAlert.type} Incident — {selectedAlert.location}
              </h2>
              <button
                onClick={() => setSelectedAlert(null)}
                className="text-gray-500 hover:text-gray-900 text-2xl"
              >
                ✕
              </button>
            </div>

            <div className="bg-white rounded-3xl p-12 shadow-lg">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
                {[
                  { label: 'Severity', value: selectedAlert.severity.toUpperCase() },
                  { label: 'Status', value: selectedAlert.status.toUpperCase() },
                  { label: 'Responders', value: selectedAlert.responders },
                  { label: 'Population at Risk', value: `${(selectedAlert.affectedPopulation / 1000000).toFixed(1)}M` }
                ].map((stat, i) => (
                  <div key={i} className="text-center">
                    <div className="text-sm text-gray-600 font-light uppercase tracking-wider mb-2">
                      {stat.label}
                    </div>
                    <div className="text-3xl font-light text-blue-600">{stat.value}</div>
                  </div>
                ))}
              </div>

              <div className="border-t border-gray-200 pt-8">
                <h3 className="text-2xl font-light text-gray-900 mb-4">Response Actions</h3>
                <div className="space-y-3">
                  <button className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg font-light hover:bg-blue-700 transition-all">
                    Deploy Additional Resources
                  </button>
                  <button className="w-full px-6 py-3 bg-gray-100 text-gray-900 rounded-lg font-light hover:bg-gray-200 transition-all">
                    Generate Report
                  </button>
                  <button className="w-full px-6 py-3 bg-gray-100 text-gray-900 rounded-lg font-light hover:bg-gray-200 transition-all">
                    Alert Media & Public
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Styles */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(20px); }
        }
      `}</style>
    </div>
  )
}
