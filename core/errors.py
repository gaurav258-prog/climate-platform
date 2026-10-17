"""Errors a screen shows in customer words (UI standard, product owner 2026-10-16): a code from the message catalogue
(core/messages.py) with its values. The API answers {"error": {"error": code, "message": label, "detail": {...}}} —
the label on the screen, the detail behind its ⓘ — and the technical cause goes to the log only."""
from __future__ import annotations

from typing import Any

from core import messages


class UserError(Exception):
    def __init__(self, code: str, status: int | None = None, **params: Any):
        self.code, self.params = code, params
        self.status = status or messages.catalogue().get(code, {}).get("status", 400)
        super().__init__(code)

    def body(self) -> dict:
        r = messages.render(self.code, **self.params)
        return {"error": {"error": self.code, "message": r["label"], "detail": r["detail"]}}
