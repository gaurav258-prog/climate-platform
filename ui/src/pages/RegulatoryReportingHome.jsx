import { BarChart3, AlertTriangle, CheckCircle, TrendingUp, Layers, GitCompare, Calendar, GitBranch } from 'lucide-react'

/**
 * Regulatory Reporting Module Home
 * Central hub for all regulatory reporting tools
 */
export default function RegulatoryReportingHome({ onModuleSelect }) {
  const modules = [
    {
      id: 'scenario-impact',
      name: 'Scenario Financial Impact',
      icon: BarChart3,
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
      icon: AlertTriangle,
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
      icon: CheckCircle,
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
      icon: TrendingUp,
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
      icon: Layers,
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
      icon: GitCompare,
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
      icon: Calendar,
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
      icon: GitBranch,
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
          {modules.map((module) => {
            const Icon = module.icon
            return (
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
                  <Icon className={`${module.color} flex-shrink-0`} size={28} />
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
          })}
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
