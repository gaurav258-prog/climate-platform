import { useState, useEffect } from 'react'
import { ChevronRight, Play, Pause } from 'lucide-react'

/**
 * Apple Store-inspired Climate Intelligence Dashboard
 * Clean, minimalist design with hero section + hazard cards
 */
export default function AppleDashboard({ onHazardChange, onViewChange }) {
  const [scrollPosition, setScrollPosition] = useState(0)
  const [hoveredCard, setHoveredCard] = useState(null)
  const [stats, setStats] = useState({
    totalEvents: 0,
    activeAlerts: 0,
    coverage: '100%'
  })

  useEffect(() => {
    const handleScroll = () => setScrollPosition(window.scrollY)
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    // Fetch real-time stats
    fetch('http://localhost:8000/seismic/events?days=30&min_magnitude=4.5')
      .then(res => res.json())
      .then(data => {
        setStats(prev => ({
          ...prev,
          totalEvents: data.events?.length || 0
        }))
      })
      .catch(() => {})
  }, [])

  const hazards = [
    {
      id: 'flood',
      name: 'Flood Intelligence',
      description: 'Real-time flood risk assessment and early warning systems',
      icon: '🌊',
      color: 'from-blue-400 to-cyan-600',
      gradient: 'from-blue-50 to-cyan-50',
      accent: 'text-blue-600',
      bgGradient: 'radial-gradient(135deg, #0EA5E9 0%, #06B6D4 100%)',
      stats: { events: '247', regions: '1,200+', accuracy: '92%' }
    },
    {
      id: 'wildfire',
      name: 'Wildfire Intelligence',
      description: 'Predictive wildfire risk mapping with satellite data',
      icon: '🔥',
      color: 'from-orange-400 to-red-600',
      gradient: 'from-orange-50 to-red-50',
      accent: 'text-orange-600',
      bgGradient: 'radial-gradient(135deg, #FB923C 0%, #DC2626 100%)',
      stats: { events: '156', regions: '850+', accuracy: '88%' }
    },
    {
      id: 'heat',
      name: 'Heat Stress Intelligence',
      description: 'Monitor extreme heat events and health risks',
      icon: '☀️',
      color: 'from-yellow-400 to-orange-600',
      gradient: 'from-yellow-50 to-orange-50',
      accent: 'text-yellow-600',
      bgGradient: 'radial-gradient(135deg, #FBBF24 0%, #F97316 100%)',
      stats: { events: '89', regions: '500+', accuracy: '85%' }
    },
    {
      id: 'seismic',
      name: 'Seismic Intelligence',
      description: 'Earthquake risk forecasting and damage assessment',
      icon: '🌍',
      color: 'from-red-400 to-rose-600',
      gradient: 'from-red-50 to-rose-50',
      accent: 'text-red-600',
      bgGradient: 'radial-gradient(135deg, #F87171 0%, #E11D48 100%)',
      stats: { events: '61', regions: '17', accuracy: '80%' }
    }
  ]

  const navigateToHazard = (hazardId) => {
    onHazardChange(hazardId)
    onViewChange('map')
  }

  return (
    <div className="w-full bg-white">
      {/* Hero Section */}
      <section className="relative h-screen flex items-center justify-center overflow-hidden">
        {/* Animated background gradient */}
        <div className="absolute inset-0">
          <div
            className="absolute inset-0 opacity-30"
            style={{
              background: 'radial-gradient(circle at 20% 50%, rgba(59, 130, 246, 0.3), transparent 50%)',
              animation: 'float 6s ease-in-out infinite'
            }}
          />
          <div
            className="absolute inset-0 opacity-20"
            style={{
              background: 'radial-gradient(circle at 80% 80%, rgba(34, 197, 94, 0.3), transparent 50%)',
              animation: 'float 8s ease-in-out infinite 1s'
            }}
          />
          <video
            autoPlay
            muted
            loop
            className="absolute inset-0 w-full h-full object-cover opacity-20"
            style={{
              background: 'linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%)'
            }}
          >
            <source src="https://www.apple.com/media/home/hero/large.mp4" type="video/mp4" />
          </video>
        </div>

        {/* Content */}
        <div className="relative z-10 text-center px-6 max-w-4xl mx-auto">
          <h1
            className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight"
            style={{ opacity: 1 - scrollPosition / 500 }}
          >
            Climate
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-600 via-green-600 to-blue-600">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Real-time hazard monitoring, AI-powered risk forecasting, and parametric insurance solutions for climate resilience
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button className="px-8 py-3 bg-gray-900 text-white rounded-full font-light hover:bg-gray-800 transition-all transform hover:scale-105">
              Explore Solutions
            </button>
            <button className="px-8 py-3 bg-gray-100 text-gray-900 rounded-full font-light hover:bg-gray-200 transition-all transform hover:scale-105">
              Learn More →
            </button>
          </div>

          {/* Live stats */}
          <div className="mt-16 grid grid-cols-3 gap-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-3xl font-light text-blue-600">{stats.totalEvents}</div>
              <div className="text-sm text-gray-600 font-light mt-1">Active Events</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-light text-green-600">1,200+</div>
              <div className="text-sm text-gray-600 font-light mt-1">Regions Monitored</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-light text-purple-600">{stats.coverage}</div>
              <div className="text-sm text-gray-600 font-light mt-1">Global Coverage</div>
            </div>
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 z-10">
          <div className="flex flex-col items-center gap-2">
            <p className="text-sm text-gray-600 font-light">Scroll to explore</p>
            <div className="w-6 h-10 border border-gray-400 rounded-full flex items-start justify-center p-2">
              <div
                className="w-1 h-2 bg-gray-600 rounded-full"
                style={{
                  animation: 'scroll 2s ease-in-out infinite'
                }}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Hazard Cards Section */}
      <section className="py-24 px-6 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          {/* Section header */}
          <div className="mb-20 text-center">
            <h2 className="text-5xl md:text-6xl font-light text-gray-900 mb-6">
              Hazard Intelligence
            </h2>
            <p className="text-xl text-gray-600 font-light max-w-3xl mx-auto">
              Comprehensive monitoring and forecasting for the four major climate hazards
            </p>
          </div>

          {/* Hazard cards grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {hazards.map((hazard, index) => (
              <div
                key={hazard.id}
                className="group cursor-pointer"
                onMouseEnter={() => setHoveredCard(hazard.id)}
                onMouseLeave={() => setHoveredCard(null)}
                onClick={() => navigateToHazard(hazard.id)}
              >
                {/* Card container */}
                <div
                  className="relative h-96 rounded-3xl overflow-hidden shadow-lg transition-all duration-500 transform hover:scale-102 hover:shadow-2xl"
                  style={{
                    background: hazard.bgGradient
                  }}
                >
                  {/* Background animation */}
                  <div
                    className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                    style={{
                      background: `linear-gradient(135deg, ${hazard.color})`,
                      animation: hoveredCard === hazard.id ? 'pulse 2s ease-in-out infinite' : 'none'
                    }}
                  />

                  {/* Content */}
                  <div className="relative z-10 h-full flex flex-col justify-between p-8">
                    {/* Top */}
                    <div>
                      <div className="text-6xl mb-4">{hazard.icon}</div>
                      <h3 className="text-3xl font-light text-gray-900 mb-2">
                        {hazard.name}
                      </h3>
                      <p className="text-gray-700 font-light text-lg leading-relaxed">
                        {hazard.description}
                      </p>
                    </div>

                    {/* Bottom - Stats */}
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <div className="text-2xl font-light text-gray-900">
                          {hazard.stats.events}
                        </div>
                        <div className="text-xs text-gray-600 font-light">Events</div>
                      </div>
                      <div>
                        <div className="text-2xl font-light text-gray-900">
                          {hazard.stats.regions}
                        </div>
                        <div className="text-xs text-gray-600 font-light">Regions</div>
                      </div>
                      <div>
                        <div className="text-2xl font-light text-gray-900">
                          {hazard.stats.accuracy}
                        </div>
                        <div className="text-xs text-gray-600 font-light">Accuracy</div>
                      </div>
                    </div>

                    {/* Arrow indicator */}
                    <div className="absolute bottom-6 right-6 opacity-0 group-hover:opacity-100 transition-opacity">
                      <ChevronRight size={24} className="text-gray-900" />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-5xl font-light text-gray-900 mb-16 text-center">
            Powered by Innovation
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
            {[
              {
                icon: '🤖',
                title: 'AI-Powered Forecasting',
                description: 'Machine learning models trained on 20+ years of climate data'
              },
              {
                icon: '🛰️',
                title: 'Satellite Integration',
                description: 'Real-time SAR, optical, and thermal satellite imagery'
              },
              {
                icon: '📡',
                title: 'Live Data Streams',
                description: 'Continuous data ingestion from 100+ global sensors'
              }
            ].map((feature, i) => (
              <div key={i} className="text-center">
                <div className="text-5xl mb-4">{feature.icon}</div>
                <h3 className="text-2xl font-light text-gray-900 mb-3">
                  {feature.title}
                </h3>
                <p className="text-gray-600 font-light text-lg">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 px-6 bg-gradient-to-br from-gray-900 to-gray-800">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-5xl font-light text-white mb-6">
            Ready to Get Started?
          </h2>
          <p className="text-xl text-gray-300 font-light mb-8">
            Join leading organizations using Climate Intelligence for risk management and parametric insurance
          </p>
          <button className="px-8 py-4 bg-white text-gray-900 rounded-full font-light hover:bg-gray-100 transition-all transform hover:scale-105 text-lg">
            Schedule Demo
          </button>
        </div>
      </section>

      {/* Styles */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(20px); }
        }

        @keyframes scroll {
          0% { opacity: 1; transform: translateY(0); }
          50% { opacity: 1; }
          100% { opacity: 0; transform: translateY(12px); }
        }

        @keyframes pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.6; }
        }

        .hover\:scale-102:hover {
          transform: scale(1.02);
        }
      `}</style>
    </div>
  )
}
