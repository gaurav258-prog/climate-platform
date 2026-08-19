
import SimpleIcon from '../components/SimpleIcon'

export default function RegulatoryChangeDetectionPage() {
  const changes = [
    { framework: 'EU Taxonomy', version: '2024 v2.0', affected: 'Activity Classification', effort: 20, status: 'New' },
    { framework: 'TCFD', version: 'Updated 2024', affected: 'Scenario Analysis', effort: 15, status: 'New' },
    { framework: 'SEC', version: '2024 Final Rule', affected: 'GHG Emissions Scope', effort: 12, status: 'In Review' },
    { framework: 'CSRD', version: '2024 v1.1', affected: 'Assurance Requirements', effort: 8, status: 'Implemented' },
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Regulatory Change Detection</h1>
            <p className="text-gray-600">Track framework version changes and affected processing modules</p>
          </div>
          <div><SimpleIcon type="alert" /></div>
        </div>
      </section>

      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Framework</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Version</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Affected Area</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Effort (hrs)</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {changes.map((c, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{c.framework}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{c.version}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{c.affected}</td>
                  <td className="px-6 py-4 text-sm font-semibold text-gray-900">{c.effort}h</td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                      c.status === 'New' ? 'bg-red-100 text-red-800' :
                      c.status === 'In Review' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-green-100 text-green-800'
                    }`}>
                      {c.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
