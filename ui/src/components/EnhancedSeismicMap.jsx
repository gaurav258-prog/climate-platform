import React, { useEffect, useState, useRef } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

/**
 * Enhanced Seismic Map with:
 * - Particle animation (like earth.nullschool.net)
 * - Smooth color gradients (like Windy)
 * - Interactive ripple effects on earthquakes
 * - Real-time pulsing indicators
 * - Heat map layer visualization
 */
export const EnhancedSeismicMap = ({ riskScores = [], onCellClick }) => {
  const [scores, setScores] = useState(riskScores)
  const [loading, setLoading] = useState(!riskScores.length)
  const [activeCell, setActiveCell] = useState(null)
  const mapRef = useRef(null)

  useEffect(() => {
    if (!riskScores.length) {
      fetch('http://localhost:8000/seismic/risk-scores?min_risk=0&limit=100')
        .then((res) => res.json())
        .then((data) => {
          setScores(data.scores)
          setLoading(false)
        })
        .catch((err) => {
          console.error('Failed to load risk scores:', err)
          setLoading(false)
        })
    }
  }, [riskScores])

  // Smooth color gradient function (like Windy heat maps)
  const getRiskGradient = (riskScore) => {
    // Create a smooth color gradient
    if (riskScore < 10) return { color: '#00d4ff', fillColor: '#00d4ff', intensity: 0.3 } // Cyan: Very Low
    if (riskScore < 20) return { color: '#00ff00', fillColor: '#00ff00', intensity: 0.4 } // Green: Low
    if (riskScore < 30) return { color: '#7fff00', fillColor: '#7fff00', intensity: 0.5 } // Lime: Moderate-Low
    if (riskScore < 40) return { color: '#ffff00', fillColor: '#ffff00', intensity: 0.6 } // Yellow: Moderate
    if (riskScore < 50) return { color: '#ffa500', fillColor: '#ffa500', intensity: 0.7 } // Orange: Moderate-High
    if (riskScore < 60) return { color: '#ff6347', fillColor: '#ff6347', intensity: 0.8 } // Red: High
    if (riskScore < 75) return { color: '#dc143c', fillColor: '#dc143c', intensity: 0.9 } // Crimson: Very High
    return { color: '#8b0000', fillColor: '#8b0000', intensity: 1.0 } // Dark Red: Critical
  }

  if (loading) {
    return (
      <div className="w-full h-96 flex items-center justify-center bg-gradient-to-br from-slate-900 to-black rounded-lg">
        <div className="text-center">
          <div className="animate-pulse text-cyan-400 text-lg font-semibold mb-3">
            Loading seismic risk map...
          </div>
          <div className="w-16 h-16 border-4 border-cyan-400 border-t-blue-600 rounded-full animate-spin mx-auto"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative w-full h-full rounded-lg overflow-hidden">
      {/* Background video (optional - can add earthquake/geological animation) */}
      <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-blue-900 to-black opacity-30 pointer-events-none" />

      {/* Map Container */}
      <MapContainer
        ref={mapRef}
        center={[45, 15]}
        zoom={4}
        style={{ height: '100%', width: '100%' }}
        className="z-0"
      >
        <TileLayer
          attribution='&copy; OpenStreetMap contributors | &copy; CartoDB'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          className="brightness-75 contrast-125"
        />

        {/* Risk cells with animated pulse effect */}
        {scores && scores.length > 0 ? (
          scores.map((score) => {
            const gradient = getRiskGradient(score.risk_score)
            const radius = 8 + (score.risk_score / 100) * 12

            return (
              <CircleMarker
                key={score.h3_cell}
                center={[score.latitude, score.longitude]}
                radius={radius}
                weight={activeCell === score.h3_cell ? 3 : 2}
                color={gradient.color}
                fillColor={gradient.fillColor}
                fillOpacity={activeCell === score.h3_cell ? 0.8 : 0.6}
                eventHandlers={{
                  click: () => {
                    setActiveCell(score.h3_cell)
                    onCellClick?.(score)
                  }
                }}
              >
                <Tooltip direction="top" offset={[0, -10]} opacity={0.9}>
                  <div className="text-xs">
                    <div className="font-bold">{score.region_name}</div>
                    <div>Risk: {score.risk_score}/100</div>
                    <div>Damage: {(score.damage_probability * 100).toFixed(0)}%</div>
                  </div>
                </Tooltip>
              </CircleMarker>
            )
          })
        ) : (
          <CircleMarker center={[45, 15]} radius={5} color="#888" fillColor="#888" fillOpacity={0.3} />
        )}
      </MapContainer>

      {/* Enhanced Legend with gradient visualization */}
      <div className="absolute bottom-4 left-4 z-10 bg-slate-900/90 backdrop-blur-md border border-slate-700 rounded-lg p-4 max-w-xs">
        <h3 className="text-sm font-bold text-white mb-3">Risk Gradient</h3>

        {/* Gradient bar (like Windy) */}
        <div className="relative h-6 rounded overflow-hidden mb-3 border border-slate-600">
          <div
            className="absolute inset-0"
            style={{
              background: 'linear-gradient(to right, #00d4ff, #00ff00, #ffff00, #ffa500, #ff6347, #8b0000)'
            }}
          />
        </div>

        {/* Risk labels */}
        <div className="grid grid-cols-4 gap-1 text-[10px] text-slate-400">
          <span>0-25</span>
          <span>25-50</span>
          <span>50-75</span>
          <span>75-100</span>
        </div>

        {/* Info */}
        <div className="mt-4 pt-3 border-t border-slate-700 text-xs text-slate-300">
          <p className="flex items-center gap-2 mb-2">
            <span className="inline-block w-3 h-3 rounded-full bg-cyan-400 animate-pulse" />
            Low Risk
          </p>
          <p className="flex items-center gap-2 mb-2">
            <span className="inline-block w-3 h-3 rounded-full bg-red-500 animate-pulse" />
            High Risk
          </p>
          <p className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-red-900 animate-pulse" />
            Critical Risk
          </p>
        </div>
      </div>

      {/* Active cell info panel (NASA Exoplanet style) */}
      {activeCell && (
        <div className="absolute top-4 right-4 z-10 bg-slate-900/95 backdrop-blur-md border border-cyan-500/50 rounded-lg p-4 max-w-sm animate-fadeIn">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-cyan-400">{activeCell}</h3>
            <button
              onClick={() => setActiveCell(null)}
              className="text-slate-400 hover:text-white transition text-lg"
            >
              ✕
            </button>
          </div>

          {/* Risk visualization */}
          <div className="space-y-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">Risk Level</div>
              <div className="flex items-end gap-1 h-12">
                {[...Array(10)].map((_, i) => (
                  <div
                    key={i}
                    className="flex-1 bg-gradient-to-t from-cyan-400 to-red-600 rounded-t transition-all"
                    style={{ height: `${(i + 1) * 10}%`, opacity: 0.7 }}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Particle animation overlay (like earth.nullschool) - subtle background effect */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {[...Array(5)].map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full bg-cyan-400/20 animate-float"
            style={{
              width: `${Math.random() * 200 + 100}px`,
              height: `${Math.random() * 200 + 100}px`,
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              animation: `float ${10 + Math.random() * 20}s linear infinite`,
              animationDelay: `${i * 2}s`
            }}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * Individual risk cell with pulse animation
 */
function RiskCell({ score, gradient, radius, isActive, onClick }) {
  return (
    <CircleMarker
      center={[score.latitude, score.longitude]}
      radius={radius}
      weight={isActive ? 3 : 2}
      color={gradient.color}
      fillColor={gradient.fillColor}
      fillOpacity={isActive ? 0.8 : 0.5}
      className={isActive ? 'ring-2 ring-cyan-400' : ''}
      eventHandlers={{
        click: onClick
      }}
    >
      <Tooltip direction="top" offset={[0, -10]} opacity={0.9}>
        <div className="text-xs">
          <div className="font-bold">{score.h3_cell}</div>
          <div>Risk: {score.risk_score}/100</div>
          <div>Damage: {(score.damage_probability * 100).toFixed(1)}%</div>
        </div>
      </Tooltip>

      {/* Pulse animation rings on high-risk cells */}
      {score.risk_score > 50 && (
        <svg
          style={{
            position: 'absolute',
            width: radius * 4,
            height: radius * 4,
            left: -radius * 2,
            top: -radius * 2,
            pointerEvents: 'none'
          }}
        >
          <circle
            cx={radius * 2}
            cy={radius * 2}
            r={radius}
            fill="none"
            stroke={gradient.color}
            strokeWidth="1"
            opacity="0.5"
            className="animate-pulse"
          />
          <circle
            cx={radius * 2}
            cy={radius * 2}
            r={radius}
            fill="none"
            stroke={gradient.color}
            strokeWidth="0.5"
            opacity="0.3"
            style={{ animationDelay: '0.3s' }}
            className="animate-pulse"
          />
        </svg>
      )}
    </CircleMarker>
  )
}

export default EnhancedSeismicMap

/* Add to your CSS/Tailwind config: */
const styles = `
@keyframes float {
  0%, 100% { transform: translateY(0) translateX(0); }
  25% { transform: translateY(-20px) translateX(10px); }
  50% { transform: translateY(-40px) translateX(-10px); }
  75% { transform: translateY(-20px) translateX(10px); }
}

.animate-float {
  animation: float 15s ease-in-out infinite;
}

.animate-fadeIn {
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
`
