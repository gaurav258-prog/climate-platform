"""How the EUDR records speak to a screen (UI standard, product owner 2026-10-16): every check, refusal and explanation
is a message-catalogue code (data/reference/messages.en.json, prefix eudr.) with its values — the label for the screen,
the detail (what / why / next) behind its ⓘ — and every code it names (a shipment's kind, a reading's outcome, an event)
has its customer name in the catalogue's names blocks (names.eudr.*). Nothing here says whether a product complies:
a reading, a check or a record is what the undertaking weighs; the undertaking concludes (E108).
"""
from __future__ import annotations

from typing import Any, Optional

from core import messages
from core.errors import UserError


class EudrError(UserError, ValueError):
    """A refused EUDR step in customer words: a catalogue code with its values. The API answers it as a UserError (the
    label on the screen, the detail behind its ⓘ); str() is the detail's sentence (logs, another service's message)."""

    def __str__(self) -> str:
        return messages.render(self.code, **self.params)["detail"]["what"]


def finding(rule: str, category: str, severity: str, passed: bool, code: str, ref: Optional[str] = None,
            **params: Any) -> dict:
    """A check in the catalogue's words, the shape every rule set of the filings checklist shares
    (services/governance/filing_validation._check): `msg` is the message — its label for the screen, its detail behind
    the ⓘ — `message` its sentence for the other readers (the exception monitor, a refusal), `ref` the legal basis,
    shown one click away. category is the check's family: scope, completeness or plausibility."""
    m = messages.render(code, **params)
    return {"rule": rule, "category": category, "severity": severity, "passed": bool(passed),
            "message": m["detail"]["what"], "msg": m, "ref": ref}


def name(kind: str, key: Optional[str]) -> str:
    """A code's customer name from names.eudr.<kind> ('kind', 'making_available' → 'Making available')."""
    return messages.name(f"eudr.{kind}", key) if key is not None else ""


def state(status: str) -> str:
    """A statement's or declaration's lifecycle status in words ('in_review' → 'in review'): the filings' own names
    (names.filing.status), shared with every filing."""
    return messages.name("filing.status", status)


def names() -> dict[str, dict[str, str]]:
    """Every EUDR names block, keyed without its prefix ({'kind': {...}, 'outcome': {...}}) — what a screen names the
    codes of its records with."""
    return {k.removeprefix("eudr."): v for k, v in messages.names().items() if k.startswith("eudr.")}


def blocking_labels(findings: list[dict], n: int = 6) -> str:
    """The failing blocking checks in a line, by their labels (a refusal to prepare or keep names them)."""
    return "; ".join([f["msg"]["label"] for f in findings if not f["passed"] and f["severity"] == "blocking"][:n])


# ── a product's place in Annex I (services.reference.eudr_refdata.scope) ──

def scope_kind(sc: dict) -> str:
    """Why the list of covered products decides as it does, from the outcome's own fields: listed, not_listed, or open
    — ambiguous (the entry's application is unclear), excepts_part (the entry excepts part of what it names),
    ex_heading (printed 'ex': only part of the heading) or narrower_only (only longer codes are listed)."""
    if sc.get("in_scope") is True:
        return "listed"
    if sc.get("in_scope") is False:
        return "not_listed"
    e = sc.get("entry")
    if e is None:
        return "narrower_only"
    if e.get("application_ambiguous"):
        return "ambiguous"
    if e.get("printed_exception"):
        return "excepts_part"
    return "ex_heading"


def scope_msg(sc: dict, hs_code: str) -> dict:
    """The scope outcome as a message: label for the screen, the printed entry it rests on behind the ⓘ."""
    e = sc.get("entry") or {}
    kind = scope_kind(sc)
    printed = ", ".join(x.get("printed_code") or x["code"] for x in sc.get("entries") or [])
    return messages.render(f"eudr.scope.{kind}", hs=hs_code, printed=e.get("printed_code") or e.get("code") or printed,
                           commodity=name("commodity", e.get("commodity")) if e.get("commodity") else "",
                           description=e.get("description") or "", exception=e.get("printed_exception") or "",
                           note=e.get("application_note") or "")


# ── a plot's satellite reading (services/eudr/reading.py) ──

# the reasons read() gives a 'not_assessable' reading, by the start of the sentence it stored before it kept the kind
_REASON_START = (("a point has no area", "point_no_radius"), ("the plot crosses data tiles", "crosses_tiles"),
                 ("the 2000 tree-cover layer could not be read", "treecover_unreadable"),
                 ("the dataset could not be read", "dataset_unreadable"))


def reason_kind(r: dict) -> Optional[str]:
    """Why a reading is not assessable: the kind read() records with it, or — a reading kept before it recorded the kind
    — the kind of the sentence it stored (each written by read() alone, so the start names it exactly)."""
    if r.get("outcome") != "not_assessable":
        return None
    kind = (r.get("method") or {}).get("reason_kind")
    if kind:
        return kind
    reason = (r.get("reason") or "").strip()
    return next((k for start, k in _REASON_START if reason.startswith(start)), "unknown")


def reading_msg(r: Optional[dict]) -> dict:
    """A plot's current reading as a message: what the dataset shows, never a verdict."""
    if r is None:
        return messages.render("eudr.reading.unread")
    if r["outcome"] == "loss_after_cutoff":
        return messages.render("eudr.reading.loss", loss_ha=hectares(r.get("loss_ha")), year=r.get("first_loss_year") or "")
    if r["outcome"] == "no_loss_detected":
        return messages.render("eudr.reading.no_loss")
    return messages.render(f"eudr.reading.not_assessable.{reason_kind(r)}")


def with_reading_msg(r: Optional[dict]) -> Optional[dict]:
    return None if r is None else {**r, "msg": reading_msg(r)}


def hectares(v: Any) -> str:
    """An area in hectares as a reader writes it (1,234.5; up to two decimals)."""
    try:
        return f"{float(v):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "—"
