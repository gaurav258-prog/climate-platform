import React, { useEffect, useState } from 'react';

export const SeismicEventsCard = ({
  days = 7,
  minMagnitude = 4.5,
  onEventClick,
}) => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(
      `http://localhost:8000/seismic/events?days=${days}&min_magnitude=${minMagnitude}`
    )
      .then((res) => res.json())
      .then((data) => {
        setEvents(data.events);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load events:', err);
        setLoading(false);
      });
  }, [days, minMagnitude]);

  const getMagnitudeColor = (mag) => {
    if (mag < 5.0) return 'text-yellow-600';
    if (mag < 6.0) return 'text-orange-600';
    if (mag < 7.0) return 'text-red-600';
    return 'text-red-900';
  };

  const getMMIColor = (mmi) => {
    const level = mmi.charCodeAt(0);
    if (level < 70) return 'bg-green-100 text-green-800'; // I-IV
    if (level < 85) return 'bg-yellow-100 text-yellow-800'; // V-VI
    if (level < 88) return 'bg-orange-100 text-orange-800'; // VII
    return 'bg-red-100 text-red-800'; // VIII+
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="text-gray-600 text-center">Loading recent earthquakes...</div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="p-4 border-b border-gray-200 bg-gray-50">
        <h3 className="font-semibold text-gray-900">
          Recent Earthquakes ({events.length})
        </h3>
        <p className="text-xs text-gray-600 mt-1">
          Last {days} days, M≥{minMagnitude}
        </p>
      </div>

      <div className="divide-y divide-gray-200 max-h-96 overflow-y-auto">
        {events.length === 0 ? (
          <div className="p-4 text-center text-gray-600 text-sm">
            No earthquakes in this period
          </div>
        ) : (
          events.map((event) => (
            <button
              key={event.event_id}
              onClick={() => onEventClick?.(event)}
              className="w-full p-4 hover:bg-blue-50 transition text-left"
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="font-semibold text-gray-900 text-sm">
                    {event.location}
                  </div>
                  <div className="text-xs text-gray-600 mt-1">
                    {new Date(event.origin_time).toLocaleString()}
                  </div>
                </div>
                <div className="text-right">
                  <div className={`font-bold text-lg ${getMagnitudeColor(event.magnitude)}`}>
                    M{event.magnitude.toFixed(1)}
                  </div>
                  <div className="text-xs text-gray-600">{event.depth_km}km depth</div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 mt-3">
                <div>
                  <div className="text-xs text-gray-600">Deaths</div>
                  <div className="font-semibold text-sm">
                    {event.casualties.deaths.toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-600">Buildings</div>
                  <div className="font-semibold text-sm">
                    {event.building_damage.collapsed.toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-600">Intensity</div>
                  <div className={`text-xs font-semibold px-2 py-1 rounded ${getMMIColor(event.max_mmi)}`}>
                    {event.max_mmi}
                  </div>
                </div>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
};

export default SeismicEventsCard
