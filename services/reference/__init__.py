"""Reference-data layer.

Turns a bare ISIN (all a client has to give us) into an auditable issuer →
security → footprint → emissions graph, built entirely from OPEN data:

  * GLEIF (gleif.py)        — issuer identity + ISIN→LEI, free & keyless
  * facilities (later)      — Climate TRACE / GEM / OSM footprints
  * emissions (later)       — disclosed, else estimated with the method disclosed

Every record is stamped with source + vintage; every ISIN resolution is logged.
Nothing is fabricated: unmatched ISINs and estimated figures are surfaced, not
hidden. This is build-order step 1 of the asset-management beachhead — the layer
that makes "onboard with ISINs alone" real.
"""
