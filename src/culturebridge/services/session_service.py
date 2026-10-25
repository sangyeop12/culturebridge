"""Signed anonymous browser sessions, without user accounts or personal profiles."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

from starlette.responses import JSONResponse

from culturebridge.config import get_settings
from culturebridge.services.operation_service import session_owner


class AnonymousSessionMiddleware:
    def __init__(self, app):
        self.app = app
        self.requests = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        settings = get_settings()
        cookies = SimpleCookie()
        try:
            cookies.load(dict(scope.get("headers", [])).get(b"cookie", b"").decode())
        except Exception:
            pass
        query = parse_qs(scope.get("query_string", b"").decode(errors="replace"))
        kiosk = scope.get("path") == "/kiosk" or query.get("mode", [""])[0] == "kiosk"
        cookie_name = "cb_kiosk_session" if kiosk else "cb_session"
        supplied = cookies.get(cookie_name)
        raw = supplied.value if supplied else ""
        identity, _, signature = raw.partition(".")
        key = settings.storage_secret.encode()
        expected = hmac.new(key, identity.encode(), hashlib.sha256).hexdigest()
        valid = len(identity) == 32 and hmac.compare_digest(signature, expected)
        if scope.get("path") == "/kiosk" and query.get("reset", [""])[0] in {"manual", "timeout"}:
            valid = False
        if not valid:
            identity = secrets.token_hex(16)
        signed = identity + "." + hmac.new(key, identity.encode(), hashlib.sha256).hexdigest()
        owner = f"kiosk:{identity}" if kiosk else identity
        token = session_owner.set(owner)
        scope.setdefault("state", {})["cb_owner"] = owner
        try:
            if settings.public_mode and scope["type"] == "http" and scope.get("method") == "POST":
                now = time.monotonic()
                address = (scope.get("client") or ("unknown",))[0]
                for old in list(self.requests):
                    if not self.requests[old] or self.requests[old][-1] < now - 60:
                        del self.requests[old]
                bucket = self.requests[(str(settings.db_path.resolve()), address)]
                while bucket and bucket[0] < now - 60:
                    bucket.popleft()
                if len(bucket) >= settings.requests_per_minute:
                    return await JSONResponse(
                        {"detail": "요청이 많습니다. 잠시 후 다시 시도하세요."},
                        status_code=429,
                        headers={"Retry-After": "60"},
                    )(scope, receive, send)
                bucket.append(now)

            async def session_send(message):
                if message["type"] == "http.response.start" and not valid:
                    suffix = (
                        "; Secure"
                        if settings.secure_cookies or scope.get("scheme") == "https"
                        else ""
                    )
                    message.setdefault("headers", []).append(
                        (
                            b"set-cookie",
                            (
                                f"{cookie_name}={signed}; Path=/; HttpOnly; SameSite=Lax{suffix}"
                            ).encode(),
                        )
                    )
                await send(message)

            await self.app(scope, receive, session_send)
        finally:
            session_owner.reset(token)
