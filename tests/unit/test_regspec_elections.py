"""Every transitional option a specification declares is a governed election the organisation can actually make: the
switch exists in calc_settings, the value that changes the governing version is allowed, and the default leaves the
version as it is (the option is the undertaking's choice, never the platform's)."""
from __future__ import annotations

import services.regspec as R
from services.calc_settings import INTERPRETATION_SCHEMA as SWITCHES


def test_every_transitional_option_is_an_election_the_organisation_can_make():
    seen = 0
    for fw in R.frameworks():
        for v in R.versions(fw):
            opt = v.get("transitional_option")
            if not opt:
                continue
            seen += 1
            sw = SWITCHES.get(opt["switch"])
            assert sw, f"{fw} {v['version']}: switch '{opt['switch']}' is not a governed setting"
            assert opt["elected_value"] in sw["allowed"], (fw, v["version"])
            assert sw["default"] != opt["elected_value"], f"{fw} {v['version']}: the option must not be on by default"
            assert opt["then_governed_by"] in {x["version"] for x in R.versions(fw)}, (fw, v["version"])
    assert seen >= 2          # Taxonomy 2026/73 Art. 4 and ESRS 2026/1563 Art. 2
