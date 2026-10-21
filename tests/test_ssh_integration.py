"""Integration-style SSH policy tests without live network access."""

import asyncio
from types import SimpleNamespace

import pytest

from oleg_commander.config import Config, SecurityConfig
from oleg_commander.security import SecurityManager
from oleg_commander.tools.ssh import SSHTool


class FakeRemoteFile:
    def __init__(self, sftp, path, mode):
        self.sftp = sftp
        self.path = path
        self.mode = mode

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def read(self, limit):
        return self.sftp.files[self.path][:limit]

    async def write(self, data):
        self.sftp.files[self.path] = data


class FakeSFTP:
    def __init__(self):
        self.files = {"/srv/code/readme.txt": b"hello"}
        self.links = {}
        self.renames = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def realpath(self, path):
        return self.links.get(path, path)

    def open(self, path, mode):
        if mode == "xb" and path in self.files:
            raise FileExistsError(path)
        return FakeRemoteFile(self, path, mode)

    async def posix_rename(self, src, dest):
        self.renames.append((src, dest))
        self.files[dest] = self.files.pop(src)

    async def remove(self, path):
        self.files.pop(path, None)


class FakeConnection:
    def __init__(self, sftp):
        self.sftp = sftp
        self.commands = []
        self.exit_status = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def start_sftp_client(self):
        return self.sftp

    async def run(self, command, check):
        self.commands.append(command)
        return SimpleNamespace(
            stdout="ok", stderr="", exit_status=self.exit_status
        )


@pytest.fixture
def ssh_backend(monkeypatch):
    sftp = FakeSFTP()
    conn = FakeConnection(sftp)
    calls = []

    def connect(host, **kwargs):
        calls.append((host, kwargs))
        return conn

    monkeypatch.setattr("oleg_commander.tools.ssh.asyncssh.connect", connect)
    return conn, sftp, calls


def make_tool(*, writable=False, max_output_bytes=1024):
    config = Config(
        security=SecurityConfig(
            read_only=not writable,
            require_approval=not writable,
            allowed_ssh_hosts=["park"],
            allowed_ssh_directories={"park": ["/srv/code"]},
        ),
        execution={"timeout": 5, "max_output_bytes": max_output_bytes},
    )
    return SSHTool(SecurityManager(config))


def run(coro):
    return asyncio.run(coro)


def test_ssh_connect_checks_real_known_hosts(ssh_backend):
    _, _, calls = ssh_backend
    result = run(make_tool().ssh_connect("park"))
    assert result.success
    assert result.data["verified"] is True
    assert calls[0][0] == "park"
    assert calls[0][1]["known_hosts"].endswith(".ssh/known_hosts")
    assert calls[0][1]["connect_timeout"] == 5


def test_unknown_host_is_denied_without_network(ssh_backend):
    _, _, calls = ssh_backend
    result = run(make_tool().ssh_connect("wob"))
    assert result.error["code"] == "FORBIDDEN"
    assert not calls


def test_read_only_remote_execution(ssh_backend):
    conn, _, _ = ssh_backend
    assert run(make_tool().ssh_execute("park", "uname", [])).success
    assert conn.commands == ["uname"]
    dangerous = run(make_tool().ssh_execute("park", "rm", ["-rf", "/"]))
    assert dangerous.error["code"] == "FORBIDDEN"
    assert conn.commands == ["uname"]


def test_writable_commands_quote_arguments(ssh_backend):
    conn, _, _ = ssh_backend
    result = run(
        make_tool(writable=True).ssh_execute(
            "park", "printf", ["%s", "hello; rm -rf /"]
        )
    )
    assert result.success
    assert conn.commands == ["printf %s 'hello; rm -rf /'"]


def test_nonzero_remote_command_exit_is_not_success(ssh_backend):
    conn, _, _ = ssh_backend
    conn.exit_status = 2
    result = run(make_tool().ssh_execute("park", "date", []))
    assert not result.success
    assert result.data["exit_code"] == 2


def test_remote_file_read_and_symlink_escape_denied(ssh_backend):
    _, sftp, _ = ssh_backend
    result = run(make_tool().ssh_read_file("park", "/srv/code/readme.txt"))
    assert result.success
    assert result.data["content"] == "hello"

    sftp.links["/srv/code/leak"] = "/etc/shadow"
    result = run(make_tool().ssh_read_file("park", "/srv/code/leak"))
    assert result.error["code"] == "FORBIDDEN"


def test_ssh_paths_reject_traversal_without_connecting(ssh_backend):
    _, _, calls = ssh_backend
    tool = make_tool()
    for path in ("/srv/code/../secret", "/etc/passwd", "relative.txt"):
        result = run(tool.ssh_read_file("park", path))
        assert result.error["code"] == "FORBIDDEN"
    assert not calls


def test_size_limit_is_enforced(ssh_backend):
    _, sftp, _ = ssh_backend
    sftp.files["/srv/code/large"] = b"123456789"
    result = run(
        make_tool(max_output_bytes=8).ssh_read_file("park", "/srv/code/large")
    )
    assert not result.success


def test_write_requires_explicit_unprotected_mode(ssh_backend):
    _, _, calls = ssh_backend
    result = run(make_tool().ssh_write_file("park", "/srv/code/new", "hi"))
    assert result.error["code"] == "READ_ONLY"
    assert not calls


def test_sftp_write_uses_temp_file_and_atomic_rename(ssh_backend):
    _, sftp, _ = ssh_backend
    result = run(
        make_tool(writable=True).ssh_write_file("park", "/srv/code/new", "hi")
    )
    assert result.success
    assert sftp.files["/srv/code/new"] == b"hi"
    assert len(sftp.renames) == 1
    assert sftp.renames[0][0].startswith("/srv/code/new.oleg-commander-")


def test_download_cannot_overwrite_existing_file(ssh_backend, tmp_path):
    target = tmp_path / "existing.txt"
    target.write_text("unchanged")
    tool = make_tool(writable=True)
    tool.security_manager.config.security.allowed_directories = [str(tmp_path)]
    tool.security_manager._allowed_directories = {tmp_path.resolve()}
    result = run(
        tool.ssh_download("park", "/srv/code/readme.txt", str(target))
    )
    assert not result.success
    assert target.read_text() == "unchanged"


def test_no_ssh_directories_means_no_remote_file_access(ssh_backend):
    tool = make_tool()
    tool.security_manager.config.security.allowed_ssh_directories = {}
    result = run(tool.ssh_read_file("park", "/srv/code/readme.txt"))
    assert result.error["code"] == "FORBIDDEN"


def test_missing_ssh_host_list_is_fail_closed():
    security = SecurityManager(Config())
    assert not security.is_ssh_host_allowed("park")
    assert not security.is_ssh_path_allowed("park", "/srv/code")


def test_yaml_config_loading_and_missing_explicit_file(tmp_path, monkeypatch):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text(
        "security:\n"
        "  allowed_ssh_hosts: [park]\n"
        "  allowed_ssh_directories:\n"
        "    park: [/srv/code]\n",
        encoding="utf-8",
    )
    config = Config.load(str(yaml_file))
    assert config.security.allowed_ssh_hosts == ["park"]
    assert config.security.allowed_ssh_directories["park"] == ["/srv/code"]

    with pytest.raises(FileNotFoundError):
        Config.load(str(tmp_path / "missing.yaml"))


def test_invalid_yaml_is_rejected(tmp_path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("[bad, sequence]", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        Config.load(str(yaml_file))
