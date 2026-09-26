"""FX as a multi-source foundation: every source's rates side by side, plus rates fixed by law.

  * fx_rates.basis — what kind of figure a row is: 'reference_daily' (ECB), 'month_end' / 'period_average' (IMF
    monthly), 'seed' (setup rows). The key becomes (ccy, rate_date, source, basis), so the ECB and IMF figures for the
    same currency and date live side by side and can be compared; which one a conversion uses is decided by the source
    registry (services/reference/fx_sources.py), never by whichever row happened to be written last.
  * fx_pegs — rates fixed by law or treaty, with their legal basis and validity: the CFA and similar euro pegs, the
    Bosnian currency board, and the irrevocable conversion rates of the currencies the euro replaced (so a legacy
    DEM / HRK / BGN amount converts exactly). These are exact; no feed can improve on them.

Revision ID: fx_multisource_20260926
Revises: intake_sftp_keys_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fx_multisource_20260926"
down_revision: Union[str, None] = "intake_sftp_keys_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EMU = "Council Regulation (EC) No 2866/98 and its amendments — irrevocable euro conversion rate"
PEGS = [
    # currency, units per EUR, valid from, valid to, legal basis
    ("XOF", "655.957", "1999-01-01", None, "Council Decision 98/683/EC — CFA franc (UEMOA) fixed parity with the euro"),
    ("XAF", "655.957", "1999-01-01", None, "Council Decision 98/683/EC — CFA franc (CEMAC) fixed parity with the euro"),
    ("KMF", "491.96775", "1999-01-01", None, "Council Decision 98/683/EC — Comorian franc fixed parity with the euro"),
    ("CVE", "110.265", "1999-01-01", None, "Council Decision 98/744/EC — Cape Verde escudo fixed parity with the euro"),
    ("XPF", "119.331742", "1999-01-01", None, "CFP franc fixed at 1,000 XPF = 8.38 EUR (Protocol (No 18) TFEU; French law)"),
    ("BAM", "1.95583", "1999-01-01", None, "Currency board: Law on the Central Bank of Bosnia and Herzegovina"),
    ("ATS", "13.7603", "1999-01-01", None, _EMU), ("BEF", "40.3399", "1999-01-01", None, _EMU),
    ("DEM", "1.95583", "1999-01-01", None, _EMU), ("ESP", "166.386", "1999-01-01", None, _EMU),
    ("FIM", "5.94573", "1999-01-01", None, _EMU), ("FRF", "6.55957", "1999-01-01", None, _EMU),
    ("IEP", "0.787564", "1999-01-01", None, _EMU), ("ITL", "1936.27", "1999-01-01", None, _EMU),
    ("LUF", "40.3399", "1999-01-01", None, _EMU), ("NLG", "2.20371", "1999-01-01", None, _EMU),
    ("PTE", "200.482", "1999-01-01", None, _EMU), ("GRD", "340.750", "2001-01-01", None, _EMU),
    ("SIT", "239.640", "2007-01-01", None, _EMU), ("CYP", "0.585274", "2008-01-01", None, _EMU),
    ("MTL", "0.429300", "2008-01-01", None, _EMU), ("SKK", "30.1260", "2009-01-01", None, _EMU),
    ("EEK", "15.6466", "2011-01-01", None, _EMU), ("LVL", "0.702804", "2014-01-01", None, _EMU),
    ("LTL", "3.45280", "2015-01-01", None, _EMU), ("HRK", "7.53450", "2023-01-01", None, _EMU),
    ("BGN", "1.95583", "2026-01-01", None, _EMU),
]


def upgrade() -> None:
    op.execute("ALTER TABLE fx_rates ADD COLUMN IF NOT EXISTS basis TEXT")
    op.execute("UPDATE fx_rates SET basis = CASE WHEN source = 'ecb' THEN 'reference_daily' ELSE 'seed' END WHERE basis IS NULL")
    op.execute("ALTER TABLE fx_rates ALTER COLUMN basis SET NOT NULL")
    op.execute("ALTER TABLE fx_rates DROP CONSTRAINT IF EXISTS fx_rates_pkey")
    op.execute("ALTER TABLE fx_rates ADD CONSTRAINT fx_rates_pkey PRIMARY KEY (ccy, rate_date, source, basis)")
    op.execute("""ALTER TABLE fx_rates ADD CONSTRAINT ck_fx_basis
                  CHECK (basis IN ('reference_daily', 'month_end', 'period_average', 'seed'))""")
    op.execute("ALTER TABLE fx_rates ALTER COLUMN source TYPE TEXT")
    op.execute("""
        CREATE TABLE IF NOT EXISTS fx_pegs (
            ccy            CHAR(3) NOT NULL,
            units_per_eur  NUMERIC(18, 8) NOT NULL,
            valid_from     DATE NOT NULL,
            valid_to       DATE,
            legal_basis    TEXT NOT NULL,
            PRIMARY KEY (ccy, valid_from),
            CONSTRAINT ck_peg_positive CHECK (units_per_eur > 0)
        )
    """)
    for ccy, rate, frm, to, basis in PEGS:
        op.execute(f"""INSERT INTO fx_pegs (ccy, units_per_eur, valid_from, valid_to, legal_basis)
                       VALUES ('{ccy}', {rate}, '{frm}', {f"'{to}'" if to else 'NULL'}, $${basis}$$)
                       ON CONFLICT (ccy, valid_from) DO NOTHING""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fx_pegs")
    op.execute("ALTER TABLE fx_rates DROP CONSTRAINT IF EXISTS ck_fx_basis")
    op.execute("ALTER TABLE fx_rates DROP CONSTRAINT IF EXISTS fx_rates_pkey")
    op.execute("DELETE FROM fx_rates WHERE basis <> 'reference_daily' AND source <> 'seed'")
    op.execute("ALTER TABLE fx_rates ADD CONSTRAINT fx_rates_pkey PRIMARY KEY (ccy, rate_date)")
    op.execute("ALTER TABLE fx_rates DROP COLUMN IF EXISTS basis")
