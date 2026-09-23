"""Document-based entity-structure extraction — the auto-extract source for entity_structure_import.py.

NOT built. This deployment has no ANTHROPIC_API_KEY configured, and there is no LLM integration anywhere
else in this codebase to piggyback on. Rather than fake or mock an extraction (which would mean either
inventing a fixed structure or silently degrading to something that looks like it works but isn't reading
the actual uploaded document), this reports the gap honestly — available() and extract_from_document() are
the real interface points, checked and refused cleanly, not stubbed with fabricated output.

What the real implementation belongs here, once a key exists:
  1. Extract text from the uploaded PDF (pdftotext -layout is enough for a text-based annual report — this
     is exactly how ING Bank N.V.'s real 2025 Annual Report was read to build scripts/seed_ing_org_structure.py
     this session; a scanned/image-only report would need the embedded-image extraction technique used
     elsewhere in this codebase for the EBA Annex XL table, services/governance/transition_alignment.py).
  2. Locate the relevant note (typically "Principal subsidiaries" / "List of participating interests" /
     equivalent — the exact heading varies by jurisdiction and accounting standard).
  3. Call Claude with a schema-constrained extraction prompt to produce rows in EXACTLY the shape
     entity_structure_import.create_import() expects (name, parent_ref, kind, country, ownership_pct,
     consolidation_method), each carrying a source_note (a page/note citation — e.g. "Note 41, p.200") and
     a confidence score, so a human reviewer can see where every claim came from and how sure the model was
     — never presented as ground truth, always as a proposal to confirm or correct.
  4. Feed the result into entity_structure_import.create_import(org_id, actor, source="document_extraction",
     rows=..., source_document_name=filename) — the SAME staging path the manual-CSV workflow uses, so
     everything downstream (review, edit, confirm, cycle/dangling-parent validation) is shared, not
     duplicated.
"""
from __future__ import annotations

import os


def available() -> bool:
    """Whether document-based extraction can run at all in this deployment. False today for two
    independent reasons: no ANTHROPIC_API_KEY is configured, AND the extraction call itself isn't
    implemented yet — both would need to be true for this to return True."""
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and False   # implementation pending — see docstring


class ExtractionUnavailable(RuntimeError):
    pass


def extract_from_document(file_bytes: bytes, filename: str) -> list[dict]:
    """Would return entity_structure_import.create_import()-shaped rows extracted from the document.
    Raises honestly — this deployment has no ANTHROPIC_API_KEY configured and the extraction call itself
    isn't implemented yet — rather than returning a fabricated or mocked structure."""
    raise ExtractionUnavailable(
        "Document-based entity-structure extraction isn't available: this deployment has no "
        "ANTHROPIC_API_KEY configured, and the extraction call itself isn't implemented yet (see this "
        "module's docstring for exactly what belongs here once it is). Use the manual CSV template "
        "instead — GET /v1/entity-structure/template.csv."
    )
