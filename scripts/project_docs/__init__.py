"""The as-built project documents, generated from the code and the database: docs/BACKEND_SCHEMA.md,
docs/TECHNICAL_REQUIREMENTS.md, docs/APP_FLOW.md and docs/DESIGN_BRIEF.md. Every statement in them is read from a
source file or the PostgreSQL catalogue, or is arithmetic on what was read; a hand-written passage is tied to the
source it describes (a checksum), so a change to that source stops the generator until the passage is re-read.

scripts/build_project_docs.py writes them (--write) or compares them with what the code produces now (--check, the
gate step in scripts/precommit.sh).
"""
