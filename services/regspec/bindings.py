"""Where each framework's implementation declares how every row and column of its spec templates is filled.

The binding lives with the code that fills the template (so a change to one is reviewed with the other); this module
only finds it. A framework without a binding has not been moved onto the change route yet.
"""
from __future__ import annotations


def binding_for(framework: str) -> dict | None:
    if framework == "bank_p3esg":
        from services.governance.pillar3_grids import BINDING
        return BINDING
    if framework == "sfdr_pai":
        from services.governance.sfdr_binding import BINDING
        return BINDING
    return None
