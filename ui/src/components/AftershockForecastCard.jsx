import React, { useEffect, useState } from 'react';

export const AftershockForecastCard = ({ eventId, onClose }) => {
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(!!eventId);
  const [error, setError] = useState<string | null>(null);
  const [selectedWindow, setSelectedWindow] = useState('24h');

  useEffect(() => {
    if (eventId) {
      fetch(`http://localhost:8000/seismic/aftershock-forecast?event_id=${eventId}`)
        .then((res) => res.json())
        .then((data) => {
          setForecast(data);
          setLoading(false);
        })
        .catch((err) => {
          setError('Failed to load aftershock forecast');
          setLoading(false);
        });
    }
  }, [eventId]);

  if (!eventId) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
        <div className="text-gray-600">Select an event to view aftershock forecast</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
        <div className="text-gray-600">Loading aftershock forecast...</div>
      </div>
    );
  }

  if (error || !forecast) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
        <div className="text-red-600">{error || 'No forecast available'}</div>
      </div>
    );
  }

  const activeWindow = forecast.forecast_windows.find((w) => w.window === selectedWindow);

  const getProbabilityColor = (prob) => {
    if (prob < 0.05) return 'text-green-600';
    if (prob < 0.15) return 'text-yellow-600';
    if (prob < 0.3) return 'text-orange-600';
    return 'text-red-600';
  };

  const getProbabilityBg = (prob) => {
    if (prob < 0.05) return 'bg-green-50';
    if (prob < 0.15) return 'bg-yellow-50';
    if (prob < 0.3) return 'bg-orange-50';
    return 'bg-red-50';
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="p-4 border-b border-gray-200 bg-gradient-to-r from-purple-50 to-blue-50 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">ETAS Aftershock Forecast</h3>
          <p className="text-xs text-gray-600 mt-1">
            M{forecast.mainshock.magnitude.toFixed(1)} mainshock
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        )}
      </div>

      <div className="p-6">
        {/* Window Selector */}
        <div className="flex gap-2 mb-6">
          {['24h', '72h', '7d'].map((window) => (
            <button
              key={window}
              onClick={() => setSelectedWindow(window)}
              className={`flex-1 px-4 py-2 rounded font-medium text-sm transition ${
                selectedWindow === window
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {window === '24h' ? '24 Hours' : window === '72h' ? '3 Days' : '7 Days'}
            </button>
          ))}
        </div>

        {activeWindow && (
          <>
            {/* Probability */}
            <div className={`p-4 rounded-lg mb-6 ${getProbabilityBg(activeWindow.probability)}`}>
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-semibold text-gray-700">Aftershock Probability</span>
                <span className={`text-2xl font-bold ${getProbabilityColor(activeWindow.probability)}`}>
                  {(activeWindow.probability * 100).toFixed(1)}%
                </span>
              </div>
              <div className="mt-3 w-full bg-gray-300 rounded-full h-2.5">
                <div
                  className="h-2.5 rounded-full transition-all bg-blue-600"
                  style={{ width: `${Math.min(activeWindow.probability * 100, 100)}%` }}
                />
              </div>
            </div>

            {/* Expected Aftershocks */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="p-3 bg-blue-50 rounded-lg">
                <div className="text-xs text-gray-600 font-medium">Expected Aftershocks</div>
                <div className="text-2xl font-bold text-blue-600 mt-1">
                  {activeWindow.expected_aftershock_count}
                </div>
              </div>
              <div className="p-3 bg-indigo-50 rounded-lg">
                <div className="text-xs text-gray-600 font-medium">Magnitude Range</div>
                <div className="text-sm font-bold text-indigo-600 mt-1">
                  M{activeWindow.expected_magnitude_range[0].toFixed(1)} —{' '}
                  {activeWindow.expected_magnitude_range[1].toFixed(1)}
                </div>
              </div>
            </div>

            {/* Most Probable Region */}
            <div className="mb-6 border-t pt-6">
              <h4 className="font-semibold text-gray-900 mb-3">Most Probable Region</h4>
              <div className="bg-gray-50 p-4 rounded-lg space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-gray-600">Latitude</span>
                  <span className="font-semibold">
                    {activeWindow.most_probable_region.latitude.toFixed(2)}°
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-600">Longitude</span>
                  <span className="font-semibold">
                    {activeWindow.most_probable_region.longitude.toFixed(2)}°
                  </span>
                </div>
                <div className="flex items-center justify-between pt-2 border-t">
                  <span className="text-gray-600">Radius</span>
                  <span className="font-semibold">
                    ±{Math.round(activeWindow.most_probable_region.radius_km)} km
                  </span>
                </div>
              </div>
            </div>

            {/* Metadata */}
            <div className="border-t pt-4 space-y-2 text-xs text-gray-600">
              <div className="flex items-center justify-between">
                <span>Methodology:</span>
                <span className="font-semibold text-gray-900">ETAS</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Validation:</span>
                <span className="font-semibold text-gray-900">CSEP R²=0.66</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default AftershockForecastCard
