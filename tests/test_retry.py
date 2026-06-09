"""
Tests du helper de retry sur les erreurs transitoires de l'API Gmail.
Utilise un faux objet 'request' exposant .execute() (pas un mock de l'API).
"""

import pytest
from googleapiclient.errors import HttpError

from backend.src.services import analyzer


class _FakeResp(dict):
    """Imite une httplib2.Response (dict avec attribut .status)."""

    def __init__(self, status):
        super().__init__()
        self.status = status
        self.reason = "test"
        self["content-type"] = "application/json"


class _FakeRequest:
    """Stub minimal exposant .execute() pour piloter les échecs."""

    def __init__(self, fail_times, status=503):
        self.calls = 0
        self.fail_times = fail_times
        self.status = status

    def execute(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise HttpError(_FakeResp(self.status), b"error")
        return {"ok": True}


def test_retry_puis_succes(monkeypatch):
    monkeypatch.setattr(analyzer.time, "sleep", lambda *_: None)  # pas d'attente réelle
    req = _FakeRequest(fail_times=2, status=503)
    assert analyzer._execute_with_retry(req, max_attempts=4) == {"ok": True}
    assert req.calls == 3


def test_erreur_non_retryable_remonte(monkeypatch):
    monkeypatch.setattr(analyzer.time, "sleep", lambda *_: None)
    req = _FakeRequest(fail_times=1, status=404)
    with pytest.raises(HttpError):
        analyzer._execute_with_retry(req, max_attempts=4)
    assert req.calls == 1
