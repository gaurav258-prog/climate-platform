"""Which country a United States postal state code lies in (ISO 3166-2:US: 50 states, 1 district, 6 outlying areas).

The 50 states and the District of Columbia are subdivisions of the United States (ISO 3166-1 'US'). The six outlying
areas — American Samoa, Guam, the Northern Mariana Islands, Puerto Rico, the United States Minor Outlying Islands and
the United States Virgin Islands — are ISO 3166-2:US subdivisions that also hold their own ISO 3166-1 codes (AS, GU, MP,
PR, UM, VI), and the UN M49 regions place them outside Northern America (data/reference/un_m49_regions.json: Caribbean,
Micronesia, Polynesia). A dataset's two-letter state field (FEMA's NFIP claims) is read to a country here, never by
matching it against country codes: 'CA' California is not Canada, 'DE' Delaware is not Germany (E325)."""
from __future__ import annotations

STATES_AND_DC: frozenset[str] = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})
OUTLYING_AREAS: frozenset[str] = frozenset({"AS", "GU", "MP", "PR", "UM", "VI"})


def country(code: str | None) -> str | None:
    """The ISO 3166-1 country of a US postal state code: 'US' for the 50 states and DC, the area's own code for an
    outlying area, None for a blank or unknown code (it cannot be placed)."""
    c = str(code or "").strip().upper()
    if c in STATES_AND_DC:
        return "US"
    return c if c in OUTLYING_AREAS else None
