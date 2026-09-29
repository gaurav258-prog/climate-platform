"""Every route is authenticated, a reviewed public route, or tenant-resolved with record ownership checked (E24).

  * a route with no authentication must be in api/public_routes.PUBLIC_ROUTES (reviewed, with its reason)
  * a route that serves anonymous callers through the sector tenant resolver and takes a record id must check the
    record belongs to the caller's organisation (api.deps.own_or_404), or be a reviewed reference-id route
  * nothing on the public list may be a stale entry
"""
import inspect
import re

from fastapi.routing import APIRoute

from api.main import app
from api.public_routes import PUBLIC_ROUTES, REFERENCE_ID_ROUTES

_AUTH = ("get_current_user", "require_customer_id", "require_ingest_org", "require_step_up", "require_permission", "scim_org")


def _flat(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        else:
            sub = getattr(r, "router", None) or getattr(r, "original_router", None)
            if sub is not None and hasattr(sub, "routes"):
                yield from _flat(sub.routes)


def _deps(dep, out):
    if dep.call is not None:
        out.add(getattr(dep.call, "__qualname__", ""))
    for d in dep.dependencies:
        _deps(d, out)
    return out


ROUTES = [(f"{m} {r.path}", r) for r in _flat(app.routes) for m in sorted(r.methods) if m != "HEAD"]


def test_the_app_registers_its_routes():
    assert len(ROUTES) > 400                                    # a silently skipped router import would show here


def test_every_unauthenticated_route_is_a_reviewed_public_route():
    offenders = []
    for key, r in ROUTES:
        deps = _deps(r.dependant, set())
        authed = any(a in d for d in deps for a in _AUTH)
        tenant = any("tenant_resolver" in d for d in deps)
        if not authed and not tenant and key not in PUBLIC_ROUTES:
            offenders.append(key)
    assert not offenders, f"routes with no authentication and not on the reviewed public list: {offenders}"


def test_anonymous_record_routes_check_ownership():
    offenders = []
    for key, r in ROUTES:
        deps = _deps(r.dependant, set())
        if not any("tenant_resolver" in d for d in deps) or any(a in d for d in deps for a in _AUTH):
            continue
        if re.search(r"\{\w+_id\}", r.path) and key not in REFERENCE_ID_ROUTES and "own_or_404" not in inspect.getsource(r.endpoint):
            offenders.append(key)
    assert not offenders, f"anonymous-capable routes that serve a record by id without an ownership check: {offenders}"


def test_the_public_list_has_no_stale_entries():
    keys = {k for k, _ in ROUTES}
    assert not (set(PUBLIC_ROUTES) - keys), set(PUBLIC_ROUTES) - keys
