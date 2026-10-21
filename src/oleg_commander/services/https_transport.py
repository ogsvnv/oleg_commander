"""TLS-bound MCP transport with an out-of-band static bearer credential.

This is for clients that support an Authorization header. It is not a
replacement for OAuth authorization required by some hosted MCP clients.
"""

import hmac
import os
import re
import stat
from pathlib import Path

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings


_HOSTNAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,251}[a-zA-Z0-9]$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


class BearerGuard:
    """Reject unauthenticated HTTP/websocket calls before reaching MCP."""

    def __init__(self, app, token: str):
        self.app = app
        self.auth_header = b"Bearer " + token.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        candidates = [
            value for key, value in scope.get("headers", ())
            if key.lower() == b"authorization"
        ]
        if len(candidates) != 1 or not hmac.compare_digest(
            candidates[0], self.auth_header
        ):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401})
            else:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"text/plain"),
                            (b"www-authenticate", b"Bearer"),
                            (b"cache-control", b"no-store"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": b"Unauthorized"})
            return

        # Do not pass the static token into the MCP app or its instrumentation.
        safe_scope = dict(scope)
        safe_scope["headers"] = [
            (key, value)
            for key, value in scope.get("headers", ())
            if key.lower() != b"authorization"
        ]
        await self.app(safe_scope, receive, send)


def validate_https(config) -> tuple[str, str, str, str]:
    """Reject insecure configuration before binding a remote listener."""
    public = config.server.public_host
    cert = config.server.tls_certfile
    key = config.server.tls_keyfile
    token = os.environ.get("OLEG_COMMANDER_BEARER_TOKEN", "")
    if (
        not isinstance(public, str)
        or not _HOSTNAME.fullmatch(public)
        or ".." in public
        or public.endswith(".")
    ):
        raise ValueError("HTTPS needs a valid server.public_host hostname")
    if not _TOKEN.fullmatch(token):
        raise ValueError("HTTPS needs OLEG_COMMANDER_BEARER_TOKEN (32+ random chars)")
    if not cert or not key:
        raise ValueError("HTTPS requires tls_certfile and tls_keyfile")
    certificate, private_key = Path(cert).expanduser(), Path(key).expanduser()
    if (
        not certificate.is_file()
        or certificate.is_symlink()
        or not private_key.is_file()
        or private_key.is_symlink()
    ):
        raise ValueError("TLS certificate/key files must exist and not be symlinks")
    if stat.S_IMODE(private_key.stat().st_mode) & 0o077:
        raise ValueError("TLS private key must be owner-only (mode 0600)")
    if not os.access(private_key, os.R_OK):
        raise ValueError("TLS private key is not readable")
    return public, str(certificate), str(private_key), token


async def run_https(mcp_server, config):
    """Start MCP over HTTPS with auth, host validation and TLS encryption."""
    public, cert, key, token = validate_https(config)
    host = config.server.host
    port = config.server.port
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[public, f"{public}:{port}"],
        allowed_origins=[f"https://{public}", f"https://{public}:{port}"],
    )
    app = mcp_server.streamable_http_app(
        host=host,
        transport_security=security,
    )
    guarded = BearerGuard(app, token)
    server = uvicorn.Server(
        uvicorn.Config(
            guarded,
            host=host,
            port=port,
            ssl_certfile=cert,
            ssl_keyfile=key,
            log_level="warning",
            access_log=False,
            server_header=False,
            proxy_headers=False,
        )
    )
    await server.serve()
