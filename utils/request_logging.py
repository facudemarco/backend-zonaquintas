"""Capture bounded, redacted HTTP request and JSON response details."""

import asyncio
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode

from sqlalchemy import text

from Database.getConnection import engine


logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 32 * 1024
RETENTION_DAYS = 30
SENSITIVE_PARTS = (
    "password", "passwd", "token", "secret", "authorization", "cookie",
    "api_key", "apikey", "card", "cvv", "cvc",
    "refresh", "access_token", "otp",
)
_last_cleanup = None
_cleanup_lock = threading.Lock()
_schema_warning_logged = False


def _is_sensitive(key):
    normalized = "".join(char.lower() for char in str(key) if char.isalnum() or char == "_")
    return any(part in normalized for part in SENSITIVE_PARTS)


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def sanitize_query(query_string):
    if not query_string:
        return ""
    pairs = parse_qsl(query_string, keep_blank_values=True)
    safe_pairs = [(key, "[REDACTED]" if _is_sensitive(key) else value) for key, value in pairs]
    return urlencode(safe_pairs)[:4096]


def _store_json_body(buffer, too_large, content_type):
    if not content_type or not ("application/json" in content_type or "+json" in content_type):
        return None
    if too_large:
        return json.dumps({"_omitted": "JSON body exceeds 32 KiB"})
    if not buffer:
        return None
    try:
        parsed = json.loads(bytes(buffer))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.dumps({"_omitted": "JSON body could not be decoded"})
    return json.dumps(redact(parsed), ensure_ascii=False, separators=(",", ":"))


def _persist(record):
    global _last_cleanup, _schema_warning_logged
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO request_logs
                    (id, method, path, query_string, status_code, duration_ms,
                     request_bytes, response_bytes, request_body, response_body, created_at)
                VALUES
                    (:id, :method, :path, :query_string, :status_code, :duration_ms,
                     :request_bytes, :response_bytes, :request_body, :response_body, NOW())
            """), record)

            now = datetime.utcnow()
            with _cleanup_lock:
                should_cleanup = _last_cleanup is None or now - _last_cleanup >= timedelta(hours=6)
                if should_cleanup:
                    connection.execute(
                        text("DELETE FROM request_logs WHERE created_at < :cutoff"),
                        {"cutoff": now - timedelta(days=RETENTION_DAYS)},
                    )
                    _last_cleanup = now
        _schema_warning_logged = False
    except Exception:
        # Logging must never make an application request fail.
        if not _schema_warning_logged:
            logger.warning("Request logging is unavailable; apply the request_logs migration.", exc_info=True)
            _schema_warning_logged = True


class RequestLogMiddleware:
    """ASGI middleware that records API calls without consuming request bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        request_body = bytearray()
        response_body = bytearray()
        request_too_large = False
        response_too_large = False
        request_bytes = 0
        response_bytes = 0
        response_status = 500
        response_content_type = ""

        async def capture_receive():
            nonlocal request_too_large, request_bytes
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                request_bytes += len(chunk)
                remaining = MAX_BODY_BYTES - len(request_body)
                if len(chunk) > remaining:
                    request_too_large = True
                elif not request_too_large:
                    request_body.extend(chunk)
            return message

        async def capture_send(message):
            nonlocal response_status, response_content_type
            nonlocal response_too_large, response_bytes
            if message.get("type") == "http.response.start":
                response_status = message.get("status", 500)
                headers = dict(message.get("headers", []))
                response_content_type = headers.get(b"content-type", b"").decode("latin-1")
            elif message.get("type") == "http.response.body":
                chunk = message.get("body", b"")
                response_bytes += len(chunk)
                remaining = MAX_BODY_BYTES - len(response_body)
                if len(chunk) > remaining:
                    response_too_large = True
                elif not response_too_large:
                    response_body.extend(chunk)
            await send(message)

        try:
            await self.app(scope, capture_receive, capture_send)
        except Exception:
            raise
        finally:
            request_headers = dict(scope.get("headers", []))
            request_content_type = request_headers.get(b"content-type", b"").decode("latin-1")
            record = {
                "id": str(uuid.uuid4()),
                "method": scope.get("method", "GET")[:10],
                "path": scope.get("path", "")[:1024],
                "query_string": sanitize_query(scope.get("query_string", b"").decode("latin-1")),
                "status_code": response_status,
                "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
                "request_bytes": request_bytes,
                "response_bytes": response_bytes,
                "request_body": _store_json_body(request_body, request_too_large, request_content_type),
                "response_body": _store_json_body(response_body, response_too_large, response_content_type),
            }
            await asyncio.to_thread(_persist, record)
