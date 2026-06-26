import { useState } from 'react'
import { CheckCircle, FileText, Shield, Zap, TrendingUp, Lock } from 'lucide-react'

/**
 * Apple-style Compliance & Packages Page
 */
export default function AppleCompliancePage() {
  const [selectedPackage, setSelectedPackage] = useState(null)

  const packages = [
    {
      id: 1,
      name: 'Starter',
      subtitle: 'For Small Insurers',
      price: '$999',
      period: '/month',
      color: 'blue',
      users: 'Up to 5 users',
      features: [
        'Basic risk mapping for 1 hazard type',
        'Daily data updates',
        'Email alerts',
        'API access (limited)',
        'Email support'
      ],
      cta: 'Get Started'
    },
    {
      id: 2,
      name: 'Professional',
      subtitle: 'For Growing Teams',
      price: '$4,999',
      period: '/month',
      color: 'green',
      users: 'Up to 25 users',
      features: [
        'All 4 hazard types with real-time data',
        'Hourly data updates',
        'SMS + Email alerts',
        'Full API access',
        'Parametric contract designer',
        'Priority phone support'
      ],
      cta: 'Subscribe Now',
      popular: true
    },
    {
      id: 3,
      name: 'Enterprise',
      subtitle: 'For Large Organizations',
      price: 'Custom',
      period: 'pricing',
      color: 'purple',
      users: 'Unlimited users',
      features: [
        'Custom risk models',
        'Real-time data ingestion',
        ' 24/7 phone + dedicated support',
        'Custom integrations',
        'Advanced ML forecasting',
        'SLA guarantees (99.99% uptime)',
        'White-label options'
      ],
      cta: 'Contact Sales'
    }
  ]

  const complianceStandards = [
    { icon: '✓', title: 'ISO 27001', desc: 'Information Security Management' },
    { icon: '✓', title: 'SOC 2 Type II', desc: 'Security & Availability Compliance' },
    { icon: '✓', title: 'GDPR Compliant', desc: 'EU Data Protection Regulations' },
    { icon: '✓', title: 'CSEP Validated', desc: 'Earthquake Forecasting Standards' },
  ]

  return (
    <div className="w-full bg-white">
      {/* Hero Section */}
      <section className="relative h-96 flex items-center justify-center overflow-hidden pt-12">
        <div className="absolute inset-0 opacity-20"
          style={{
            background: 'radial-gradient(circle at 50% 50%, rgba(99, 102, 241, 0.3), transparent 60%)',
            animation: 'float 8s ease-in-out infinite'
          }}
        />

        <div className="relative z-10 text-center px-6 max-w-4xl mx-auto">
          <h1 className="text-6xl md:text-7xl font-light text-gray-900 mb-4 leading-tight">
            Compliance & Packages
          </h1>
          <p className="text-xl text-gray-600 font-light">
            Enterprise-grade security, compliance, and flexible pricing plans
          </p>

          <div className="grid grid-cols-3 gap-8 mt-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-3xl font-light text-indigo-600">3</div>
              <div className="text-sm text-gray-600 font-light mt-2">Pricing Plans</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-light text-blue-600">1000+</div>
              <div className="text-sm text-gray-600 font-light mt-2">Active Customers</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-light text-purple-600">99.99%</div>
              <div className="text-sm text-gray-600 font-light mt-2">Uptime SLA</div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Plans */}
      <section className="py-24 px-6 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-5xl font-light text-gray-900 mb-4">Simple, Transparent Pricing</h2>
            <p className="text-xl text-gray-600 font-light">
              Choose the plan that fits your organization
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {packages.map((pkg) => (
              <div
                key={pkg.id}
                onClick={() => setSelectedPackage(pkg)}
                className={`group cursor-pointer relative`}
              >
                {pkg.popular && (
                  <div className="absolute -top-4 left-0 right-0 flex justify-center">
                    <span className="px-4 py-1 bg-green-600 text-white text-xs font-light rounded-full">
                      Most Popular
                    </span>
                  </div>
                )}
                <div className={`bg-white p-8 rounded-2xl shadow-sm hover:shadow-xl transition-all border-2 ${
                  pkg.popular ? 'border-green-600' : 'border-gray-200'
                } ${pkg.popular ? 'scale-105' : ''}`}>
                  <h3 className="text-2xl font-light text-gray-900 mb-1">{pkg.name}</h3>
                  <p className="text-sm text-gray-600 font-light mb-6">{pkg.subtitle}</p>

                  <div className="mb-6">
                    <span className="text-4xl font-light text-gray-900">{pkg.price}</span>
                    <span className="text-gray-600 font-light ml-2">{pkg.period}</span>
                  </div>

                  <div className="text-sm text-gray-600 font-light mb-8 pb-8 border-b border-gray-200">
                    {pkg.users}
                  </div>

                  <button className={`w-full px-6 py-3 rounded-lg font-light transition-all mb-8 ${
                    pkg.popular
                      ? 'bg-green-600 text-white hover:bg-green-700'
                      : 'bg-gray-100 text-gray-900 hover:bg-gray-200'
                  }`}>
                    {pkg.cta}
                  </button>

                  <div className="space-y-3">
                    {pkg.features.map((feature, i) => (
                      <div key={i} className="flex items-start gap-3">
                        <CheckCircle size={16} className={`text-${pkg.color}-600 flex-shrink-0 mt-0.5`} />
                        <span className="text-sm text-gray-700 font-light">{feature}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Compliance & Security */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-5xl font-light text-gray-900 mb-4 text-center">
            Enterprise Security & Compliance
          </h2>
          <p className="text-xl text-gray-600 font-light text-center mb-16 max-w-2xl mx-auto">
            Your data security and regulatory compliance are our top priorities
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {complianceStandards.map((standard, i) => (
              <div key={i} className="p-6 border border-gray-200 rounded-2xl text-center hover:border-indigo-300 transition-all">
                <div className="text-3xl mb-3">{standard.icon}</div>
                <h3 className="text-lg font-light text-gray-900 mb-2">{standard.title}</h3>
                <p className="text-sm text-gray-600 font-light">{standard.desc}</p>
              </div>
            ))}
          </div>

          <div className="mt-16 bg-indigo-50 rounded-2xl p-12 text-center border border-indigo-200">
            <Shield size={32} className="text-indigo-600 mx-auto mb-4" />
            <h3 className="text-2xl font-light text-gray-900 mb-2">Regular Security Audits</h3>
            <p className="text-gray-600 font-light max-w-2xl mx-auto">
              Third-party security audits conducted quarterly. All data encrypted in transit and at rest.
              Zero-trust security architecture with role-based access control.
            </p>
          </div>
        </div>
      </section>

      {/* Selected Package Detail */}
      {selectedPackage && (
        <section className="py-24 px-6 bg-gradient-to-br from-indigo-50 to-blue-50">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-4xl font-light text-gray-900">
                {selectedPackage.name} Plan Details
              </h2>
              <button
                onClick={() => setSelectedPackage(null)}
                className="text-gray-500 hover:text-gray-900 text-2xl"
              >
                ✕
              </button>
            </div>

            <div className="bg-white rounded-3xl p-12 shadow-lg">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-8 mb-12">
                {[
                  { label: 'Price', value: selectedPackage.price },
                  { label: 'Users', value: selectedPackage.users },
                  { label: 'Support', value: selectedPackage.name === 'Enterprise' ? '24/7' : selectedPackage.name === 'Professional' ? 'Priority' : 'Email' }
                ].map((stat, i) => (
                  <div key={i} className="text-center">
                    <div className="text-sm text-gray-600 font-light uppercase tracking-wider mb-2">
                      {stat.label}
                    </div>
                    <div className="text-2xl font-light text-indigo-600">{stat.value}</div>
                  </div>
                ))}
              </div>

              <div className="border-t border-gray-200 pt-8">
                <h3 className="text-2xl font-light text-gray-900 mb-4">Included Features</h3>
                <div className="space-y-3">
                  {selectedPackage.features.map((feature, i) => (
                    <div key={i} className="flex items-center gap-3 p-2">
                      <CheckCircle size={18} className="text-green-600 flex-shrink-0" />
                      <span className="text-gray-700 font-light">{feature}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-8 pt-8 border-t border-gray-200">
                <button className="w-full px-6 py-4 bg-indigo-600 text-white rounded-lg font-light hover:bg-indigo-700 transition-all">
                  {selectedPackage.cta}
                </button>
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
