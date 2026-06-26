/**
 * Regulatory Reporting Module Home - Minimalist BCG/McKinsey Style
 * Central hub for all regulatory reporting tools
 */

const SimpleIcon = ({ type }) => {
  const styles = "w-6 h-6 stroke-current stroke-1.5"
  if (type === 'bars') return (
    <svg className={styles} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="12" width="3" height="9" />
      <rect x="10" y="6" width="3" height="15" />
      <rect x="17" y="3" width="3" height="18" />
    </svg>
  )
  if (type === 'alert') return (
    <svg className={styles} viewBox="0 0 24 24" fill="none">
      <path d="M12 3 L21 18 H3 Z" />
      <line x1="12" y1="10" x2="12" y2="14" />
      <circle cx="12" cy="17" r="0.5" fill="currentColor" />
    </svg>
  )
  if (type === 'check') return (
    <svg className={styles} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" />
      <path d="M7 12 L11 16 L17 8" />
    </svg>
  )
  if (type === 'trend') return (
    <svg className={styles} viewBox="0 0 24 24" fill="none">
      <path d="M3 21 L8 13 L13 16 L21 5" />
      <polyline points="18 5 21 5 21 8" />
    </svg>
  )
  if (type === 'stack') return (
    <svg className={styles} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="3" width="18" height="4" />
      <rect x="3" y="9" width="18" height="4" />
      <rect x="3" y="15" width="18" height="4" />
    </svg>
  )
  if (type === 'compare') return (
    <svg className={styles} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="6" width="7" height="12" />
      <rect x="14" y="3" width="7" height="15" />
      <path d="M10 18 L14 18" />
    </svg>
  )
  if (type === 'calendar') return (
    <svg className={styles} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="17" rx="1" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="9" y1="4" x2="9" y2="9" />
      <line x1="15" y1="4" x2="15" y2="9" />
    </svg>
  )
  if (type === 'branch') return (
    <svg className={styles} viewBox="0 0 24 24" fill="none">
      <circle cx="6" cy="4" r="2" />
      <circle cx="6" cy="20" r="2" />
      <circle cx="18" cy="12" r="2" />
      <path d="M6 6 L6 18" />
      <path d="M6 12 L18 12" />
    </svg>
  )
  return null
}

