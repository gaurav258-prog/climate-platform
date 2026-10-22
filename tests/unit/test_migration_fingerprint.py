"""E172: a migration's probe-free fingerprint ignores an edit to its REFUSAL_PROBE (a round-trip fixture that never
runs on upgrade or downgrade) and sees every other edit — so the applied-migration check (E100) still catches a
migration changed after it ran."""
from core.db.migration_fingerprint import file_sha, schema_sha

BASE = '''"""doc"""
from alembic import op

revision = "r1"
REFUSAL_PROBE = {"setup": "INSERT INTO t VALUES (1);", "cleanup": "DELETE FROM t;"}


def upgrade():
    op.execute("ALTER TABLE t ADD COLUMN c int")


def downgrade():
    op.execute("ALTER TABLE t DROP COLUMN c")
'''


def _two(tmp_path, other: str):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text(BASE)
    b.write_text(other)
    return str(a), str(b)


def test_a_probe_only_edit_keeps_the_schema_fingerprint(tmp_path):
    a, b = _two(tmp_path, BASE.replace('VALUES (1);"', 'VALUES (2);"'))
    assert file_sha(a) != file_sha(b) and schema_sha(a) == schema_sha(b)


def test_any_other_edit_changes_it(tmp_path):
    for other in (BASE.replace("ADD COLUMN c int", "ADD COLUMN c bigint"), BASE.replace('revision = "r1"', 'revision = "r2"'),
                  BASE + "\nHELPER = 1\n"):
        a, b = _two(tmp_path, other)
        assert schema_sha(a) != schema_sha(b)


def test_a_constant_only_the_probe_reads_is_part_of_the_probe(tmp_path):
    """E314: a migration applied before its probe was written (the API's start-up migrated the file the moment it was
    saved) gained the probe and the probe's own organisation id — the schema it builds is unchanged."""
    probed = BASE.replace('REFUSAL_PROBE = {"setup": "INSERT INTO t VALUES (1);", "cleanup": "DELETE FROM t;"}',
                          'ORG = "o1"\nREFUSAL_PROBE = {"setup": f"INSERT INTO t VALUES (\'{ORG}\');", "cleanup": "DELETE FROM t;"}')
    bare = "\n".join(line for line in BASE.splitlines() if not line.startswith("REFUSAL_PROBE")) + "\n"
    a, b = _two(tmp_path, probed)
    assert schema_sha(b) == schema_sha(a)
    (tmp_path / "bare.py").write_text(bare)                               # the file as it ran: no probe at all
    assert schema_sha(str(tmp_path / "bare.py")) == schema_sha(b)
    # read by the upgrade as well: no longer the probe's alone
    used = probed.replace('op.execute("ALTER TABLE t ADD COLUMN c int")', 'op.execute(f"ALTER TABLE t ADD COLUMN {ORG} int")')
    a, b = _two(tmp_path, used)
    assert schema_sha(a) != schema_sha(b)
