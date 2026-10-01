"""A monetary figure rests only on facts (feedback: facts only; E69). data/reference/money/parameters.json is the
register: every method or parameter an institution states, and every number a money module holds with why it is not
a guess. This test refuses:

  - a number literal anywhere in a money module (module or class level, a default, inline) that the register does not
    list as 'path:scope:value' — a new guess cannot be typed in (0, 1, -1, 100, rounding digits, indexes excepted);
  - a registered constant without a non-guess class: 'definition' (what a reported figure is), 'computation' (a
    setting of the arithmetic, e.g. a simulation count), 'text' (quoted, with its reference) or 'reference_data'
    (a named dataset with its vintage);
  - a method parameter without a label, a unit the stated lane checks, or a known breakdown;
  - a module still on the worklist ('pending') that no longer holds an unregistered number — move it to 'modules'.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "data" / "reference" / "money" / "parameters.json").read_text())
CLASSES = {"definition": ("why",), "computation": ("why",), "text": ("ref", "quote"), "reference_data": ("dataset", "vintage")}


TRIVIAL = {0, 1, -1, 100}              # arithmetic identities: nothing, the whole, a sign, per cent


def _numbers(path: str) -> list[str]:
    """Every number literal in the module, as 'scope:value' — scope is the module-level name it is assigned to, or the
    class / function it appears in. Not counted: 0, 1, -1, 100, the digits of a round(), an index or a slice."""
    tree = ast.parse((ROOT / path).read_text())
    parent = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}

    def scope(n):
        top = n
        while parent.get(top) is not None and not isinstance(parent[top], ast.Module):
            top = parent[top]
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inner = n
            while inner is not top and not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = parent[inner]
            return inner.name
        targets = top.targets if isinstance(top, ast.Assign) else [top.target] if isinstance(top, ast.AnnAssign) else []
        return next((t.id for t in targets if isinstance(t, ast.Name)), "<module>")

    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)):
            continue
        p = parent.get(n)
        if isinstance(p, ast.Call) and getattr(p.func, "id", None) == "round" and n is not p.args[0]:
            continue
        if isinstance(p, (ast.Subscript, ast.Slice)):
            continue
        v = -n.value if isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.USub) else n.value
        if v in TRIVIAL:
            continue
        out.append(f"{scope(n)}:{v:g}")
    return out


def _loose(path: str) -> list[str]:
    return [n for n in _numbers(path) if f"{path}:{n}" not in REG["constants"]]


def test_every_registered_constant_says_why_it_is_not_a_guess():
    for key, c in REG["constants"].items():
        assert c.get("class") in CLASSES, (key, c.get("class"))
        for field in CLASSES[c["class"]]:
            assert str(c.get(field) or "").strip(), (key, field)


def test_every_method_parameter_is_one_the_stated_lane_checks():
    from services.governance.provided_data import _METHOD_RANGE
    from services.money.params import members
    for key, p in REG["parameters"].items():
        assert key.startswith("method.") and p.get("label") and p.get("used_for"), key
        assert p["unit"] in _METHOD_RANGE, (key, p["unit"])
        if p.get("breakdown"):
            assert members(p["breakdown"]), key


@pytest.mark.parametrize("path", REG["modules"])
def test_a_money_module_holds_no_unregistered_number(path):
    loose = _loose(path)
    assert not loose, f"{path}: numbers with no registered source (state them as method parameters, or register why " \
                      f"they are not a guess): {loose}"


def test_the_worklist_is_real():
    assert not set(REG["modules"]) & set(REG["pending"])
    done = [p for p in REG["pending"] if not _loose(p)]
    assert not done, f"no longer pending — move to 'modules': {done}"
