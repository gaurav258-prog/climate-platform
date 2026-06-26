import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Popup, Tooltip } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export const SeismicRiskMap = ({ riskScores = [], onCellClick }) => {
  const [scores, setScores] = useState(riskScores);
  const [loading, setLoading] = useState(!riskScores.length);

  useEffect(() => {
    if (!riskScores.length) {
      // Fetch from API
      fetch('http://localhost:8000/seismic/risk-scores?min_risk=0&limit=100')
        .then((res) => res.json())
        .then((data) => {
          setScores(data.scores);
          setLoading(false);
        })
        .catch((err) => {
          console.error('Failed to load risk scores:', err);
          setLoading(false);
        });
    }
  }, [riskScores]);

  const getRiskColor = (riskScore) => {
    if (riskScore < 20) return '#2ecc71'; // Green: Low
    if (riskScore < 40) return '#f39c12'; // Orange: Moderate
    if (riskScore < 60) return '#e74c3c'; // Red: High
    return '#8b0000'; // Dark Red: Very High
  };

  const getRiskLabel = (riskScore) => {
    if (riskScore < 20) return 'Low';
    if (riskScore < 40) return 'Moderate';
    if (riskScore < 60) return 'High';
    return 'Very High';
  };

  if (loading) {
    return (
      <div className="w-full h-96 flex items-center justify-center bg-gray-100 rounded-lg">
        <div className="text-gray-600">Loading seismic risk map...</div>
      </div>
    );
  }

  return (
    <div className="w-full rounded-lg overflow-hidden border border-gray-200">
      <MapContainer
        center={[45, 15]}
        zoom={4}
        style={{ height: '500px', width: '100%' }}
      >
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {scores.map((score) => (
          <RiskHexagon
            key={score.h3_cell}
            score={score}
            color={getRiskColor(score.risk_score)}
            label={getRiskLabel(score.risk_score)}
            onClick={() => onCellClick?.(score)}
          />
        ))}
      </MapContainer>

      {/* Legend */}
      <div className="p-4 bg-white border-t border-gray-200">
        <div className="text-sm font-semibold mb-3">Risk Levels</div>
        <div className="grid grid-cols-2 gap-2">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded" style={{ backgroundColor: '#2ecc71' }} />
            <span className="text-xs">Low (0-20)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded" style={{ backgroundColor: '#f39c12' }} />
            <span className="text-xs">Moderate (20-40)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded" style={{ backgroundColor: '#e74c3c' }} />
            <span className="text-xs">High (40-60)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded" style={{ backgroundColor: '#8b0000' }} />
            <span className="text-xs">Very High (60+)</span>
          </div>
        </div>
      </div>
    </div>
  );
};

const RiskHexagon = ({ score, color, label, onClick }) => {
  const CircleMarker = ({ center, radius, color }) => {
    const L = require('leaflet');
    React.useEffect(() => {
      // Custom circle marker representing H3 cell
    }, []);
    return null;
  };

  return (
    <Popup position={[score.latitude, score.longitude]}>
      <div className="p-3 w-64">
        <div className="font-semibold mb-2">{score.h3_cell}</div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <div className="text-gray-600">Risk Score</div>
            <div className="font-bold text-lg" style={{ color }}>
              {score.risk_score}/100
            </div>
          </div>
          <div>
            <div className="text-gray-600">Level</div>
            <div className="font-bold">{label}</div>
          </div>
        </div>
        <div className="mt-3 border-t pt-3">
          <div className="text-xs text-gray-600 mb-2">Damage Probability</div>
          <div className="text-sm font-semibold">
            {(score.damage_probability * 100).toFixed(1)}%
          </div>
        </div>
        <div className="mt-2">
          <div className="text-xs text-gray-600 mb-2">Aftershock Probability</div>
          <div className="text-xs space-y-1">
            <div>24h: {(score.aftershock_24h * 100).toFixed(1)}%</div>
            <div>72h: {(score.aftershock_72h * 100).toFixed(1)}%</div>
            <div>7d: {(score.aftershock_7d * 100).toFixed(1)}%</div>
          </div>
        </div>
        <button
          onClick={onClick}
          className="mt-3 w-full px-3 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700"
        >
          View Details
        </button>
      </div>
    </Popup>
  );
};

export default SeismicRiskMap
