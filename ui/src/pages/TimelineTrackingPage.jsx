import { Calendar } from 'lucide-react'

export default function TimelineTrackingPage() {
  const timelines = [
    { framework: 'TCFD', effective: '2023-06-26', daysToFramework: 0, customerDeadline: '2023-07-03', daysRemaining: -729, status: 'Overdue' },
    { framework: 'EU Taxonomy', effective: '2024-01-01', daysToFramework: -543, customerDeadline: '2024-01-08', daysRemaining: -895, status: 'Overdue' },
    { framework: 'SEC Climate Rules', effective: '2024-12-18', daysToFramework: -190, customerDeadline: '2024-12-25', daysRemaining: -183, status: 'Overdue' },
    { framework: 'CSRD (EU)', effective: '2025-01-01', daysToFramework: -177, customerDeadline: '2025-01-08', daysRemaining: -170, status: 'Overdue' },
    { framework: 'UK FCA Climate Rules', effective: '2025-06-01', daysToFramework: 67, customerDeadline: '2025-06-08', daysRemaining: 74, status: 'In Progress' },
    { framework: 'SBTi Validation', effective: '2026-12-31', daysToFramework: 554, customerDeadline: '2027-01-07', daysRemaining: 561, status: 'Pending' },
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Timeline & Deadline Tracking</h1>
            <p className="text-gray-600">Framework effective date → Customer deadline (regulatory deadline + 7 days + implementation)</p>
          </div>
          <Calendar className="text-blue-600" size={40} />
        </div>
      </section>

      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Framework</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Effective Date</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Customer Deadline</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Days Remaining</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {timelines.map((item, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{item.framework}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{item.effective}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{item.customerDeadline}</td>
                  <td className="px-6 py-4 text-sm font-semibold">
                    <span className={item.daysRemaining < 0 ? 'text-red-600' : item.daysRemaining < 90 ? 'text-orange-600' : 'text-green-600'}>
                      {item.daysRemaining > 0 ? '+' : ''}{item.daysRemaining} days
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                      item.status === 'Overdue' ? 'bg-red-100 text-red-800' :
                      item.status === 'In Progress' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-green-100 text-green-800'
                    }`}>
                      {item.status}
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
