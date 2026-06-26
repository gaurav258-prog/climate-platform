import { useState } from 'react'

const SimpleIcon = ({ type }) => {
  const s = 'w-10 h-10 stroke-current stroke-1.5'
  if (type === 'bars') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="12" width="3" height="9" /><rect x="10" y="6" width="3" height="15" /><rect x="17" y="3" width="3" height="18" /></svg>
  if (type === 'check') return <svg className={s} viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" /><path d="M7 12 L11 16 L17 8" /></svg>
  if (type === 'trend') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M3 21 L8 13 L13 16 L21 5" /></svg>
  if (type === 'cal') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="17" rx="1" /><line x1="3" y1="9" x2="21" y2="9" /></svg>
  if (type === 'stack') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="4" /><rect x="3" y="9" width="18" height="4" /><rect x="3" y="15" width="18" height="4" /></svg>
  if (type === 'compare') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="7" height="12" /><rect x="14" y="3" width="7" height="15" /></svg>
  if (type === 'alert') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M12 3 L21 18 H3 Z" /></svg>
  if (type === 'file') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M4 4 L4 20 Q4 21 5 21 L19 21 Q20 21 20 20 L20 9 L14 3 L5 3 Q4 3 4 4" /></svg>
  if (type === 'branch') return <svg className={s} viewBox="0 0 24 24" fill="none"><circle cx="6" cy="4" r="2" /><circle cx="6" cy="20" r="2" /><circle cx="18" cy="12" r="2" /><path d="M6 6 L6 18 M6 12 L18 12" /></svg>
  return null
}

const SimpleIcon = ({ type }) => {
  const s = 'w-10 h-10 stroke-current stroke-1.5'
  if (type === 'bars') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="12" width="3" height="9" /><rect x="10" y="6" width="3" height="15" /><rect x="17" y="3" width="3" height="18" /></svg>
  if (type === 'check') return <svg className={s} viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" /><path d="M7 12 L11 16 L17 8" /></svg>
  if (type === 'trend') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M3 21 L8 13 L13 16 L21 5" /></svg>
  if (type === 'cal') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="17" rx="1" /><line x1="3" y1="9" x2="21" y2="9" /></svg>
  if (type === 'stack') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="4" /><rect x="3" y="9" width="18" height="4" /><rect x="3" y="15" width="18" height="4" /></svg>
  if (type === 'compare') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="7" height="12" /><rect x="14" y="3" width="7" height="15" /></svg>
  if (type === 'alert') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M12 3 L21 18 H3 Z" /></svg>
  if (type === 'file') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M4 4 L4 20 Q4 21 5 21 L19 21 Q20 21 20 20 L20 9 L14 3 L5 3 Q4 3 4 4" /></svg>
  if (type === 'branch') return <svg className={s} viewBox="0 0 24 24" fill="none"><circle cx="6" cy="4" r="2" /><circle cx="6" cy="20" r="2" /><circle cx="18" cy="12" r="2" /><path d="M6 6 L6 18 M6 12 L18 12" /></svg>
  return null
}

/**
 * Compliance Gap Analysis
 * Map bank assets + emissions to TCFD/Taxonomy/SEC frameworks
 */
