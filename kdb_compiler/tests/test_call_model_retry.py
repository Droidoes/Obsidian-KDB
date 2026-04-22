"""Tests for call_model_retry — retryable classification, backoff, Retry-After."""
from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from kdb_compiler.call_model import ModelRequest, ModelResponse
from kdb_compiler.call_model_retry import _parse_retry_after, call_model_with_retry


# ---------- fixtures / helpers ----------

def _ok() -> ModelResponse:
    return ModelResponse(
        text="ok", input_tokens=1, output_tokens=1, latency_ms=1,
        model="m", provider="anthropic", raw=None,
    )


def _make_sdk_error(
    cls: type[Exception],
    *,
    status_code: int = 429,
    headers: dict[str, str] | None = None,
) -> Exception:
    req = httpx.Request("POST", "https://example.com/api")
    resp = httpx.Response(status_code=status_code, headers=headers or {}, request=req)
    return cls("test error", response=resp, body=None)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch):
    """Make every test instant by default. Tests that care about sleep durations override."""
    monkeypatch.setattr("kdb_compiler.call_model_retry.time.sleep", lambda _s: None)


def _req() -> ModelRequest:
    return ModelRequest(provider="anthropic", model="m", prompt="hi")


# ---------- happy path ----------

def test_first_call_succeeds_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    cm = MagicMock(return_value=_ok())
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", cm)
    resp = call_model_with_retry(_req())
    assert cm.call_count == 1
    assert resp.text == "ok"


# ---------- attempts threading (M2 Step A2) ----------

def test_attempts_field_reflects_retry_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned ModelResponse.attempts must equal the 1-indexed attempt
    number that finally succeeded — needed by the M2 resp-stats writer."""
    sequence: list[Exception | ModelResponse] = [
        _make_sdk_error(anthropic.RateLimitError),
        _make_sdk_error(anthropic.InternalServerError, status_code=503),
        _ok(),
    ]

    def fake_call(_):
        v = sequence.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", fake_call)
    resp = call_model_with_retry(_req(), max_attempts=3)
    assert resp.attempts == 3, f"expected attempts=3 after 2 retries, got {resp.attempts}"


def test_attempts_field_is_1_on_first_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """First-try success → attempts == 1."""
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", MagicMock(return_value=_ok()))
    resp = call_model_with_retry(_req())
    assert resp.attempts == 1


# ---------- retryable flow ----------

def test_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sequence = [
        _make_sdk_error(anthropic.RateLimitError),
        _make_sdk_error(anthropic.InternalServerError, status_code=503),
        _ok(),
    ]

    def fake_call(_):
        v = sequence.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", fake_call)
    resp = call_model_with_retry(_req(), max_attempts=3)
    assert resp.text == "ok"
    assert sequence == []


def test_exhaustion_reraises_last_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = _make_sdk_error(anthropic.RateLimitError)
    monkeypatch.setattr(
        "kdb_compiler.call_model_retry.call_model",
        MagicMock(side_effect=exc),
    )
    with pytest.raises(anthropic.RateLimitError):
        call_model_with_retry(_req(), max_attempts=3)


def test_max_attempts_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    cm = MagicMock(side_effect=_make_sdk_error(anthropic.RateLimitError))
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", cm)
    with pytest.raises(anthropic.RateLimitError):
        call_model_with_retry(_req(), max_attempts=4)
    assert cm.call_count == 4


# ---------- non-retryable flow ----------

def test_auth_error_bubbles_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = _make_sdk_error(anthropic.AuthenticationError, status_code=401)
    cm = MagicMock(side_effect=exc)
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", cm)
    with pytest.raises(anthropic.AuthenticationError):
        call_model_with_retry(_req(), max_attempts=3)
    assert cm.call_count == 1


def test_bad_request_bubbles_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = _make_sdk_error(anthropic.BadRequestError, status_code=400)
    cm = MagicMock(side_effect=exc)
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", cm)
    with pytest.raises(anthropic.BadRequestError):
        call_model_with_retry(_req(), max_attempts=3)
    assert cm.call_count == 1


def test_valueerror_bubbles_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    cm = MagicMock(side_effect=ValueError("bad input"))
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", cm)
    with pytest.raises(ValueError):
        call_model_with_retry(_req(), max_attempts=3)
    assert cm.call_count == 1


# ---------- retry-after parsing ----------

def test_parse_retry_after_integer_string() -> None:
    resp = MagicMock()
    resp.headers = {"retry-after": "15"}
    exc = type("X", (), {"response": resp})()
    assert _parse_retry_after(exc) == 15.0


def test_parse_retry_after_capitalized_header() -> None:
    resp = MagicMock()
    resp.headers = {"Retry-After": "7"}
    exc = type("X", (), {"response": resp})()
    assert _parse_retry_after(exc) == 7.0


def test_parse_retry_after_missing_returns_none() -> None:
    resp = MagicMock()
    resp.headers = {}
    exc = type("X", (), {"response": resp})()
    assert _parse_retry_after(exc) is None


def test_parse_retry_after_no_response_returns_none() -> None:
    exc = type("X", (), {})()
    assert _parse_retry_after(exc) is None


def test_parse_retry_after_bad_value_returns_none() -> None:
    resp = MagicMock()
    resp.headers = {"retry-after": "soon"}
    exc = type("X", (), {"response": resp})()
    assert _parse_retry_after(exc) is None


# ---------- retry-after honored during retry ----------

def test_retry_after_header_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = _make_sdk_error(anthropic.RateLimitError, headers={"retry-after": "7"})
    sequence: list[Exception | ModelResponse] = [exc, _ok()]

    def fake_call(_):
        v = sequence.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    sleeps: list[float] = []
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", fake_call)
    monkeypatch.setattr("kdb_compiler.call_model_retry.time.sleep", lambda s: sleeps.append(s))

    call_model_with_retry(_req(), max_attempts=3)
    assert len(sleeps) == 1
    # Retry-After was 7s; +20% jitter ceiling = 8.4s
    assert 7.0 <= sleeps[0] <= 8.4


def test_retry_after_capped_by_max_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = _make_sdk_error(anthropic.RateLimitError, headers={"retry-after": "9999"})
    sequence: list[Exception | ModelResponse] = [exc, _ok()]

    def fake_call(_):
        v = sequence.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    sleeps: list[float] = []
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", fake_call)
    monkeypatch.setattr("kdb_compiler.call_model_retry.time.sleep", lambda s: sleeps.append(s))

    call_model_with_retry(_req(), max_attempts=3, max_backoff=30.0)
    # Cap is 30s; jitter adds up to +20%
    assert 30.0 <= sleeps[0] <= 36.0


def test_exponential_backoff_without_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = _make_sdk_error(anthropic.RateLimitError)  # no retry-after header
    sequence: list[Exception | ModelResponse] = [exc, exc, _ok()]

    def fake_call(_):
        v = sequence.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    sleeps: list[float] = []
    monkeypatch.setattr("kdb_compiler.call_model_retry.call_model", fake_call)
    monkeypatch.setattr("kdb_compiler.call_model_retry.time.sleep", lambda s: sleeps.append(s))

    call_model_with_retry(_req(), max_attempts=3, initial_backoff=1.0)
    assert len(sleeps) == 2
    # attempt 1 → 1.0s base (+ up to +20% jitter)
    assert 1.0 <= sleeps[0] <= 1.2
    # attempt 2 → 2.0s base (+ up to +20% jitter)
    assert 2.0 <= sleeps[1] <= 2.4
