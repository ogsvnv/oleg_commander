"""Authenticated HTTPS transport tests without an external public listener."""

import asyncio

import httpx
import pytest

from oleg_commander.config import Config, ServerConfig
from oleg_commander.services.https_transport import BearerGuard, validate_https


async def fake_app(scope, receive, send):
    if scope["type"] != "http":
        return
    secrets = [
        value for name, value in scope["headers"]
        if name.lower() == b"authorization"
    ]
    assert not secrets
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"authorized"})


def run(coro):
    return asyncio.run(coro)


def test_bearer_middleware_rejects_unknown_or_missing_tokens():
    async def exercise():
        guard = BearerGuard(fake_app, "x" * 42)
        transport = httpx.ASGITransport(app=guard)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://example.test"
        ) as client:
            no_header = await client.get("/mcp")
            assert no_header.status_code == 401
            assert no_header.headers["www-authenticate"] == "Bearer"
            bad = await client.get(
                "/mcp", headers={"Authorization": "Bearer wrong"}
            )
            assert bad.status_code == 401
            authorized = await client.post(
                "/mcp", headers={"Authorization": "Bearer " + "x" * 42}
            )
            assert authorized.status_code == 200
            assert authorized.text == "authorized"

    run(exercise())


def test_bearer_middleware_denies_duplicate_headers():
    async def exercise():
        guard = BearerGuard(fake_app, "z" * 42)
        transport = httpx.ASGITransport(app=guard)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://example.test"
        ) as client:
            response = await client.get(
                "/mcp",
                headers=[
                    ("authorization", "Bearer " + "z" * 42),
                    ("authorization", "Bearer " + "z" * 42),
                ],
            )
            assert response.status_code == 401

    run(exercise())


def test_https_start_requires_public_host_random_token_and_certificates(
    tmp_path, monkeypatch
):
    cert = tmp_path / "certificate.pem"
    key = tmp_path / "private-key.pem"
    cert.write_text("not-a-real-cert")
    key.write_text("not-a-real-key")
    key.chmod(0o600)
    config = Config(
        server=ServerConfig(
            transport="https",
            host="0.0.0.0",
            public_host="commander.example.org",
            port=8765,
            tls_certfile=str(cert),
            tls_keyfile=str(key),
        ),
    )
    monkeypatch.setenv("OLEG_COMMANDER_BEARER_TOKEN", "x" * 42)
    public, certificate, private_key, token = validate_https(config)
    assert public == "commander.example.org"
    assert certificate == str(cert)
    assert private_key == str(key)
    assert token == "x" * 42

    monkeypatch.setenv("OLEG_COMMANDER_BEARER_TOKEN", "short")
    with pytest.raises(ValueError, match="BEARER_TOKEN"):
        validate_https(config)
    monkeypatch.delenv("OLEG_COMMANDER_BEARER_TOKEN", raising=False)
    with pytest.raises(ValueError, match="BEARER_TOKEN"):
        validate_https(config)


def test_https_denies_insecure_key_and_symlink(tmp_path, monkeypatch):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("test")
    key.write_text("test")
    monkeypatch.setenv("OLEG_COMMANDER_BEARER_TOKEN", "x" * 42)
    config = Config(
        server=ServerConfig(
            transport="https",
            public_host="commander.example.org",
            tls_certfile=str(cert),
            tls_keyfile=str(key),
        ),
    )
    key.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        validate_https(config)
    key.chmod(0o600)
    link = tmp_path / "link.pem"
    link.symlink_to(key)
    config.server.tls_keyfile = str(link)
    with pytest.raises(ValueError, match="symlinks"):
        validate_https(config)


def test_https_rejects_bad_hostnames(tmp_path, monkeypatch):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("cert")
    key.write_text("key")
    key.chmod(0o600)
    monkeypatch.setenv("OLEG_COMMANDER_BEARER_TOKEN", "y" * 42)
    for public_host in (None, "bad..host", "host/evil", "host ", "host."):
        config = Config(
            server=ServerConfig(
                transport="https",
                public_host=public_host,
                tls_certfile=str(cert),
                tls_keyfile=str(key),
            ),
        )
        with pytest.raises(ValueError, match="public_host"):
            validate_https(config)


def test_server_routes_https_to_verified_transport(monkeypatch, tmp_path):
    from oleg_commander import server
    from oleg_commander.server import OlegCommanderServer
    from tests.test_security_regressions import FakeMCPServer

    monkeypatch.setattr(server, "MCPServer", FakeMCPServer)
    monkeypatch.setenv("HOME", str(tmp_path))
    called = []

    async def fake_run_https(mcp_server, config):
        called.append(config.server.host)

    monkeypatch.setattr(server, "run_https", fake_run_https)
    config = Config(
        server=ServerConfig(transport="https", host="0.0.0.0"),
    )
    run(OlegCommanderServer(config).start())
    assert called == ["0.0.0.0"]