export default function ComplianceGapAnalysisPage() {
  const [selectedFramework, setSelectedFramework] = useState('tcfd')

  const frameworks = {
    tcfd: {
      name: 'TCFD (Task Force on Climate-related Financial Disclosures)',
      completeness: 72,
      gaps: [
        { field: 'Governance Structure', status: 'missing', priority: 'high', effort: '8h' },
        { field: 'Risk Management Process', status: 'incomplete', priority: 'high', effort: '12h' },
        { field: 'Scenario Analysis Results', status: 'missing', priority: 'high', effort: '20h' },
        { field: 'GHG Scope 1 Emissions', status: 'complete', priority: 'none', effort: '-' },
        { field: 'GHG Scope 2 Emissions', status: 'complete', priority: 'none', effort: '-' },
        { field: 'Scope 3 Emissions', status: 'missing', priority: 'medium', effort: '16h' },
        { field: 'Transition Plan', status: 'incomplete', priority: 'medium', effort: '24h' },
      ]
    },
    taxonomy: {
      name: 'EU Taxonomy (Economic Activities Classification)',
      completeness: 58,
      gaps: [
        { field: 'Activity Classification', status: 'incomplete', priority: 'high', effort: '15h' },
        { field: 'Alignment Assessment', status: 'missing', priority: 'high', effort: '25h' },
        { field: 'DNSH (Do No Significant Harm)', status: 'missing', priority: 'high', effort: '20h' },
        { field: 'Minimum Safeguards', status: 'incomplete', priority: 'medium', effort: '10h' },
        { field: 'KPI Calculation', status: 'incomplete', priority: 'medium', effort: '12h' },
        { field: 'Revenue Mapping', status: 'complete', priority: 'none', effort: '-' },
      ]
    },
    sec: {
      name: 'SEC Climate Disclosure Rules',
      completeness: 65,
      gaps: [
        { field: 'Governance Disclosure', status: 'incomplete', priority: 'high', effort: '10h' },
        { field: 'Risk Assessment & Strategy', status: 'incomplete', priority: 'high', effort: '18h' },
        { field: 'GHG Emissions Data', status: 'missing', priority: 'high', effort: '14h' },
        { field: 'Climate Scenario Analysis', status: 'missing', priority: 'high', effort: '25h' },
        { field: 'Supply Chain Risk', status: 'incomplete', priority: 'medium', effort: '12h' },
      ]
    }
  }

  const current = frameworks[selectedFramework]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      {/* Header */}
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-4xl font-light text-gray-900 mb-2">Compliance Gap Analysis</h1>
              <p className="text-gray-600">Identify missing and incomplete fields for TCFD, EU Taxonomy, and SEC compliance</p>
            </div>
            <div><SimpleIcon type="check" /></div>
          </div>
        </div>
      </section>

      {/* Framework Selection */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <h2 className="text-2xl font-light text-gray-900 mb-6">Select Regulatory Framework</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Object.entries(frameworks).map(([key, framework]) => (
            <button
              key={key}
              onClick={() => setSelectedFramework(key)}
              className={`rounded-lg border-2 p-6 text-left transition-all ${
                selectedFramework === key
                  ? 'bg-green-50 border-gray-400 shadow-md'
                  : 'bg-white border-gray-200 hover:border-gray-300'
              }`}
            >
              <h3 className="text-lg font-semibold text-gray-900 mb-2">{framework.name.split('(')[0].trim()}</h3>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-green-600" style={{ width: `${framework.completeness}%` }} />
                </div>
                <span className="text-sm font-semibold text-gray-900">{framework.completeness}%</span>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Gap Analysis Table */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <h2 className="text-2xl font-light text-gray-900 mb-6">{current.name}</h2>
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Field</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Status</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Priority</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Est. Effort</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {current.gaps.map((gap, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm text-gray-900">{gap.field}</td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                      gap.status === 'complete' ? 'bg-green-100 text-green-800' :
                      gap.status === 'incomplete' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-red-100 text-red-800'
                    }`}>
                      {gap.status.charAt(0).toUpperCase() + gap.status.slice(1)}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    {gap.priority === 'none' ? (
                      <span className="text-gray-500">-</span>
                    ) : (
                      <span className={`inline-block px-3 py-1 rounded text-xs font-semibold ${
                        gap.priority === 'high' ? 'bg-red-100 text-red-800' :
                        'bg-orange-100 text-orange-800'
                      }`}>
                        {gap.priority.toUpperCase()}
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm font-semibold text-gray-900">{gap.effort}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Remediation Summary */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-8">
          <h3 className="text-lg font-semibold text-yellow-900 mb-4">Remediation Plan</h3>
          <ul className="space-y-2 text-yellow-800 text-sm">
            <li>✓ Total Completeness: {current.completeness}%</li>
            <li>✓ Missing Fields: {current.gaps.filter(g => g.status === 'missing').length}</li>
            <li>✓ Incomplete Fields: {current.gaps.filter(g => g.status === 'incomplete').length}</li>
            <li>✓ Total Effort Required: {current.gaps.filter(g => g.priority === 'high').length * 12 + current.gaps.filter(g => g.priority === 'medium').length * 8}+ hours</li>
            <li>✓ Recommended Timeline: 6-8 weeks for full compliance</li>
          </ul>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
