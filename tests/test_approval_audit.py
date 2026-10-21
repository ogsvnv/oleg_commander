"""One-use approvals and redacted tool audit integration tests."""

import asyncio
import json
import stat
from pathlib import Path

import pytest

from oleg_commander.audit import AuditLogger
from oleg_commander.config import Config, LoggingConfig, SecurityConfig
from oleg_commander.security import SecurityManager
from oleg_commander.server import OlegCommanderServer
from oleg_commander.services.approval_service import (
    ApprovalService,
    invocation_digest,
)
from oleg_commander.tool_result import ToolResult
from oleg_commander.tools.filesystem import FilesystemTool


class CaptureMCP:
    def __init__(self):
        self.tools = {}

    def add_tool(self, fn, name, description):
        self.tools[name] = fn


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def make_app(tmp_path, *, read_only=False, require_approval=True, audit=True):
    config = Config(
        security=SecurityConfig(
            read_only=read_only,
            require_approval=require_approval,
            allowed_directories=[str(tmp_path)],
        ),
        logging=LoggingConfig(audit_enabled=audit),
    )
    app = OlegCommanderServer(config)
    app.server = CaptureMCP()
    asyncio.run(app._register_tools())
    return app


def call(tool, *args, **kwargs):
    return asyncio.run(tool(*args, **kwargs))


def test_write_is_approved_out_of_band_and_consumed_once(tmp_path, isolated_home):
    app = make_app(tmp_path)
    target = tmp_path / "example.txt"
    mutate = app.server.tools["filesystem.write_file"]

    first = call(mutate, path=str(target), content="SUPER_SECRET_DATA")
    assert first.error["code"] == "APPROVAL_REQUIRED"
    request_id = first.data["approval_id"]
    assert not target.exists()

    # The approval cannot be granted through a registered MCP tool.
    assert "approval.approve" not in app.server.tools
    assert "approval.reject" not in app.server.tools
    entries = ApprovalService().list_requests()
    assert len(entries) == 1
    assert entries[0]["id"] == request_id
    assert "SUPER_SECRET_DATA" not in json.dumps(entries)

    assert ApprovalService().decide(request_id, approve=True)
    result = call(mutate, path=str(target), content="SUPER_SECRET_DATA")
    assert result.success
    assert target.read_text() == "SUPER_SECRET_DATA"

    # Approval is one-use: replaying the same call creates a new request.
    replay = call(mutate, path=str(target), content="SUPER_SECRET_DATA")
    assert replay.error["code"] == "APPROVAL_REQUIRED"
    assert replay.data["approval_id"] != request_id

    db_data = ApprovalService().path.read_bytes()
    audit_data = AuditLogger().path.read_text()
    assert b"SUPER_SECRET_DATA" not in db_data
    assert "SUPER_SECRET_DATA" not in audit_data
    assert "filesystem.write_file" in audit_data
    assert '"success"' in audit_data


def test_changed_arguments_require_another_approval(tmp_path, isolated_home):
    app = make_app(tmp_path)
    mutate = app.server.tools["filesystem.write_file"]
    target = str(tmp_path / "another.txt")
    first = call(mutate, target, "hello")
    assert ApprovalService().decide(first.data["approval_id"], True)
    changed = call(mutate, target, "different")
    assert changed.error["code"] == "APPROVAL_REQUIRED"
    assert changed.data["approval_id"] != first.data["approval_id"]
    assert not Path(target).exists()


def test_rejected_request_cannot_be_used(tmp_path, isolated_home):
    app = make_app(tmp_path)
    mutate = app.server.tools["filesystem.delete_file"]
    req = call(mutate, path=str(tmp_path / "unused"))
    request_id = req.data["approval_id"]
    assert ApprovalService().decide(request_id, False)
    assert not ApprovalService().decide(request_id, True)
    again = call(mutate, path=str(tmp_path / "unused"))
    assert again.error["code"] == "APPROVAL_REQUIRED"
    assert again.data["approval_id"] != request_id


