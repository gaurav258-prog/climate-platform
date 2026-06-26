import { useState } from 'react'
import { Zap, TrendingUp, Shield, DollarSign, BarChart3, AlertCircle } from 'lucide-react'

/**
 * Apple-style Parametric Insurance Contract Designer
 */
export default function AppleParametricPage() {
  const [selectedContract, setSelectedContract] = useState(null)
  const [newContract, setNewContract] = useState({
    name: '',
    hazard: 'flood',
    coverage: 'high',
    premium: 50000,
    payout: 5000000
  })

  const contracts = [
    {
      id: 1,
      name: 'Rhine Basin Flood Cover',
      hazard: 'Flood',
      coverage: 'High Risk Regions',
      premium: '$750,000',
      payout: '$50M',
      triggers: 5,
      status: 'Active',
      roi: '18.5%'
    },
    {
      id: 2,
      name: 'Mediterranean Wildfire Insurance',
      hazard: 'Wildfire',
      coverage: 'Spain & Portugal',
      premium: '$1.2M',
      payout: '$75M',
      triggers: 3,
      status: 'Active',
      roi: '22.3%'
    },
    {
      id: 3,
      name: 'Southern Europe Heat Wave Protection',
      hazard: 'Heat',
      coverage: 'Population Centers',
      premium: '$500,000',
      payout: '$30M',
      triggers: 2,
      status: 'Active',
      roi: '15.8%'
    },
    {
      id: 4,
      name: 'Seismic Risk Portfolio',
      hazard: 'Seismic',
      coverage: 'Greece & Turkey',
      premium: '$2M',
      payout: '$100M',
      triggers: 4,
      status: 'Underwriting',
      roi: '24.1%'
    },
  ]

  return (
    <div className="w-full bg-white">
      {/* Hero Section */}
      <section className="relative h-96 flex items-center justify-center overflow-hidden pt-12">
        <div className="absolute inset-0 opacity-20"
          style={{
            background: 'radial-gradient(circle at 50% 50%, rgba(34, 197, 94, 0.3), transparent 60%)',
            animation: 'float 8s ease-in-out infinite'
          }}
        />

        <div className="relative z-10 text-center px-6 max-w-4xl mx-auto">
          <h1 className="text-6xl md:text-7xl font-light text-gray-900 mb-4 leading-tight">
            Parametric Insurance
          </h1>
          <p className="text-xl text-gray-600 font-light">
            Design, manage, and deploy parametric insurance contracts triggered by climate data
          </p>

          <div className="grid grid-cols-3 gap-8 mt-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-3xl font-light text-green-600">{contracts.length}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Active Contracts</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-light text-blue-600">$4.5M</div>
              <div className="text-sm text-gray-600 font-light mt-2">Total Premiums</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-light text-purple-600">$255M</div>
              <div className="text-sm text-gray-600 font-light mt-2">Total Payouts</div>
            </div>
          </div>
        </div>
      </section>

      {/* Contracts Portfolio */}
      <section className="py-24 px-6 bg-green-50">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-16">
            <div>
              <h2 className="text-5xl font-light text-gray-900 mb-4">Insurance Portfolio</h2>
              <p className="text-xl text-gray-600 font-light">
                Index-based contracts with automated triggers
              </p>
            </div>
            <button className="px-6 py-3 bg-green-600 text-white rounded-lg font-light hover:bg-green-700 transition-all">
              + New Contract
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {contracts.map((contract) => (
              <div
                key={contract.id}
                onClick={() => setSelectedContract(contract)}
                className="group cursor-pointer"
              >
                <div className="bg-white p-8 rounded-2xl shadow-sm hover:shadow-lg transition-all border border-green-100 hover:border-green-300">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <h3 className="text-2xl font-light text-gray-900 mb-2">
                        {contract.name}
                      </h3>
                      <p className="text-sm text-gray-600 font-light">{contract.coverage}</p>
                    </div>
                    <span className={`px-3 py-1 rounded-full text-xs font-light ${
                      contract.status === 'Active'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-yellow-100 text-yellow-700'
                    }`}>
                      {contract.status}
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-4 mb-6 pb-6 border-b border-gray-200">
                    <div>
                      <span className="text-xs text-gray-500 uppercase tracking-wider font-light">Premium</span>
                      <div className="text-lg font-light text-gray-900 mt-1">{contract.premium}</div>
                    </div>
                    <div>
                      <span className="text-xs text-gray-500 uppercase tracking-wider font-light">Max Payout</span>
                      <div className="text-lg font-light text-gray-900 mt-1">{contract.payout}</div>
                    </div>
                    <div>
                      <span className="text-xs text-gray-500 uppercase tracking-wider font-light">Triggers</span>
                      <div className="text-lg font-light text-gray-900 mt-1">{contract.triggers}</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <TrendingUp size={16} className="text-green-600" />
                      <span className="text-sm font-light text-green-700">ROI: {contract.roi}</span>
                    </div>
                    <span className="text-sm font-light text-gray-500">Click to edit →</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-5xl font-light text-gray-900 mb-16 text-center">
            How Parametric Works
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {[
              {
                step: '1',
                icon: '📍',
                title: 'Define Trigger',
                desc: 'Set risk parameters (flood depth, fire intensity, temp threshold)'
              },
              {
                step: '2',
                icon: '📊',
                title: 'Monitor Index',
                desc: 'Real-time tracking of hazard intensity from satellite & weather data'
              },
              {
                step: '3',
                icon: '⚡',
                title: 'Auto Payout',
                desc: 'When index crosses threshold, payout is triggered automatically'
              },
              {
                step: '4',
                icon: '💰',
                title: 'Fast Settlement',
                desc: 'Funds transferred within 24h, no claims adjusting needed'
              }
            ].map((item, i) => (
              <div key={i} className="text-center">
                <div className="text-4xl mb-4">{item.icon}</div>
                <div className="text-5xl font-light text-green-600 mb-3">{item.step}</div>
                <h3 className="text-xl font-light text-gray-900 mb-2">{item.title}</h3>
                <p className="text-gray-600 font-light text-sm">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Selected Contract Detail */}
      {selectedContract && (
        <section className="py-24 px-6 bg-gradient-to-br from-green-50 to-emerald-50">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-4xl font-light text-gray-900">
                {selectedContract.name}
              </h2>
              <button
                onClick={() => setSelectedContract(null)}
                className="text-gray-500 hover:text-gray-900 text-2xl"
              >
                ✕
              </button>
            </div>

            <div className="bg-white rounded-3xl p-12 shadow-lg">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
                {[
                  { label: 'Status', value: selectedContract.status },
                  { label: 'Premium', value: selectedContract.premium },
                  { label: 'Max Payout', value: selectedContract.payout },
                  { label: 'Expected ROI', value: selectedContract.roi }
                ].map((stat, i) => (
                  <div key={i} className="text-center">
                    <div className="text-sm text-gray-600 font-light uppercase tracking-wider mb-2">
                      {stat.label}
                    </div>
                    <div className="text-2xl font-light text-green-600">{stat.value}</div>
                  </div>
                ))}
              </div>

              <div className="border-t border-gray-200 pt-8">
                <h3 className="text-2xl font-light text-gray-900 mb-4">Contract Actions</h3>
                <div className="grid grid-cols-2 gap-3">
                  <button className="px-6 py-3 bg-green-600 text-white rounded-lg font-light hover:bg-green-700 transition-all">
                    Edit Triggers
                  </button>
                  <button className="px-6 py-3 bg-blue-600 text-white rounded-lg font-light hover:bg-blue-700 transition-all">
                    View History
                  </button>
                  <button className="px-6 py-3 bg-gray-100 text-gray-900 rounded-lg font-light hover:bg-gray-200 transition-all">
                    Pause Contract
                  </button>
                  <button className="px-6 py-3 bg-gray-100 text-gray-900 rounded-lg font-light hover:bg-gray-200 transition-all">
                    Export Terms
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(20px); }
        }
      `}</style>
    </div>
  )
}
