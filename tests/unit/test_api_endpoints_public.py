"""E310: GET /v1/lookup/score/{lookup_id} was served by the private helper `_poll_context` — a helper had been put between
the route's decorator and the function it decorated — so polling a pending lookup could never answer. Every operation the
API serves must be a public endpoint function: a name with a leading underscore is a helper, never a route."""
from api.main import app


def test_no_operation_is_served_by_a_private_helper():
    ops = [(p, m, o.get("operationId") or "") for p, ms in app.openapi()["paths"].items() for m, o in ms.items()]
    assert len(ops) > 100
    assert [x for x in ops if x[2].startswith("_")] == []
