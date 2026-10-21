import asyncio
import json

from utils import request_logging
from utils.request_logging import _store_json_body, redact, sanitize_query


def test_redact_removes_credentials_recursively():
    value = {
        "email": "person@example.com",
        "password": "do-not-store",
        "profile": {"access_token": "token-value", "name": "Guest"},
        "items": [{"card_number": "4111111111111111", "status": "paid"}],
    }

    result = redact(value)

    assert result["password"] == "[REDACTED]"
    assert result["profile"]["access_token"] == "[REDACTED]"
    assert result["items"][0]["card_number"] == "[REDACTED]"
    assert result["profile"]["name"] == "Guest"


def test_query_secrets_are_redacted():
    result = sanitize_query("page=2&access_token=token-value&status=paid")

    assert "token-value" not in result
    assert "access_token=%5BREDACTED%5D" in result
    assert "status=paid" in result


def test_json_body_is_saved_redacted_and_oversized_body_is_omitted():
    body = b'{"password":"secret","email":"person@example.com"}'

    saved = json.loads(_store_json_body(body, False, "application/json"))
    omitted = json.loads(_store_json_body(bytearray(b"partial"), True, "application/json"))

    assert saved["password"] == "[REDACTED]"
    assert saved["email"] == "person@example.com"
    assert omitted["_omitted"] == "JSON body exceeds 32 KiB"


def test_middleware_records_status_duration_and_sanitized_json(monkeypatch):
    captured = []
    monkeypatch.setattr(request_logging, "_persist", captured.append)
    body = b'{"password":"secret","name":"Test"}'
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def app(scope, receive_fn, send_fn):
        assert (await receive_fn())["body"] == body
        await send_fn({
            "type": "http.response.start", "status": 201,
            "headers": [(b"content-type", b"application/json")],
        })
        await send_fn({
            "type": "http.response.body",
            "body": b'{"access_token":"hidden","ok":true}',
            "more_body": False,
        })

    scope = {
        "type": "http", "method": "POST", "path": "/register",
        "query_string": b"source=form&token=hidden",
        "headers": [(b"content-type", b"application/json")],
    }
    asyncio.run(request_logging.RequestLogMiddleware(app)(scope, receive, send))

    assert sent[0]["status"] == 201
    assert len(captured) == 1
    record = captured[0]
    assert record["status_code"] == 201
    assert json.loads(record["request_body"])["password"] == "[REDACTED]"
    assert json.loads(record["response_body"])["access_token"] == "[REDACTED]"
    assert "hidden" not in record["query_string"]
