"""One store per fact (E34): an investee's Taxonomy KPIs are read and written only through services.issuer_taxonomy
(plus the bank book's frozen per-objective read, which follows the same precedence), and a product's SFDR commitments
only through its template answers (template_answers, one store for every document template). A new direct reader would re-open the second path."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_CODE = [p for d in ("api", "services", "ml", "scripts") for p in (ROOT / d).rglob("*.py")]


def _users(pattern: str) -> set[str]:
    rx = re.compile(pattern)
    return {str(p.relative_to(ROOT)) for p in _CODE if rx.search(p.read_text(errors="ignore"))}


def test_issuer_taxonomy_kpis_have_one_reader_and_writer():
    sql = r"(FROM|INTO|UPDATE|JOIN)\s+issuer_taxonomy_kpi\b"
    assert _users(sql) <= {"services/issuer_taxonomy.py", "api/routers/bank.py"}, _users(sql)


def test_the_retired_duplicate_columns_are_not_used():
    assert not _users(r"issuer_esg_metrics[^;\"]{0,400}\btaxonomy_(eligible|aligned|aligned_capex)_pct\b")
    assert not _users(r"\bsfdr_precontractual\s*=|funds\.sfdr_precontractual|SET sfdr_precontractual")


def test_template_answers_have_one_writer():
    writers = _users(r"(INSERT INTO|UPDATE|DELETE FROM) template_answers")
    assert writers <= {"services/governance/template_answers.py"}, writers
    readers = _users(r"FROM template_answers")
    assert readers <= {"services/governance/template_answers.py"}, readers
