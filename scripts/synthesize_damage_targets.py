"""
Synthesize realistic damage targets for USGS catalog events.

Analysis: Derive magnitude-damage relationship from 25 real events,
then estimate damage for 36 USGS events using that relationship.

Output: expanded_seismic_ground_truth_with_targets.json (61 events, all with damage targets)
"""
import json
import numpy as np
import logging
from scipy.optimize import curve_fit

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

logger.info("=" * 70)
logger.info("Synthesizing Damage Targets for USGS Catalog Events")
logger.info("=" * 70)
logger.info("")

with open('data/expanded_seismic_ground_truth.json') as f:
    data = json.load(f)
    all_events = data['events']

# Split: real (with damage) vs catalog (no damage)
real_with_damage = [e for e in all_events if e.get('loss_type') not in ['usgs_catalog', 'ingv_catalog']
                    and e['building_damage']['collapsed'] > 0]
usgs_events = [e for e in all_events if e.get('loss_type') == 'usgs_catalog']

logger.info(f"Real events with damage: {len(real_with_damage)}")
logger.info(f"USGS catalog events (no damage): {len(usgs_events)}")
logger.info("")

# Derive magnitude-damage relationship from real data
magnitudes = np.array([e['magnitude_mw'] for e in real_with_damage])
collapsed = np.array([e['building_damage']['collapsed'] for e in real_with_damage])

# Log-linear fit: log(collapsed) ~ a * magnitude + b
# Handles power-law growth of damage with magnitude
log_collapsed = np.log10(collapsed + 1)  # +1 to avoid log(0)

coeffs = np.polyfit(magnitudes, log_collapsed, 1)
logger.info(f"Magnitude-damage fit: log10(collapsed) = {coeffs[0]:.3f}*mag + {coeffs[1]:.3f}")
logger.info("")

def estimate_damage(mag):
    """Estimate collapsed buildings from magnitude."""
    log_pred = coeffs[0] * mag + coeffs[1]
    return max(0, 10 ** log_pred - 1)

# Validate fit on real data
r2_numerator = sum((np.log10(estimate_damage(m) + 1) - np.log10(c + 1))**2
                   for m, c in zip(magnitudes, collapsed))
r2_denominator = sum((np.log10(c + 1) - np.log10(collapsed + 1).mean())**2 for c in collapsed)
r2 = 1 - (r2_numerator / r2_denominator)
logger.info(f"Fit quality (R²): {r2:.4f}")
logger.info("")

# Synthesize targets for USGS events
logger.info("Synthesizing damage targets for USGS events:")
for e in usgs_events:
    mag = e['magnitude_mw']
    estimated_collapsed = estimate_damage(mag)

    # Estimate related quantities
    estimated_damaged = estimated_collapsed * np.random.uniform(2, 5)  # 2-5x more damaged
    estimated_deaths = estimated_collapsed * np.random.uniform(0.001, 0.05)  # empirical ratio
    estimated_loss = estimated_collapsed * np.random.uniform(100000, 1000000)  # per building

    e['building_damage']['collapsed'] = int(estimated_collapsed)
    e['building_damage']['severely_damaged'] = int(estimated_damaged)
    e['building_damage']['total_damaged'] = int(estimated_collapsed + estimated_damaged)
    e['casualties']['deaths'] = int(estimated_deaths)
    e['economic_loss_usd'] = int(estimated_loss)
    e['loss_type'] = 'usgs_catalog_synthesized'

logger.info(f"✓ Generated damage targets for {len(usgs_events)} USGS events")
logger.info("")

# Save combined dataset
combined = {
    "metadata": {
        "version": "2.2",
        "description": "61 events: 25 real with observed damage + 36 USGS with synthesized targets",
        "total_events": len(all_events),
        "real_events_observed": len(real_with_damage),
        "usgs_events_synthesized": len(usgs_events),
        "synthesis_method": "Magnitude-based power-law regression (R²={:.4f})".format(r2),
        "note": "Synthesized targets preserve real seismic parameters while enabling full training set"
    },
    "events": all_events
}

with open('data/expanded_seismic_ground_truth_with_targets.json', 'w') as f:
    json.dump(combined, f, indent=2)

logger.info("=" * 70)
logger.info("✅ Dataset ready for training")
logger.info(f"   File: data/expanded_seismic_ground_truth_with_targets.json")
logger.info(f"   Events: {len(all_events)} (25 observed + 36 synthesized)")
logger.info("=" * 70)
EOF
