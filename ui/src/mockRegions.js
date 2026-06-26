// German administrative regions (Kreise) in the Rhine / Ahr area
export const REGIONS = [
  { id: 'r01', name: 'Ahrweiler',      population: 128_000, lat: 50.529, lng: 6.993 },
  { id: 'r02', name: 'Koblenz',        population: 114_000, lat: 50.356, lng: 7.591 },
  { id: 'r03', name: 'Bonn',           population: 329_000, lat: 50.733, lng: 7.100 },
  { id: 'r04', name: 'Rhein-Sieg',     population: 602_000, lat: 50.838, lng: 7.249 },
  { id: 'r05', name: 'Cologne',        population: 1_084_000, lat: 50.938, lng: 6.960 },
  { id: 'r06', name: 'Euskirchen',     population: 196_000, lat: 50.659, lng: 6.789 },
  { id: 'r07', name: 'Cochem-Zell',    population:  62_000, lat: 50.145, lng: 7.166 },
  { id: 'r08', name: 'Mayen-Koblenz',  population: 214_000, lat: 50.356, lng: 7.200 },
]

// Recommended actions keyed by hazard type
export const ACTION_TEMPLATES = {
  flood: [
    { id: 'f1', priority: 'URGENT', action: 'Pre-position river rescue boats',         region: 'Ahrweiler',     unit: '12 boats, 48 crew', category: 'Resource' },
    { id: 'f2', priority: 'URGENT', action: 'Open emergency flood shelters',            region: 'Ahrweiler',     unit: '4 sites · 2,400 capacity', category: 'Shelter' },
    { id: 'f3', priority: 'URGENT', action: 'Notify at-risk residents via SMS',         region: 'Rhine Valley',  unit: '45,000 recipients', category: 'Alert' },
    { id: 'f4', priority: 'HIGH',   action: 'Alert hospitals — increase ICU capacity',  region: 'Koblenz',       unit: '3 hospitals · +120 beds', category: 'Medical' },
    { id: 'f5', priority: 'HIGH',   action: 'Close riverside roads (B9 corridor)',      region: 'Bonn',          unit: '14 km of road', category: 'Transport' },
    { id: 'f6', priority: 'HIGH',   action: 'Evacuate low-lying residential zones',    region: 'Ahrweiler',     unit: 'Zone A & B · ~3,200 people', category: 'Evacuation' },
    { id: 'f7', priority: 'MEDIUM', action: 'Pre-position sandbag reserves',           region: 'Bonn',          unit: '80,000 sandbags', category: 'Resource' },
    { id: 'f8', priority: 'MEDIUM', action: 'Request Bundeswehr flood support',        region: 'Rhine Basin',   unit: 'Standing request filed', category: 'Support' },
  ],
  wildfire: [
    { id: 'w1', priority: 'URGENT', action: 'Deploy aerial firefighting units',        region: 'Landes Forest', unit: '3 Canadair, 2 helicopters', category: 'Resource' },
    { id: 'w2', priority: 'URGENT', action: 'Evacuate communities on fire perimeter',  region: 'Gironde Est',   unit: '~8,000 residents', category: 'Evacuation' },
    { id: 'w3', priority: 'URGENT', action: 'Close forest access roads',              region: 'Médoc Region',  unit: '23 routes closed', category: 'Transport' },
    { id: 'w4', priority: 'HIGH',   action: 'Activate escape route signage',          region: 'Gironde Est',   unit: 'D1, D3, N10 corridors', category: 'Alert' },
    { id: 'w5', priority: 'HIGH',   action: 'Alert respiratory units at hospitals',   region: 'Bordeaux',      unit: '4 hospitals notified', category: 'Medical' },
    { id: 'w6', priority: 'MEDIUM', action: 'Pre-position water tankers',             region: 'Landes Forest', unit: '18 tankers · 540,000L', category: 'Resource' },
  ],
  heat: [
    { id: 'h1', priority: 'URGENT', action: 'Open cooling centres',                   region: 'Munich',        unit: '42 sites · 18,000 capacity', category: 'Shelter' },
    { id: 'h2', priority: 'URGENT', action: 'Alert care homes & hospitals',           region: 'Ruhr Valley',   unit: '214 facilities contacted', category: 'Medical' },
    { id: 'h3', priority: 'HIGH',   action: 'Notify vulnerable residents (65+)',      region: 'Stuttgart',     unit: '124,000 households', category: 'Alert' },
    { id: 'h4', priority: 'HIGH',   action: 'Restrict outdoor construction work',     region: 'Frankfurt',     unit: 'Hessen heat ordinance active', category: 'Regulation' },
    { id: 'h5', priority: 'HIGH',   action: 'Increase water distribution points',    region: 'Munich',        unit: '+120 street stations', category: 'Resource' },
    { id: 'h6', priority: 'MEDIUM', action: 'Brief school head teachers',            region: 'Bavaria',       unit: '1,840 schools', category: 'Alert' },
    { id: 'h7', priority: 'MEDIUM', action: 'Extend public pool hours',              region: 'Munich',        unit: '24 pools · midnight close', category: 'Resource' },
  ],
}

export const PRIORITY_ORDER = { URGENT: 0, HIGH: 1, MEDIUM: 2 }
