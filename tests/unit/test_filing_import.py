"""Prior-filings extractor — reading a filed report into its reported lines (services.ingest.filing_import).
Covers number/unit parsing, cross-framework keyword mapping (incl. the ordering traps), and end-to-end
extraction from a synthetic Excel and an inline-XBRL document (scale/sign transforms)."""
import io

import openpyxl
import pytest

from services.ingest.filing_import import detect_format, extract, match_datapoint, parse_number


def test_parse_number_units_and_separators():
    assert parse_number("1,240")[0] == 1240              # thousands comma
    assert parse_number("1,594,585")[0] == 1594585       # multi-group thousands comma
    assert parse_number("18.4%") == (18.4, "%")
    assert parse_number("€412,900")[0] == 412900.0
    assert parse_number("412,9")[0] == 412.9             # european decimal comma
    assert parse_number("")[0] is None and parse_number(None)[0] is None


def test_mapping_ordering_traps():
    # 'aligned' must beat 'eligible'; 'transition' must beat gar-'alignment'; 'emissions to water' -> nature
    assert match_datapoint("bank_p3esg", "Green Asset Ratio aligned share") == "p3_gar_aligned"
    assert match_datapoint("bank_tcfd", "Transition alignment distance NZE2050") == "transition_risk"
    assert match_datapoint("sfdr_pai", "PAI 8 emissions to water") == "pai_nature"
    assert match_datapoint("csrd_e1", "E1-6 GHG emissions Scope 1") == "e1_ghg"
    assert match_datapoint("bank_p3esg", "some proprietary metric") is None   # unmatched, never guessed


def test_extract_excel_maps_and_reads_values():
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Template 5"
    ws.append(["Line", "Value"])
    ws.append(["Financed emissions Scope 3 (tCO2e)", "1,594,585"])
    ws.append(["Green Asset Ratio eligible", "18.4%"])
    buf = io.BytesIO(); wb.save(buf)

    out = extract("bank_p3esg", "filed.xlsx", buf.getvalue())
    assert out["format"] == "excel"
    by_dp = {c["datapoint_key"]: c for c in out["cells"] if c["datapoint_key"]}
    assert by_dp["p3_scope3"]["value_num"] == 1594585.0
    assert by_dp["p3_gar_eligible"]["value_num"] == 18.4 and by_dp["p3_gar_eligible"]["unit"] == "%"


def test_extract_ixbrl_applies_scale():
    ix = (b'<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>'
          b'<ix:nonFraction name="FinancedEmissionsScope3" contextRef="c" unitRef="tco2e" scale="3">412.9</ix:nonFraction>'
          b'<ix:nonFraction name="GreenAssetRatioEligibleStock" contextRef="c" unitRef="pure" scale="0">0.184</ix:nonFraction>'
          b'</body></html>')
    assert detect_format("f.html", ix) == "ixbrl"
    out = extract("bank_p3esg", "f.html", ix)
    vals = {c["datapoint_key"]: c["value_num"] for c in out["cells"]}
    assert vals["p3_scope3"] == pytest.approx(412900.0)   # 412.9 x 10^3
    assert vals["p3_gar_eligible"] == pytest.approx(0.184)


def test_extract_rejects_unreadable_and_unknown():
    with pytest.raises(ValueError):
        extract("bank_p3esg", "empty.xlsx", b"")          # not a real workbook -> unsupported/unreadable
    with pytest.raises(ValueError):
        extract("no_such_framework", "f.html", b"<html></html>")
