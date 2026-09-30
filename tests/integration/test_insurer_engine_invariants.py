"""The insurance engine on every insurer book in the database: warming never lowers the expected annual loss or the
1-in-200 annual loss (same simulated years under every scenario, every insured peril priced), and the simulated mean
reconciles to the sum of the policies' expected losses. What the ORSA climate analysis and the recovery stress stand on."""
import pytest
from sqlalchemy import text

from core.db.session import get_session

pytestmark = pytest.mark.integration
PATH = (("baseline", "current"), ("hot_house_3_5c", "2030"), ("hot_house_3_5c", "2050"), ("hot_house_3_5c", "2100"))


def test_warming_never_lowers_losses_and_the_mean_reconciles():
    from api.routers.insurance import build_disclosure_snapshot
    with get_session() as s:
        orgs = s.execute(text("SELECT org_id::text, name FROM organizations WHERE type = 'insurer'")).all()
        assert orgs
        for org_id, name in orgs:
            eal, aep = [], []
            for sc, hz in PATH:
                snap = build_disclosure_snapshot(s, org_id, sc, hz)
                cat = snap["rollup"]["catastrophe"] or {}
                if not cat.get("available"):
                    break
                assert cat["mean_reconciles"], (name, sc, hz)
                eal.append(snap["rollup"]["total_expected_annual_loss_eur"])
                aep.append(cat["aep_eur"]["rp_200"])
            assert eal == sorted(eal) and aep == sorted(aep), (name, eal, aep)
