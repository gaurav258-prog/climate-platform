"""CRCS — the Continuous Regulatory Compliance Service: regulatory change detection.

The live engine is eurlex_detector (the official EU register, Cellar SPARQL, checked daily). The scrapers package
holds the news source; early_signals reads the regulators' feeds — signals only, never settled fact.
"""
