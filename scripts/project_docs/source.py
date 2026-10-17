"""Readers for the source files the documents describe, and the Markdown helpers every document uses.

Pure functions over text — no database, no network — so tests/unit/test_build_project_docs.py exercises them directly:
a subset of TypeScript object literals (the sidebar and tab configurations), CSS custom-property blocks, exported
React functions with the comment above them, and a hand-written passage tied to the source it describes.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGENERATE = "venv/bin/python -m scripts.build_project_docs --write"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def sha12(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


# ── TypeScript object literals ─────────────────────────────────────────────────────────────────────────────────────
class Ident(str):
    """A bare identifier the literal uses but the file does not define as data (an icon component, say)."""


_SKIP = re.compile(r"(?:\s+|//[^\n]*|/\*.*?\*/)*", re.S)
_TOK = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|\.\.\.|[A-Za-z_$][\w$]*|[{}\[\]:,()]""")


class _Literal:
    """Recursive descent over objects, arrays, strings, numbers, true/false/null, identifiers and `...SPREAD`."""

    def __init__(self, src: str, pos: int, consts: dict):
        self.src, self.pos, self.consts = src, pos, consts

    def _tok(self, advance: bool) -> str:
        pos = _SKIP.match(self.src, self.pos).end()
        m = _TOK.match(self.src, pos)
        if not m:
            raise SyntaxError(f"cannot read a literal at offset {pos}: {self.src[pos:pos + 40]!r}")
        if advance:
            self.pos = m.end()
        return m.group(0)

    def peek(self) -> str:
        return self._tok(False)

    def take(self, want: str | None = None) -> str:
        t = self._tok(True)
        if want is not None and t != want:
            raise SyntaxError(f"expected {want!r}, found {t!r}")
        return t

    def value(self):
        t = self.take()
        if t == "{":
            out = {}
            while self.peek() != "}":
                key = self.take()
                out[key[1:-1] if key[0] in "'\"" else key] = (self.take(":"), self.value())[1]
                if self.peek() == ",":
                    self.take()
            self.take("}")
            return out
        if t == "[":
            items: list = []
            while self.peek() != "]":
                if self.peek() == "...":
                    self.take()
                    items.extend(self.consts[self.take()])
                else:
                    items.append(self.value())
                if self.peek() == ",":
                    self.take()
            self.take("]")
            return items
        if t[0] in "'\"":
            return re.sub(r"\\(.)", r"\1", t[1:-1])
        if re.fullmatch(r"-?\d+(?:\.\d+)?", t):
            return float(t) if "." in t else int(t)
        if t in ("true", "false", "null", "undefined"):
            return {"true": True, "false": False}.get(t)
        return self.consts.get(t, Ident(t))


def const_value(src: str, name: str, consts: dict | None = None):
    """The literal assigned to `const NAME` (optionally exported and typed) in src."""
    m = re.search(rf"\bconst\s+{re.escape(name)}\b[^=]*=", src)
    if not m:
        raise LookupError(f"const {name} not found")
    return _Literal(src, m.end(), consts or {}).value()


def string_list_consts(src: str) -> dict[str, list[str]]:
    """Every top-level `const NAME = [ ... ]` that is a list of strings (AGRI, FIN, ...), in file order."""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"^const\s+([A-Z][A-Z0-9_]*)\s*=\s*\[", src, re.M):
        try:
            v = _Literal(src, m.end() - 1, out).value()
        except (SyntaxError, KeyError):
            continue
        if isinstance(v, list) and all(isinstance(x, str) and not isinstance(x, Ident) for x in v):
            out[m.group(1)] = v
    return out


def function_source(src: str, name: str) -> str:
    """`function NAME(...) { ... }` as written — parameters and body, braces matched."""
    m = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", src)
    if not m:
        raise LookupError(f"function {name} not found")
    depth, i = 1, m.end()
    while depth:
        depth += {"(": 1, ")": -1}.get(src[i], 0)
        i += 1
    i = src.index("{", i)
    depth, j = 1, i + 1
    while depth:
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        j += 1
    return src[m.start():j]


