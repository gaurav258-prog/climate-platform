"""E138: a route's writes are committed before its response is sent — a client acting on a returned id at once (deciding
an approval request it was just given) must find the row saved."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import core.db.session as S
from api.deps import DbSession


class _Session:
    def __init__(self, log):
        self.log = log

    def commit(self):
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")

    def close(self):
        pass


class _Sent(JSONResponse):
    async def __call__(self, scope, receive, send):
        self.log.append("sent")
        await super().__call__(scope, receive, send)


def test_the_session_commits_before_the_response_is_sent(monkeypatch):
    log: list[str] = []
    monkeypatch.setattr(S, "_session_factory", lambda: (lambda: _Session(log)))
    app = FastAPI()

    @app.post("/x")
    def create(session: DbSession):
        r = _Sent({"id": "1"})
        r.log = log
        return r

    assert TestClient(app).post("/x").status_code == 200
    assert log == ["commit", "sent"]
