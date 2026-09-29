"""One Python version for the product: declared once, used by development, CI and the shipped image.

CI and the Docker image stayed on 3.9 while the code moved to 3.11+ syntax and development ran 3.14, so the build was
red for weeks and the image would have failed at start. pyproject.toml's requires-python is the one declaration; CI's
PYTHON_VERSION, the Dockerfile's base image, ruff's target and the running interpreter must all agree with it.
"""
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def _declared() -> str:
    m = re.fullmatch(r">=(3\.\d+),<3\.\d+", PROJECT["project"]["requires-python"].replace(" ", ""))
    assert m, "requires-python must pin one minor version, e.g. '>=3.14,<3.15'"
    return m.group(1)


def test_ci_uses_the_declared_version():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert re.search(r'PYTHON_VERSION:\s*"([\d.]+)"', ci).group(1) == _declared()


def test_the_image_uses_the_declared_version():
    bases = re.findall(r"^FROM python:([\d.]+)", (ROOT / "infra" / "docker" / "Dockerfile").read_text(), re.M)
    assert bases and set(bases) == {_declared()}


def test_lint_targets_the_declared_version():
    assert PROJECT["tool"]["ruff"]["target-version"] == "py" + _declared().replace(".", "")


def test_this_interpreter_is_the_declared_version():
    assert f"{sys.version_info.major}.{sys.version_info.minor}" == _declared()
