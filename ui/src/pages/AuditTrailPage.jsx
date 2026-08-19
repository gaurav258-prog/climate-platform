
import SimpleIcon from '../components/SimpleIcon'

export default function AuditTrailPage() {
  const audits = [
    { date: '2026-06-26', user: 'CFO', action: 'Approved TCFD Disclosure', change: 'v2.3 → v2.4', status: 'Approved' },
    { date: '2026-06-25', user: 'Compliance Officer', action: 'Updated GHG Emissions Data', change: 'Scope 1/2 revised', status: 'Reviewed' },
    { date: '2026-06-24', user: 'Risk Manager', action: 'Added Climate Scenario Analysis', change: 'Added 1.5°C pathway', status: 'Draft' },
    { date: '2026-06-20', user: 'Data Team', action: 'Imported Portfolio Data', change: 'Bank Assets updated', status: 'Completed' },
    { date: '2026-06-15', user: 'External Auditor', action: 'Verified Scope 3 Emissions', change: 'Assurance signed', status: 'Completed' },
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Audit Trail & Version Control</h1>
            <p className="text-gray-600">Track all compliance decisions and regulatory filing amendments</p>
          </div>
          <div><SimpleIcon type="branch" /></div>
        </div>
      </section>

      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Date</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">User</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Action</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Change</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {audits.map((a, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm text-gray-700">{a.date}</td>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{a.user}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{a.action}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{a.change}</td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                      a.status === 'Approved' ? 'bg-green-100 text-green-800' :
                      a.status === 'Reviewed' ? 'bg-blue-100 text-blue-800' :
                      a.status === 'Draft' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {a.status}
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
