"""Regression tests for bounded diagnostics and allowlisted admin tools."""

import asyncio
import json
import sys

import pytest

from oleg_commander.config import Config, ExecutionConfig, SecurityConfig
from oleg_commander.security import SecurityManager
from oleg_commander.services.command_service import run_command
from oleg_commander.tools.base import ToolResult
from oleg_commander.tools.docker import DockerTool
from oleg_commander.tools.processes import ProcessTool
from oleg_commander.tools.systemd import SystemdTool


def run(coro):
    return asyncio.run(coro)


def security(*, writable=False, services=None, containers=None):
    return SecurityManager(
        Config(
            security=SecurityConfig(
                read_only=not writable,
                require_approval=not writable,
                allowed_systemd_services=services or [],
                allowed_docker_containers=containers or [],
            ),
            execution=ExecutionConfig(timeout=2, max_output_bytes=4096),
        )
    )


@pytest.fixture
def command_stub(monkeypatch):
    calls = []
    results = []

    async def fake_run(argv, *, timeout, max_output_bytes):
        calls.append((argv, timeout, max_output_bytes))
        if results:
            return results.pop(0)
        return ToolResult(success=True, data={"exit_code": 0, "stdout": "", "stderr": ""})

    for module in (
        "oleg_commander.tools.systemd",
        "oleg_commander.tools.docker",
        "oleg_commander.tools.processes",
    ):
        monkeypatch.setattr(f"{module}.run_command", fake_run)
    return calls, results


