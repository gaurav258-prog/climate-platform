"""The UI standard (2026-10-16): every code a screen may name has customer words in its register, and the words
carry no internal names. The method parameters' short names are what a 'needs your input' box shows."""
from __future__ import annotations

import re

from services.money import params

INTERNAL = re.compile(r"\b[a-z]+_[a-z_]+\b|\bE\d{2,3}\b|\.json\b|\.py\b|/v1/|named gap|product owner", re.I)


def test_every_method_parameter_has_a_short_customer_name():
    for key, p in params.parameters().items():
        short = p.get("short")
        assert short, f"{key} has no short name"
        assert len(short.split()) <= 6, f"{key}: '{short}' is longer than six words"
        assert not INTERNAL.search(short), f"{key}: '{short}' carries an internal name"


def test_the_labels_endpoint_serves_every_method_parameter():
    from api.routers.meta import labels
    got = labels(ctx={})["method"]
    assert set(got) == set(params.parameters())
    assert got["method.at_risk_level"] == "Your at-risk threshold"
