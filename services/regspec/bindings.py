"""Where each framework's implementation declares how every row and column of its spec templates is filled.

The binding lives with the code that fills the template (so a change to one is reviewed with the other); this module
only finds it. A framework without a binding has not been moved onto the change route yet.
"""
from __future__ import annotations

from datetime import date


def binding_for(framework: str) -> dict | None:
    if framework == "bank_p3esg":                     # one binding per template, from the modules that fill them
        import services.regspec as R
        from services.governance import pillar3_gar, pillar3_grids, pillar3_other
        spec = R.governing(framework, period_end=date.today())
        return {**pillar3_grids.BINDING, **pillar3_gar.BINDING, **pillar3_other.BINDING,
                **(pillar3_other.tab_bindings(spec) if spec else {})}
    if framework == "sfdr_pai":
        from services.governance.sfdr_binding import BINDING
        return BINDING
    return None