def output(stdout="", stderr="", *, exit_code=0):
    return ToolResult(
        success=exit_code == 0,
        data={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
        error=None if exit_code == 0 else {"code": "COMMAND_FAILED", "message": "fail"},
    )


def test_systemd_requires_explicit_allowlist(command_stub):
    calls, _ = command_stub
    tool = SystemdTool(security())
    result = run(tool.systemd_status("ssh.service"))
    assert result.error["code"] == "FORBIDDEN"
    result = run(
        SystemdTool(security(services=["ssh.service"])).systemd_status(
            "-ssh.service"
        )
    )
    assert result.error["code"] == "FORBIDDEN"
    assert not calls


def test_systemd_status_only_reads_specific_properties(command_stub):
    calls, results = command_stub
    results.append(output("Id=ollama.service\nActiveState=active\nMainPID=120\nSecret=hidden\n"))
    tool = SystemdTool(security(services=["ollama.service"]))
    result = run(tool.systemd_status("ollama.service"))
    assert result.success
    assert result.data["status"] == {
        "Id": "ollama.service", "ActiveState": "active", "MainPID": "120"
    }
    assert "Secret" not in str(result.data)
    assert calls[0][0] == (
        "systemctl", "show", "--no-pager",
        "--property=Id,LoadState,ActiveState,SubState,MainPID",
        "ollama.service",
    )


def test_systemd_logs_validate_count_and_use_journalctl(command_stub):
    calls, results = command_stub
    tool = SystemdTool(security(services=["ollama.service"]))
    assert run(tool.systemd_logs("ollama.service", 0)).error["code"] == "INVALID_ARGUMENT"
    assert run(tool.systemd_logs("ollama.service", True)).error["code"] == "INVALID_ARGUMENT"
    assert not calls
    results.append(output("log line\n"))
    result = run(tool.systemd_logs("ollama.service", 25))
    assert result.data["logs"] == "log line\n"
    assert "--lines=25" in calls[0][0]
    assert "--unit=ollama.service" in calls[0][0]


def test_systemd_restart_is_opt_in(command_stub):
    calls, _ = command_stub
    tool = SystemdTool(security(services=["ollama.service"]))
    assert run(tool.systemd_restart("ollama.service")).error["code"] == "READ_ONLY"
    assert not calls
    writable = SystemdTool(security(writable=True, services=["ollama.service"]))
    assert run(writable.systemd_restart("ollama.service")).success
    assert calls[0][0] == (
        "systemctl", "restart", "--no-ask-password", "ollama.service"
    )


def test_docker_ps_filters_containers_and_sensitive_fields(command_stub):
    calls, results = command_stub
    tool = DockerTool(security(containers=["api"]))
    rows = [
        {
            "ID": "abc", "Names": "api", "Image": "myapp:latest",
            "Status": "Up", "State": "running",
            "Command": "python manage.py runserver --secret=x",
        },
        {"ID": "def", "Names": "db", "Image": "postgres", "Status": "Up"},
    ]
    results.append(output("\n".join(json.dumps(row) for row in rows)))
    result = run(tool.docker_ps())
    assert result.success
    assert len(result.data["containers"]) == 1
    assert result.data["containers"][0]["names"] == ["api"]
    assert "secret" not in str(result.data)
    assert calls[0][0] == (
        "docker", "ps", "--all", "--format", "{{json .}}"
    )


def test_empty_docker_allowlist_avoids_spawning_docker(command_stub):
    calls, _ = command_stub
    result = run(DockerTool(security()).docker_ps())
    assert result.data == {"containers": []}
    assert not calls


def test_docker_disallows_unlisted_or_option_like_containers(command_stub):
    calls, _ = command_stub
    tool = DockerTool(security(containers=["api"]))
    for name in ("db", "--all", "../api"):
        assert run(tool.docker_logs(name)).error["code"] == "FORBIDDEN"
    assert not calls


def test_docker_inspect_exposes_only_projected_fields(command_stub):
    calls, results = command_stub
    tool = DockerTool(security(containers=["api"]))
    results.append(output('"/api"|"myapp:1"|"running"\n'))
    result = run(tool.docker_inspect("api"))
    assert result.data == {
        "container": "api", "name": "/api",
        "image": "myapp:1", "state": "running",
    }
    assert "inspect" in calls[0][0]
    assert ".Config.Env" not in str(calls[0])


def test_docker_logs_and_restart_are_gated(command_stub):
    calls, results = command_stub
    tool = DockerTool(security(containers=["api"]))
    assert run(tool.docker_restart("api")).error["code"] == "READ_ONLY"
    assert not calls
    results.append(output("out", "err"))
    assert run(tool.docker_logs("api", lines=10)).data["stderr"] == "err"
    assert calls[0][0] == ("docker", "logs", "--tail", "10", "--", "api")
    assert run(tool.docker_logs("api", lines=1001)).error["code"] == "INVALID_ARGUMENT"
    assert run(DockerTool(security(writable=True, containers=["api"])).docker_restart("api")).success


def test_process_list_and_pid_lookup_do_not_expose_args(command_stub):
    calls, results = command_stub
    tool = ProcessTool(security())
    results.append(output(" 123 2 S 01:25 python3\n"))
    found = run(tool.list_processes())
    assert found.data["processes"][0]["pid"] == 123
    assert found.data["processes"][0]["name"] == "python3"
    results.append(output("123 2 S 01:25 python3\n"))
    assert run(tool.get_process_info(123)).data["ppid"] == 2
    assert calls[0][0] == (
        "ps", "-eo", "pid=,ppid=,stat=,etime=,comm="
    )
    assert calls[1][0] == (
        "ps", "-p", "123", "-o", "pid=,ppid=,stat=,etime=,comm="
    )


def test_process_kill_is_disabled_even_if_writable(command_stub):
    calls, _ = command_stub
    tool = ProcessTool(security(writable=True))
    assert run(tool.kill_process(123)).error["code"] == "NOT_IMPLEMENTED"
    assert run(tool.get_process_info(-1)).error["code"] == "INVALID_ARGUMENT"
    assert not calls


def test_command_runner_returns_exit_code_and_output():
    result = run(
        run_command(
            [sys.executable, "-c", "print('ok')"],
            timeout=2,
            max_output_bytes=1024,
        )
    )
    assert result.success
    assert result.data["stdout"] == "ok\n"


def test_command_runner_rejects_missing_executable():
    result = run(
        run_command(
            ["__oleg_commander_not_a_command__"],
            timeout=2,
            max_output_bytes=1024,
        )
    )
    assert result.error["code"] == "NOT_INSTALLED"


def test_command_runner_bounds_output():
    result = run(
        run_command(
            [sys.executable, "-c", "print('x' * 100000)"],
            timeout=2,
            max_output_bytes=64,
        )
    )
    assert result.error["code"] == "OUTPUT_LIMIT"


def test_command_runner_times_out():
    result = run(
        run_command(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            timeout=0.05,
            max_output_bytes=1024,
        )
    )
    assert result.error["code"] == "TIMEOUT"
