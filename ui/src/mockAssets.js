// Mock portfolio assets — representative loan book / property portfolio
export const MOCK_ASSETS = [
  { id: 'a1', name: 'Frankfurt HQ',       lat: 50.110, lng: 8.682,  type: 'Office',       exposure_eur: 48_000_000 },
  { id: 'a2', name: 'Cologne Logistics',  lat: 50.938, lng: 6.960,  type: 'Industrial',   exposure_eur: 31_000_000 },
  { id: 'a3', name: 'Bonn Retail Park',   lat: 50.733, lng: 7.100,  type: 'Retail',       exposure_eur: 22_000_000 },
  { id: 'a4', name: 'Koblenz Warehouse',  lat: 50.356, lng: 7.591,  type: 'Industrial',   exposure_eur: 17_500_000 },
  { id: 'a5', name: 'Düsseldorf Tower',   lat: 51.227, lng: 6.773,  type: 'Office',       exposure_eur: 95_000_000 },
  { id: 'a6', name: 'Bad Neuenahr Hotel', lat: 50.548, lng: 6.951,  type: 'Hospitality',  exposure_eur: 12_000_000 },
  { id: 'a7', name: 'Ahrweiler Apt Complex', lat: 50.529, lng: 6.993, type: 'Residential', exposure_eur: 8_500_000 },
  { id: 'a8', name: 'Mainz Mixed-Use',    lat: 49.998, lng: 8.271,  type: 'Mixed',        exposure_eur: 41_000_000 },
]

export function formatEur(n) {
  if (n >= 1_000_000) return `€${(n / 1_000_000).toFixed(0)}M`
  return `€${(n / 1_000).toFixed(0)}K`
}