export default function RegulatoryReportingHome({ onModuleSelect }) {
  const modules = [
    {
      id: 'scenario-impact',
      name: 'Scenario Financial Impact',
      iconType: 'bars',
      description: 'Calculate projected revenue, revenue_impact, npv, and stranded asset risk per scenario/time-horizon',
      color: 'text-blue-600',
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-300',
      status: 'Active',
      metrics: ['NPV Analysis', 'Revenue Impact', 'Scenario Modeling']
    },
    {
      id: 'regulatory-changes',
      name: 'Regulatory Change Detection',
      iconType: 'alert',
      description: 'Track framework version changes, affected tables, processing modules, and implementation effort hours',
      color: 'text-orange-600',
      bgColor: 'bg-orange-50',
      borderColor: 'border-orange-300',
      status: 'Active',
      metrics: ['Framework Tracking', 'Impact Analysis', 'Effort Estimation']
    },
    {
      id: 'compliance-gap',
      name: 'Compliance Gap Analysis',
      iconType: 'check',
      description: 'Map bank_assets + emissions to TCFD/Taxonomy/SEC. Identify missing or incomplete fields',
      color: 'text-green-600',
      bgColor: 'bg-green-50',
      borderColor: 'border-green-300',
      status: 'Active',
      metrics: ['Gap Identification', 'Completeness Check', 'Remediation Plan']
    },
    {
      id: 'risk-materiality',
      name: 'Risk Materiality Calculation',
      iconType: 'trend',
      description: 'Calculate financial_impact_materiality_pct. Compare to bank materiality threshold for disclosure',
      color: 'text-purple-600',
      bgColor: 'bg-purple-50',
      borderColor: 'border-purple-300',
      status: 'Active',
      metrics: ['Materiality Assessment', 'Threshold Comparison', 'Disclosure Logic']
    },
    {
      id: 'portfolio-aggregation',
      name: 'Portfolio Aggregation',
      iconType: 'stack',
      description: 'Sum/weight all bank_assets by sector/geography for portfolio-level TCFD disclosures',
      color: 'text-cyan-600',
      bgColor: 'bg-cyan-50',
      borderColor: 'border-cyan-300',
      status: 'Active',
      metrics: ['Sector Analysis', 'Geographic Breakdown', 'Portfolio Summary']
    },
    {
      id: 'benchmarking',
      name: 'Comparative Benchmarking',
      iconType: 'compare',
      description: "Compare bank's scores vs peer group (sector/size) for investor/regulator positioning",
      color: 'text-pink-600',
      bgColor: 'bg-pink-50',
      borderColor: 'border-pink-300',
      status: 'Active',
      metrics: ['Peer Comparison', 'Positioning Analysis', 'Competitive Intelligence']
    },
    {
      id: 'timeline-tracking',
      name: 'Timeline & Deadline Tracking',
      iconType: 'calendar',
      description: 'Framework effective_date → customer deadline (regulatory deadline = 7 days + implementation time)',
      color: 'text-red-600',
      bgColor: 'bg-red-50',
      borderColor: 'border-red-300',
      status: 'Active',
      metrics: ['Deadline Calculation', 'Implementation Tracking', 'Timeline Management']
    },
    {
      id: 'audit-trail',
      name: 'Audit Trail & Version Control',
      iconType: 'branch',
      description: 'Track filing amendments, regulation version changes, compliance decisions for regulator review',
      color: 'text-indigo-600',
      bgColor: 'bg-indigo-50',
      borderColor: 'border-indigo-300',
      status: 'Active',
      metrics: ['Version Control', 'Change Tracking', 'Audit History']
    }
  ]

  const reports = [
    { name: 'TCFD Disclosure', description: 'Generate TCFD compliance report' },
    { name: 'EU Taxonomy Report', description: 'Generate EU Taxonomy alignment report' },
    { name: 'Risk Dashboard', description: 'Interactive risk visualization & metrics' }
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      {/* Hero Section */}
      <section className="relative min-h-[35vh] flex items-center justify-center overflow-hidden pt-12 pb-12 bg-white border-b border-gray-200">
        <div className="text-center px-6 max-w-4xl mx-auto w-full">
          <h1 className="text-6xl md:text-7xl font-light text-gray-900 mb-6 leading-tight">
            Regulatory
            <span className="block text-indigo-600">Reporting</span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-4 max-w-2xl mx-auto leading-relaxed">
            Comprehensive compliance framework for climate financial risk disclosure, gap analysis, and regulatory intelligence.
          </p>

          <p className="text-sm text-gray-500 font-light">
            Select a module to analyze, calculate, and report on regulatory requirements across your portfolio.
          </p>
        </div>
      </section>

      {/* Analysis Modules Grid */}
      <section className="py-16 px-6 max-w-7xl mx-auto w-full">
        <h2 className="text-3xl font-light text-gray-900 mb-8">Analysis Modules</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {modules.map((module) => (
              <button
                key={module.id}
                onClick={() => onModuleSelect(module.id)}
                className={`${module.bgColor} ${module.borderColor} rounded-lg border-2 p-8 text-left hover:shadow-md transition-all cursor-pointer bg-white`}
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-xl font-semibold text-gray-900">{module.name}</h3>
                    <span className={`inline-block mt-2 px-3 py-1 rounded-full text-xs font-semibold ${module.color} ${module.bgColor}`}>
                      {module.status}
                    </span>
                  </div>
                  <div className={`${module.color} flex-shrink-0`}>
                    <SimpleIcon type={module.iconType} />
                  </div>
                </div>

                {/* Description */}
                <p className="text-gray-700 text-sm leading-relaxed mb-6">
                  {module.description}
                </p>

                {/* Metrics */}
                <div className="space-y-2 pt-6 border-t border-gray-200">
                  {module.metrics.map((metric, idx) => (
                    <div key={idx} className="text-xs text-gray-600">
                      <span className={`inline-block w-2 h-2 rounded-full ${module.color} mr-2`} />
                      {metric}
                    </div>
                  ))}
                </div>

                {/* CTA */}
                <div className="mt-6 pt-6 border-t border-gray-200">
                  <p className={`text-sm font-semibold ${module.color}`}>
                    Open Analysis →
                  </p>
                </div>
              </button>
            )
          )}
        </div>
      </section>

      {/* Report Templates */}
      <section className="py-12 px-6 max-w-7xl mx-auto w-full">
        <h2 className="text-3xl font-light text-gray-900 mb-8">Report Templates</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <button onClick={() => onModuleSelect('tcfd-report')} className="bg-white rounded-lg border border-gray-300 p-8 hover:shadow-md transition-all text-left">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{reports[0].name}</h3>
            <p className="text-gray-600 text-sm mb-6">{reports[0].description}</p>
            <span className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">
              View Report →
            </span>
          </button>
          <button onClick={() => onModuleSelect('taxonomy-report')} className="bg-white rounded-lg border border-gray-300 p-8 hover:shadow-md transition-all text-left">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{reports[1].name}</h3>
            <p className="text-gray-600 text-sm mb-6">{reports[1].description}</p>
            <span className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">
              View Report →
            </span>
          </button>
          <button onClick={() => onModuleSelect('risk-dashboard')} className="bg-white rounded-lg border border-gray-300 p-8 hover:shadow-md transition-all text-left">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{reports[2].name}</h3>
            <p className="text-gray-600 text-sm mb-6">{reports[2].description}</p>
            <span className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">
              View Dashboard →
            </span>
          </button>
        </div>
      </section>

      {/* Info Cards */}
      <section className="py-12 px-6 max-w-7xl mx-auto w-full">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-indigo-50 rounded-lg border border-indigo-300 p-8">
            <h3 className="text-lg font-semibold text-indigo-900 mb-3">Data Model</h3>
            <ul className="text-sm text-indigo-800 space-y-2">
              <li>✓ Organizations & Bank Assets (CORE)</li>
              <li>✓ Climate Hazard Exposure Mapping</li>
              <li>✓ GHG Emissions Inventory</li>
              <li>✓ Climate Risk Scores (Financial + Regulatory)</li>
              <li>✓ Climate Scenarios (1.5°C, 2°C, 4°C)</li>
            </ul>
          </div>

          <div className="bg-green-50 rounded-lg border border-green-300 p-8">
            <h3 className="text-lg font-semibold text-green-900 mb-3">Standards Compliance</h3>
            <ul className="text-sm text-green-800 space-y-2">
              <li>✓ TCFD (Task Force on Climate-related Financial Disclosures)</li>
              <li>✓ EU Taxonomy (Economic Activities Classification)</li>
              <li>✓ SEC Climate Disclosure Rules</li>
              <li>✓ CSEP Validated Models</li>
              <li>✓ Regulatory Change Tracking</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Footer */}
      <div className="h-12" />
    </div>
  )
}
