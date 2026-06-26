"""
Augment seismic ground truth with synthetic earthquake events.

Combines 25 real historical events with 75 synthetic events generated from
realistic distributions (Gutenberg-Richter magnitude-frequency, depth distributions,
PGA-magnitude relationships, building vulnerability profiles).

Output: expanded_seismic_ground_truth.json (100 total events)
"""
import json
import numpy as np
import logging
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

def load_real_events():
    """Load the 25 real historical events."""
    with open('data/seismic_ground_truth.json', 'r') as f:
        data = json.load(f)
    return data['events']

def generate_synthetic_events(n_events=75):
    """Generate synthetic earthquake events using realistic distributions."""
    events = []

    # Regional characteristics
    regions = [
        {'name': 'Italy', 'lat_range': (42, 44), 'lon_range': (12, 14), 'hazard': 6.5},
        {'name': 'Greece', 'lat_range': (37, 39), 'lon_range': (21, 24), 'hazard': 7.0},
        {'name': 'Turkey', 'lat_range': (36, 40), 'lon_range': (26, 36), 'hazard': 7.2},
        {'name': 'Balkans', 'lat_range': (42, 46), 'lon_range': (15, 22), 'hazard': 6.3},
        {'name': 'Spain-Portugal', 'lat_range': (36, 44), 'lon_range': (-10, -3), 'hazard': 6.0},
    ]

    for i in range(n_events):
        # Sample region
        region = regions[i % len(regions)]

        # Gutenberg-Richter: magnitude distribution (more small events)
        # P(M > m) = 10^(-b(m - m_min)) where b ≈ 1.0
        # Sample: M = m_min + rand / b (exponential)
        m_min = 4.5
        b = 1.0
        magnitude = m_min + np.random.exponential(1.0 / b)
        magnitude = np.clip(magnitude, 4.5, 8.5)

        # Depth distribution (shallow earthquakes more damaging)
        # Exponential distribution, mean ~20km
        depth = np.random.exponential(20) + 5
        depth = np.clip(depth, 5, 100)

        # PGA scales with magnitude and inversely with distance
        # Use Wells & Coppersmith: log10(a) = 0.3*Mw + 3.6 (at 10km)
        pga_base = 10 ** (0.3 * magnitude + 3.6 - 2)  # Reduced for distance
        pga = pga_base * (1 + np.random.normal(0, 0.2))
        pga = np.clip(pga, 0.1, 3.0)

        # Casualties scale with magnitude and population density
        # Baseline: exp(magnitude - 5) * random_factor
        deaths_base = np.exp(magnitude - 5.0) * 100
        deaths = int(deaths_base * np.random.lognormal(0, 1.2))
        deaths = np.clip(deaths, 0, 500000)

        injured = int(deaths * np.random.uniform(0.5, 3.0))
        displaced = int(deaths * np.random.uniform(2, 10))

        # Building damage scales with magnitude, depth, building quality
        # Shallow + high magnitude = more damage
        depth_factor = 1.0 - (depth / 150)  # Normalized by ~max depth
        mag_factor = (magnitude - 4.5) / 4.0  # Normalized by ~max usable magnitude

        collapsed_base = (10 ** (magnitude - 1)) * depth_factor
        collapsed = int(collapsed_base * np.random.uniform(0.5, 2.0))
        collapsed = np.clip(collapsed, 0, 1000000)

        damaged = int(collapsed * np.random.uniform(3, 10))

        # Economic loss: power-law with magnitude
        economic_loss = (10 ** (magnitude * 1.5 - 4)) * 1e6 * np.random.lognormal(0, 0.8)
        economic_loss = np.clip(economic_loss, 0, 200e9)

        # Location
        lat = np.random.uniform(region['lat_range'][0], region['lat_range'][1])
        lon = np.random.uniform(region['lon_range'][0], region['lon_range'][1])

        # MMI intensity (simplified: scales with magnitude)
        max_mmi_map = {4.5: 'V', 5.5: 'VI', 6.0: 'VII', 6.5: 'VIII', 7.0: 'IX', 7.5: 'X', 8.0: 'XI'}
        max_mmi = 'VI'
        for mag_threshold in sorted(max_mmi_map.keys()):
            if magnitude >= mag_threshold:
                max_mmi = max_mmi_map[mag_threshold]

        # Generate event
        event = {
            "event_id": f"synthetic_{i:04d}_{datetime.now().strftime('%Y%m%d')}",
            "name": f"Synthetic {region['name']} M{magnitude:.1f}",
            "magnitude_mw": round(magnitude, 2),
            "magnitude_local": None,
            "mag_type": "Mw",
            "location": f"Synthetic - {region['name']}",
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "depth_km": round(depth, 1),
            "origin_time_utc": (datetime(2020, 1, 1) + timedelta(days=i * 10)).isoformat() + "Z",
            "casualties": {
                "deaths": deaths,
                "injured": injured,
                "missing": 0,
                "displaced": displaced
            },
            "economic_loss_usd": int(economic_loss),
            "loss_year": 2020 + (i % 5),
            "loss_type": "synthetic",
            "building_damage": {
                "collapsed": collapsed,
                "severely_damaged": int(collapsed * 2.5),
                "total_damaged": int(collapsed * 5)
            },
            "max_mmi": max_mmi,
            "max_pga_g": round(pga, 3),
            "sources": ["synthetic_augmentation"]
        }

        events.append(event)

    return events

def merge_datasets(real_events, synthetic_events):
    """Merge real and synthetic events into expanded dataset."""
    merged = {
        "metadata": {
            "version": "2.0",
            "date_created": datetime.now().isoformat(),
            "description": "Augmented earthquake ground truth: 25 real events + 75 synthetic events",
            "total_events": len(real_events) + len(synthetic_events),
            "real_events": len(real_events),
            "synthetic_events": len(synthetic_events),
            "data_sources": [
                "USGS Earthquake Hazards Program",
                "National Geological Services",
                "World Bank Disaster Assessments",
                "Synthetic event generation (Gutenberg-Richter, Wells & Coppersmith)"
            ]
        },
        "events": real_events + synthetic_events
    }
    return merged

def main():
    logger.info("")
    logger.info("=" * 70)
    logger.info("  Seismic Ground Truth Dataset Augmentation")
    logger.info("=" * 70)
    logger.info("")

    # Load real events
    logger.info("[AUGMENT] loading 25 real historical events...")
    real_events = load_real_events()
    logger.info(f"[AUGMENT] ✓ {len(real_events)} real events loaded")

    # Generate synthetic events
    logger.info("[AUGMENT] generating 75 synthetic events...")
    synthetic_events = generate_synthetic_events(n_events=75)
    logger.info(f"[AUGMENT] ✓ {len(synthetic_events)} synthetic events generated")

    # Merge datasets
    logger.info("[AUGMENT] merging datasets...")
    merged = merge_datasets(real_events, synthetic_events)
    logger.info(f"[AUGMENT] ✓ Merged: {merged['metadata']['total_events']} total events")

    # Save expanded dataset
    logger.info("[AUGMENT] saving expanded ground truth...")
    with open('data/expanded_seismic_ground_truth.json', 'w') as f:
        json.dump(merged, f, indent=2)
    logger.info("[AUGMENT] ✓ Saved to data/expanded_seismic_ground_truth.json")

    logger.info("")
    logger.info("=" * 70)
    logger.info(f"  Augmentation Complete: 100 total events (25 real + 75 synthetic)")
    logger.info("=" * 70)
    logger.info("")

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
