import { latLngToCell, gridDisk } from 'h3-js'

// Ahr valley, Germany — Rhine flood event July 2021
const AHR_CENTER = { lat: 50.518, lng: 6.952 }
const RHINE_CENTER = { lat: 50.937, lng: 6.961 }
const MOSEL_CENTER = { lat: 50.357, lng: 7.591 }

function scoreColor(score) {
  if (score < 25) return [34, 197, 94]
  if (score < 50) return [234, 179, 8]
  if (score < 75) return [249, 115, 22]
  return [239, 68, 68]
}

function riskLevel(score) {
  if (score < 25) return 'LOW'
  if (score < 50) return 'MEDIUM'
  if (score < 75) return 'HIGH'
  return 'VERY_HIGH'
}

function seedRandom(seed) {
  let s = seed
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff
    return (s >>> 0) / 0xffffffff
  }
}

export function generateMockScores(hazardType = 'flood', dayIndex = 10) {
  const rand = seedRandom(hazardType === 'flood' ? 42 : hazardType === 'wildfire' ? 99 : 77)
  const intensity = EVENT_INTENSITY[Math.min(dayIndex, EVENT_INTENSITY.length - 1)]

  const centers =
    hazardType === 'flood'
      ? [AHR_CENTER, RHINE_CENTER, MOSEL_CENTER]
      : hazardType === 'wildfire'
      ? [{ lat: 44.5, lng: -0.6 }, { lat: 43.8, lng: 3.9 }]
      : [{ lat: 48.1, lng: 11.5 }, { lat: 51.5, lng: 7.5 }]

  const dates = getDates(hazardType)
  const scored_at = `${dates[Math.min(dayIndex, dates.length - 1)]}T06:00:00Z`

  const scores = []

  centers.forEach((center, ci) => {
    const centerCell = latLngToCell(center.lat, center.lng, 8)
    const cells = gridDisk(centerCell, ci === 0 ? 12 : 8)

    cells.forEach((cell, i) => {
      const distFactor = i < 7 ? 1 : i < 19 ? 0.75 : 0.5
      const baseScore = hazardType === 'flood' ? 72 : hazardType === 'wildfire' ? 68 : 62
      const noise = (rand() - 0.5) * 28
      const score = Math.max(4, Math.min(99, baseScore * distFactor * intensity + noise * intensity))
      const velocity = (rand() - 0.35) * 16

      scores.push({
        h3_cell: cell,
        score: Math.round(score),
        velocity_24h: Math.round(velocity * 10) / 10,
        risk_level: riskLevel(score),
        hazard_type: hazardType,
        scored_at,
      })
    })
  })

  return scores
}

export function generateAlerts(hazardType = 'flood') {
  const rand = seedRandom(hazardType === 'flood' ? 11 : hazardType === 'wildfire' ? 22 : 33)
  const scores = generateMockScores(hazardType)
  const locations = hazardType === 'flood'
    ? ['Ahr Valley', 'Rhine Basin', 'Mosel Valley', 'Koblenz Region', 'Bad Neuenahr', 'Ahrweiler', 'Cologne Region', 'Bonn Metro', 'Remagen', 'Sinzig', 'Euskirchen', 'Mayen']
    : hazardType === 'wildfire'
    ? ['Gironde Est', 'Landes Forest', 'Médoc Region', 'Bordeaux Hills', 'Camargue', 'Provence Sud', 'Var Interior', 'Corsica Nord']
    : ['Munich West', 'Ruhr Valley', 'Frankfurt Metro', 'Stuttgart Basin', 'Heidelberg', 'Mannheim', 'Karlsruhe', 'Freiburg']

  return scores
    .filter(s => s.velocity_24h > 4)
    .sort((a, b) => b.score - a.score)
    .slice(0, 12)
    .map((s, i) => ({
      ...s,
      velocity_24h: Math.round((4 + rand() * 14) * 10) / 10,
      location: locations[i % locations.length],
    }))
}

export function scoreToColor(score, alpha = 200) {
  const rgb = scoreColor(score)
  return [...rgb, alpha]
}

export const HAZARDS = [
  { id: 'flood',    label: 'Flood',    color: '#3b82f6' },
  { id: 'wildfire', label: 'Wildfire', color: '#f97316' },
  { id: 'heat',     label: 'Heat',     color: '#eab308' },
]

// Event dates for the time scrubber (11-day Rhine flood)
export const FLOOD_DATES = [
  '2021-07-04','2021-07-05','2021-07-06','2021-07-07','2021-07-08',
  '2021-07-09','2021-07-10','2021-07-11','2021-07-12','2021-07-13','2021-07-14',
]
export const WILDFIRE_DATES = [
  '2022-07-12','2022-07-13','2022-07-14','2022-07-15','2022-07-16',
  '2022-07-17','2022-07-18','2022-07-19','2022-07-20','2022-07-21','2022-07-22',
]
export const HEAT_DATES = [
  '2021-06-16','2021-06-17','2021-06-18','2021-06-19','2021-06-20',
  '2021-06-21','2021-06-22','2021-06-23','2021-06-24','2021-06-25','2021-06-26',
]

export function getDates(hazard) {
  if (hazard === 'wildfire') return WILDFIRE_DATES
  if (hazard === 'heat') return HEAT_DATES
  return FLOOD_DATES
}

// Intensity ramp: pre-event → rising → peak → receding
const EVENT_INTENSITY = [0.28, 0.33, 0.40, 0.52, 0.63, 0.74, 0.84, 0.92, 1.0, 0.93, 0.85]

export const HAZARD_VIEWS = {
  flood:    { longitude: 6.95,  latitude: 50.52, zoom: 8.5, pitch: 35, bearing: 0 },
  wildfire: { longitude: -0.55, latitude: 44.55, zoom: 8.0, pitch: 35, bearing: -15 },
  heat:     { longitude: 9.20,  latitude: 48.90, zoom: 7.5, pitch: 30, bearing: 0 },
}

export const INITIAL_VIEW_STATE = HAZARD_VIEWS.flood
