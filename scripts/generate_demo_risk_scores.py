#!/usr/bin/env python3
"""
Generate demo risk scores for the seismic map.
Populates the risk-scores endpoint with synthetic data for testing the enhanced UI.
"""

import json
import random
from datetime import datetime

# H3 cells covering major European seismic zones
EUROPEAN_H3_CELLS = [
    # Mediterranean region (highest risk)
    {"h3": "881c84d633fffff", "lat": 38.5, "lon": 14.0, "name": "Sicily"},
    {"h3": "881c84d6b3fffff", "lat": 39.5, "lon": 22.0, "name": "Greece"},
    {"h3": "881c84d553fffff", "lat": 37.5, "lon": 25.0, "name": "Turkey-Greece Border"},

    # Alpine region (moderate-high risk)
    {"h3": "881c84d3c3fffff", "lat": 45.0, "lon": 12.0, "name": "Italy Alps"},
    {"h3": "881c84d4a3fffff", "lat": 46.0, "lon": 7.0, "name": "Switzerland"},
    {"h3": "881c84d573fffff", "lat": 47.5, "lon": 13.0, "name": "Austria"},

    # Iberian Peninsula
    {"h3": "881c84d6a3fffff", "lat": 36.5, "lon": -3.5, "name": "Granada-Málaga"},
    {"h3": "881c84d433fffff", "lat": 37.0, "lon": -5.0, "name": "Southern Spain"},

    # Mid-Atlantic Ridge (offshore)
    {"h3": "881c84d5d3fffff", "lat": 37.0, "lon": -10.0, "name": "Azores"},
    {"h3": "881c84d4d3fffff", "lat": 64.0, "lon": -17.0, "name": "Iceland"},

    # Eastern Europe
    {"h3": "881c84d373fffff", "lat": 52.0, "lon": 18.0, "name": "Vrancea (Romania)"},
    {"h3": "881c84d6e3fffff", "lat": 48.0, "lon": 22.0, "name": "Carpathians"},

    # Broader European coverage (lower risk)
    {"h3": "881c84d303fffff", "lat": 51.0, "lon": 0.0, "name": "UK"},
    {"h3": "881c84d3e3fffff", "lat": 50.0, "lon": 8.0, "name": "France"},
    {"h3": "881c84d4e3fffff", "lat": 48.5, "lon": 16.0, "name": "Central Europe"},

    # Northern regions (very low risk)
    {"h3": "881c84d2b3fffff", "lat": 60.0, "lon": 18.0, "name": "Scandinavia"},
    {"h3": "881c84d2c3fffff", "lat": 56.0, "lon": 24.0, "name": "Baltic"},
]

def generate_risk_scores():
    """Generate synthetic risk scores with realistic distribution."""
    scores = []

    for i, cell_info in enumerate(EUROPEAN_H3_CELLS):
        # Risk score distribution:
        # - Mediterranean: 40-80 (high)
        # - Alpine: 30-60 (moderate-high)
        # - Others: 5-35 (low-moderate)

        base_risk = {
            "Sicily": 75,
            "Greece": 70,
            "Turkey-Greece Border": 80,
            "Italy Alps": 55,
            "Switzerland": 45,
            "Austria": 40,
            "Granada-Málaga": 50,
            "Southern Spain": 45,
            "Azores": 35,
            "Iceland": 38,
            "Vrancea (Romania)": 60,
            "Carpathians": 35,
            "UK": 8,
            "France": 15,
            "Central Europe": 20,
            "Scandinavia": 5,
            "Baltic": 10,
        }

        base = base_risk.get(cell_info["name"], 20)
        # Add some randomness
        risk_score = max(0, min(100, base + random.randint(-10, 15)))

        score = {
            "h3_cell": cell_info["h3"],
            "latitude": cell_info["lat"],
            "longitude": cell_info["lon"],
            "region_name": cell_info["name"],
            "risk_score": risk_score,
            "damage_probability": max(0.0, min(1.0, risk_score / 100.0 * random.uniform(0.6, 1.0))),
            "aftershock_24h": max(0.0, min(1.0, risk_score / 200.0 * random.uniform(0.5, 1.0))),
            "aftershock_72h": max(0.0, min(1.0, risk_score / 150.0 * random.uniform(0.6, 1.0))),
            "aftershock_7d": max(0.0, min(1.0, risk_score / 100.0 * random.uniform(0.7, 1.0))),
            "computed_at": datetime.utcnow().isoformat() + "+00:00"
        }
        scores.append(score)

    return {
        "scores": scores,
        "count": len(scores),
        "timestamp": datetime.utcnow().isoformat() + "+00:00"
    }

if __name__ == "__main__":
    data = generate_risk_scores()

    # Save to file for manual inspection
    with open("/tmp/demo_risk_scores.json", "w") as f:
        json.dump(data, f, indent=2)

    print("✅ Generated demo risk scores")
    print(f"📊 {len(data['scores'])} cells with risk data")
    print("💾 Saved to: /tmp/demo_risk_scores.json")
    print("\nSample:")
    for score in data['scores'][:3]:
        print(f"  {score['region_name']}: risk={score['risk_score']}/100, damage={score['damage_probability']:.0%}")
