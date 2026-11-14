import json

import pandas as pd
import pytest

import llm
from compare import compare
from llm import (FatalLLMError, LLMClient, LLMError, QuotaExhausted, extract_json,
                 parse_gemini_429)
from scoring import parse_scores, run_llm


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def gemini_ok(obj):
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]})


@pytest.fixture
def gemini(monkeypatch, tmp_path):
    """LLMClient wired to a scripted fake HTTP layer; returns (client, calls)."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    script, calls = [], []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        return script.pop(0)

    import requests
    monkeypatch.setattr(requests, "post", post)

    def make(*responses):
        script.extend(responses)
        return LLMClient("gemini", cache_path=tmp_path / "cache.jsonl", rpm=0), calls
    return make


def test_parse_scores_clamps_and_validates():
    out = parse_scores({"thesis_fit": 140, "stage_fit": -5, "ticket_fit": "70",
                        "geo_fit": 55.6, "rationale": " ok "})
    assert out == {"thesis_fit": 100, "stage_fit": 0, "ticket_fit": 70, "geo_fit": 56,
                   "rationale": "ok"}
    with pytest.raises(LLMError):
        parse_scores({"thesis_fit": 50})


def test_extract_json_from_wrapped_text():
    assert extract_json('Sure! ```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_quota_parsing():
    assert parse_gemini_429('{"quotaId": "GenerateRequestsPerDayPerProject"}')[0] is True
    assert parse_gemini_429('{"retryDelay": "23s"}') == (False, 23.0)


def test_missing_key_is_fatal(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(FatalLLMError):
        LLMClient("gemini")


def test_cache_prevents_second_network_call(gemini, tmp_path):
    client, calls = gemini(gemini_ok({"x": 1}))
    assert client.complete_json("sys", "user") == {"x": 1}
    # a fresh client (e.g. tomorrow's resumed run) reads the cache from disk
    again = LLMClient("gemini", cache_path=tmp_path / "cache.jsonl", rpm=0)
    assert again.complete_json("sys", "user") == {"x": 1}
    assert len(calls) == 1 and again.cache_hits == 1


def test_retries_minute_limit_then_succeeds(gemini):
    client, calls = gemini(FakeResponse(429, {"retryDelay": "1s"}), gemini_ok({"x": 2}))
    assert client.complete_json("s", "u") == {"x": 2}
    assert len(calls) == 2


def test_daily_quota_and_retired_model(gemini):
    client, _ = gemini(FakeResponse(429, {"quotaId": "RequestsPerDay"}),
                       FakeResponse(404, {"error": "not found"}))
    with pytest.raises(QuotaExhausted):
        client.complete_json("s", "u1")
    with pytest.raises(FatalLLMError):
        client.complete_json("s", "u2")


class ScriptedClient:
    network_calls = cache_hits = 0

    def __init__(self, *results):
        self.results = list(results)

    def complete_json(self, system, user):
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_run_llm_marks_fallback_rows_and_stops_on_quota(frame, startup):
    df = frame({"investor_id": "A"}, {"investor_id": "B"}, {"investor_id": "C"})
    good = {"thesis_fit": 90, "stage_fit": 80, "ticket_fit": 70, "geo_fit": 60, "rationale": "r"}
    records, failures, quota = run_llm(df, startup, ScriptedClient(
        good, LLMError("bad json"), QuotaExhausted()))
    assert [r["score_source"] for r in records] == ["llm", "rubric_fallback"]
    assert len(failures) == 1 and quota is True


def test_compare_ignores_fallback_rows():
    ids = [f"I{i}" for i in range(10)]
    base = pd.DataFrame({"investor_id": ids, "name": ids,
                         "thesis_fit": range(10), "stage_fit": range(10),
                         "ticket_fit": range(10), "geo_fit": range(10)})
    rubric = base.assign(total_score=range(10))
    llm_df = base.assign(total_score=range(10), rationale="r",
                         score_source=["llm"] * 8 + ["rubric_fallback"] * 2)
    r = compare(rubric, llm_df, picks={"I8", "I9", "I7"})
    assert r["n_compared"] == 8 and r["spearman_total"] == 1.0
