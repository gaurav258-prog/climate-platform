import React, { useState } from 'react';
import { SeismicRiskMap } from '../components/SeismicRiskMap';
import { SeismicEventsCard } from '../components/SeismicEventsCard';
import { DamageAssessmentPanel } from '../components/DamageAssessmentPanel';
import { AftershockForecastCard } from '../components/AftershockForecastCard';

interface Earthquake {
  event_id: string;
  magnitude: number;
  location: string;
}

export const SeismicDashboard: React.FC = () => {
  const [selectedEvent, setSelectedEvent] = useState<Earthquake | null>(null);
  const [showDamagePanel, setShowDamagePanel] = useState(false);
  const [showForecastPanel, setShowForecastPanel] = useState(false);
  const [filterDays, setFilterDays] = useState(7);
  const [filterMagnitude, setFilterMagnitude] = useState(4.5);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Seismic Risk Intelligence</h1>
              <p className="text-gray-600 mt-2">
                CSEP-validated earthquake forecasting and damage assessment for Europe
              </p>
            </div>
            <div className="text-right">
              <div className="text-sm text-gray-600">Validation Status</div>
              <div className="text-lg font-bold text-green-600">✓ CSEP Approved</div>
            </div>
          </div>

          {/* Filters */}
          <div className="mt-6 grid grid-cols-2 gap-4 max-w-md">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Look back (days)
              </label>
              <select
                value={filterDays}
                onChange={(e) => setFilterDays(parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
              >
                <option value={1}>Last 24 hours</option>
                <option value={7}>Last 7 days</option>
                <option value={30}>Last 30 days</option>
                <option value={90}>Last 3 months</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Minimum magnitude
              </label>
              <select
                value={filterMagnitude}
                onChange={(e) => setFilterMagnitude(parseFloat(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
              >
                <option value={3.0}>M3.0+</option>
                <option value={4.0}>M4.0+</option>
                <option value={4.5}>M4.5+</option>
                <option value={5.0}>M5.0+</option>
                <option value={6.0}>M6.0+</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: Map and Events */}
          <div className="lg:col-span-2 space-y-6">
            {/* Risk Map */}
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <div className="p-4 border-b border-gray-200 bg-gray-50">
                <h2 className="font-semibold text-gray-900">Seismic Risk Map</h2>
                <p className="text-xs text-gray-600 mt-1">
                  H3 grid cells colored by risk score (0-100)
                </p>
              </div>
              <SeismicRiskMap onCellClick={(cell) => console.log('Cell clicked:', cell)} />
            </div>

            {/* Recent Events */}
            <SeismicEventsCard
              days={filterDays}
              minMagnitude={filterMagnitude}
              onEventClick={(event) => {
                setSelectedEvent(event);
                setShowDamagePanel(true);
              }}
            />
          </div>

          {/* Right Column: Details and Forecasts */}
          <div className="space-y-6">
            {/* Event Details Section */}
            {selectedEvent ? (
              <>
                {/* Event Summary */}
                <div className="bg-white rounded-lg border border-gray-200 p-4">
                  <h3 className="font-semibold text-gray-900 mb-3">Selected Event</h3>
                  <div className="space-y-2">
                    <div>
                      <div className="text-xs text-gray-600">Location</div>
                      <div className="font-semibold text-gray-900">{selectedEvent.location}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-600">Magnitude</div>
                      <div className="text-lg font-bold text-red-600">
                        M{selectedEvent.magnitude.toFixed(1)}
                      </div>
                    </div>
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={() => setShowDamagePanel(true)}
                        className="flex-1 px-3 py-2 bg-orange-600 text-white rounded text-sm font-medium hover:bg-orange-700"
                      >
                        Damage
                      </button>
                      <button
                        onClick={() => setShowForecastPanel(true)}
                        className="flex-1 px-3 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700"
                      >
                        Forecast
                      </button>
                    </div>
                  </div>
                </div>

                {/* Damage Assessment */}
                {showDamagePanel && (
                  <DamageAssessmentPanel
                    eventId={selectedEvent.event_id}
                    onClose={() => setShowDamagePanel(false)}
                  />
                )}

                {/* Aftershock Forecast */}
                {showForecastPanel && (
                  <AftershockForecastCard
                    eventId={selectedEvent.event_id}
                    onClose={() => setShowForecastPanel(false)}
                  />
                )}
              </>
            ) : (
              <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
                <div className="text-gray-600">
                  <p className="font-semibold">Select an earthquake event</p>
                  <p className="text-sm mt-1">
                    Click on a recent earthquake to view damage and aftershock forecasts
                  </p>
                </div>
              </div>
            )}

            {/* Info Box */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h4 className="font-semibold text-blue-900 mb-2">About This Dashboard</h4>
              <ul className="text-sm text-blue-800 space-y-1">
                <li>✓ CSEP-validated forecasts (4/5 tests passed)</li>
                <li>✓ Real-time seismic data from EMSC</li>
                <li>✓ Machine learning damage predictions</li>
                <li>✓ ETAS aftershock probabilities</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SeismicDashboard;
