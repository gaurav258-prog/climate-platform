import React, { useEffect, useState } from 'react';

interface DamageAssessment {
  event_id: string;
  magnitude: number;
  location: string;
  damage_probability: number;
  building_damage: {
    collapsed: number;
    severely_damaged: number;
    total_damaged: number;
  };
  casualties: {
    deaths: number;
    injured: number;
    displaced: number;
  };
  economic_loss_usd: number;
  assessment_confidence: string;
  assessed_at: string;
}

interface DamageAssessmentPanelProps {
  eventId?: string;
  onClose?: () => void;
}

export const DamageAssessmentPanel: React.FC<DamageAssessmentPanelProps> = ({
  eventId,
  onClose,
}) => {
  const [assessment, setAssessment] = useState<DamageAssessment | null>(null);
  const [loading, setLoading] = useState(!!eventId);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (eventId) {
      fetch(`http://localhost:8000/seismic/damage-assessments?event_id=${eventId}`)
        .then((res) => res.json())
        .then((data) => {
          if (data.assessments.length > 0) {
            setAssessment(data.assessments[0]);
          }
          setLoading(false);
        })
        .catch((err) => {
          setError('Failed to load damage assessment');
          setLoading(false);
        });
    }
  }, [eventId]);

  if (!eventId) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
        <div className="text-gray-600">Select an event to view damage assessment</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
        <div className="text-gray-600">Loading damage assessment...</div>
      </div>
    );
  }

  if (error || !assessment) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
        <div className="text-red-600">{error || 'No assessment available'}</div>
      </div>
    );
  }

  const getDamageColor = (probability: number): string => {
    if (probability < 0.2) return 'text-green-600';
    if (probability < 0.5) return 'text-yellow-600';
    if (probability < 0.8) return 'text-orange-600';
    return 'text-red-600';
  };

  const getConfidenceColor = (): string => {
    if (assessment.assessment_confidence.includes('High')) return 'bg-green-100 text-green-800';
    if (assessment.assessment_confidence.includes('Medium')) return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-800';
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="p-4 border-b border-gray-200 bg-gradient-to-r from-red-50 to-orange-50 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">Damage Assessment</h3>
          <p className="text-xs text-gray-600 mt-1">{assessment.location}</p>
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
        {/* Damage Probability */}
        <div className="mb-6">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-sm font-semibold text-gray-700">Damage Probability</span>
            <span className={`text-2xl font-bold ${getDamageColor(assessment.damage_probability)}`}>
              {(assessment.damage_probability * 100).toFixed(1)}%
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${
                assessment.damage_probability < 0.3
                  ? 'bg-green-500'
                  : assessment.damage_probability < 0.6
                  ? 'bg-yellow-500'
                  : 'bg-red-500'
              }`}
              style={{ width: `${assessment.damage_probability * 100}%` }}
            />
          </div>
        </div>

        {/* Building Damage */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="p-3 bg-red-50 rounded-lg">
            <div className="text-xs text-gray-600 font-medium">Collapsed</div>
            <div className="text-lg font-bold text-red-600 mt-1">
              {assessment.building_damage.collapsed.toLocaleString()}
            </div>
          </div>
          <div className="p-3 bg-orange-50 rounded-lg">
            <div className="text-xs text-gray-600 font-medium">Severely Damaged</div>
            <div className="text-lg font-bold text-orange-600 mt-1">
              {assessment.building_damage.severely_damaged.toLocaleString()}
            </div>
          </div>
          <div className="p-3 bg-yellow-50 rounded-lg">
            <div className="text-xs text-gray-600 font-medium">Total Affected</div>
            <div className="text-lg font-bold text-yellow-600 mt-1">
              {assessment.building_damage.total_damaged.toLocaleString()}
            </div>
          </div>
        </div>

        {/* Casualties */}
        <div className="mb-6 border-t pt-6">
          <h4 className="font-semibold text-gray-900 mb-3">Humanitarian Impact</h4>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-gray-600">Deaths</div>
              <div className="text-xl font-bold text-red-600 mt-1">
                {assessment.casualties.deaths.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-600">Injured</div>
              <div className="text-xl font-bold text-orange-600 mt-1">
                {assessment.casualties.injured.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-600">Displaced</div>
              <div className="text-xl font-bold text-yellow-600 mt-1">
                {assessment.casualties.displaced.toLocaleString()}
              </div>
            </div>
          </div>
        </div>

        {/* Economic Loss */}
        <div className="mb-6 border-t pt-6">
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-semibold text-gray-700">Economic Loss</span>
            <span className="text-2xl font-bold text-gray-900">
              ${(assessment.economic_loss_usd / 1e9).toFixed(2)}B
            </span>
          </div>
          <p className="text-xs text-gray-600 mt-2">
            {(assessment.economic_loss_usd / 1e6).toFixed(0)}M USD
          </p>
        </div>

        {/* Confidence & Assessment Date */}
        <div className="border-t pt-4 flex items-center justify-between">
          <span className={`px-3 py-1 rounded text-xs font-semibold ${getConfidenceColor()}`}>
            {assessment.assessment_confidence}
          </span>
          <span className="text-xs text-gray-600">
            {new Date(assessment.assessed_at).toLocaleDateString()}
          </span>
        </div>
      </div>
    </div>
  );
};