def exported_functions(src: str) -> list[dict]:
    """Each `export [default] function Name(` with its parameter names and the comment lines directly above it."""
    lines = src.splitlines()
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    out = []
    for k, line in enumerate(lines):
        m = re.match(r"export\s+(?:default\s+)?function\s+(\w+)\s*(?:<[^(]*>)?\(", line)
        if not m:
            continue
        comment: list[str] = []
        j = k - 1
        while j >= 0 and lines[j].lstrip().startswith("//"):
            comment.insert(0, lines[j].strip()[2:].strip(" ─"))
            j -= 1
        out.append({"name": m.group(1), "line": k + 1, "params": _destructured(src, offsets[k] + m.end()),
                    "comment": " ".join(c for c in comment if c)})
    return out


def _destructured(src: str, pos: int) -> list[str]:
    """The top-level names of a `{ a, b = 1, c }` parameter pattern starting at pos (none if it is not one)."""
    start = _SKIP.match(src, pos).end()
    if src[start:start + 1] != "{":
        return []
    names, depth, part = [], 0, ""
    for ch in src[start:]:
        depth += {"{": 1, "(": 1, "[": 1, "}": -1, ")": -1, "]": -1}.get(ch, 0)
        if depth == 0 or (depth == 1 and ch == ","):
            names.append(re.split(r"[=:]", part)[0].strip())
            part = ""
            if depth == 0:
                break
        elif not (depth == 1 and ch == "{" and not part):
            part += ch
    return [n for n in names if re.fullmatch(r"\w+", n)]


# ── CSS ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def css_block(src: str, selector: str) -> str:
    """The body of the first rule whose selector is exactly `selector`."""
    m = re.search(rf"(?m)^{re.escape(selector)}\s*\{{", src)
    if not m:
        raise LookupError(f"CSS rule {selector!r} not found")
    depth, j = 1, m.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        j += 1
    return src[m.end():j - 1]


def css_vars(block: str) -> list[tuple[str, str, str]]:
    """(name, value, the comment on the same line) for each custom property declared in a rule body."""
    out = []
    for line in block.splitlines():
        for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", line):
            note = re.search(r"/\*\s*(.*?)\s*\*/", line[m.end():])
            out.append((m.group(1), " ".join(m.group(2).split()), note.group(1) if note else ""))
    return out


# ── Hand-written passages tied to their source ─────────────────────────────────────────────────────────────────────
class StaleText(RuntimeError):
    """A hand-written passage whose source changed since it was last read."""


def tied(where: str, passage: str, sources: dict[str, str], checksum: str) -> str:
    """Return `passage` only while the source it describes is the text it was written from. A change to that source
    stops the generator: re-read the source, correct the passage, then set the new checksum the error names."""
    got = sha12("\n".join(f"{k}\n{sources[k]}" for k in sorted(sources)))
    if got != checksum:
        raise StaleText(f"{where}: {', '.join(sorted(sources))} changed since the passage was written — re-read it, "
                        f"correct the passage, then set its checksum to {got!r}")
    return passage


# ── Markdown ───────────────────────────────────────────────────────────────────────────────────────────────────────
def prose(s: str) -> str:
    """Text quoted from code, made safe for Markdown: `<` and `>` outside code spans would be read as HTML."""
    parts = s.split("`")
    return "`".join(p if k % 2 else p.replace("<", "&lt;").replace(">", "&gt;") for k, p in enumerate(parts))


def cell(v) -> str:
    s = "" if v is None else str(v)
    return " ".join(prose(s).replace("|", "\\|").split())


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def mermaid(body: str) -> str:
    return "```mermaid\n" + body.rstrip() + "\n```"


def banner(sources: str) -> str:
    return (f"> **Generated — do not edit by hand.** Written by `scripts/build_project_docs.py` from {sources}. "
            f"Regenerate with `{REGENERATE}`; the gate (`scripts/precommit.sh`) fails when this file differs from "
            "what the code produces now.")
