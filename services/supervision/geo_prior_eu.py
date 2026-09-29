"""EU member states as coded in the Eurostat GISCO country layer (EL = Greece) — from the one reference module."""
from __future__ import annotations

from services.reference.eu_membership import members_gisco

EU_MEMBERS = members_gisco()