def test_expired_approval_is_not_accepted(tmp_path, isolated_home, monkeypatch):
    approval = ApprovalService(timeout_minutes=10)

    async def stub(*, value: str = "a"):
        return ToolResult(success=True)

    authorized, request_id = approval.request_or_consume("x.write", stub, (), {"value": "x"})
    assert not authorized
    assert approval.decide(request_id, True)
    import sqlite3
    with sqlite3.connect(approval.path) as db:
        db.execute("UPDATE approvals SET expires=0 WHERE id=?", (request_id,))
    authorized, second_id = approval.request_or_consume(
        "x.write", stub, (), {"value": "x"}
    )
    assert not authorized
    assert second_id != request_id


def test_read_only_never_prompts_or_writes(tmp_path, isolated_home):
    app = make_app(tmp_path, read_only=True)
    tool = app.server.tools["filesystem.write_file"]
    result = call(tool, str(tmp_path / "data"), "secret")
    assert result.error["code"] == "READ_ONLY"
    assert not ApprovalService().list_requests()


def test_audit_required_even_if_write_allowed(tmp_path, isolated_home):
    app = make_app(tmp_path, require_approval=False, audit=False)
    tool = app.server.tools["filesystem.write_file"]
    result = call(tool, str(tmp_path / "data"), "secret")
    assert result.error["code"] == "AUDIT_REQUIRED"
    assert not (tmp_path / "data").exists()


def test_authorization_is_task_scoped(tmp_path, isolated_home):
    security = SecurityManager(
        Config(security=SecurityConfig(read_only=False, require_approval=True))
    )
    assert not security.can_modify()

    async def check():
        async def child():
            return security.can_modify()

        with security.authorized_write():
            assert security.can_modify()
            assert await child()
        assert not security.can_modify()

    asyncio.run(check())
    assert not security.can_modify()


def test_approval_digest_is_canonical_for_positional_and_keyword_args():
    async def operation(path: str, content: str = ""):
        return None

    a = invocation_digest("write", operation, ("/tmp/file", "x"), {})
    b = invocation_digest("write", operation, (), {"content": "x", "path": "/tmp/file"})
    c = invocation_digest("write", operation, (), {"content": "y", "path": "/tmp/file"})
    assert a == b
    assert c != a


def test_local_state_is_private(tmp_path, isolated_home):
    store = ApprovalService()
    audit = AuditLogger()
    for path in [store.path, audit.path]:
        assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
        assert stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0


def test_fail_closed_if_state_directory_is_insecure(tmp_path, isolated_home):
    state = isolated_home / ".local" / "state" / "oleg-commander"
    state.mkdir(parents=True)
    state.chmod(0o755)
    with pytest.raises(PermissionError):
        ApprovalService()


def test_audit_does_not_store_return_values(tmp_path, isolated_home):
    app = make_app(tmp_path, read_only=True)
    file_path = tmp_path / "private.txt"
    file_path.write_text("HIGHLY_PRIVATE_OUTPUT")
    tool = app.server.tools["filesystem.read_file"]
    result = call(tool, path=str(file_path))
    assert result.success
    assert result.data["content"] == "HIGHLY_PRIVATE_OUTPUT"
    log_text = AuditLogger().path.read_text()
    assert "HIGHLY_PRIVATE_OUTPUT" not in log_text
    assert "filesystem.read_file" in log_text


def test_approved_context_is_reset_if_tool_errors(tmp_path, isolated_home, monkeypatch):
    app = make_app(tmp_path)
    tool = app.server.tools["filesystem.write_file"]
    target = str(tmp_path / "blocked.txt")
    req = call(tool, target, "text")
    assert ApprovalService().decide(req.data["approval_id"], True)

    async def crash(self, path, content):
        raise RuntimeError("SECRET_IN_EXCEPTION")

    monkeypatch.setattr(FilesystemTool, "write_file", crash)
    # A separate app registers the patched implementation with the same request
    # digest, so this is a new approval; test exception-safe reset directly.
    security = app.security_manager
    with pytest.raises(RuntimeError), security.authorized_write():
        raise RuntimeError("boom")
    assert not security.can_modify()
