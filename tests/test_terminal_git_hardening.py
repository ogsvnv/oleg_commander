"""Real local terminal/Git tests: bounded subprocesses, argv, path boundaries."""

import asyncio
import os
import subprocess
from pathlib import Path

from oleg_commander.config import Config, ExecutionConfig, SecurityConfig
from oleg_commander.security import SecurityManager
from oleg_commander.tools.git import GitTool
from oleg_commander.tools.terminal import TerminalTool


def run(coro):
    return asyncio.run(coro)


def security(tmp_path, *, writable=False, cap=4096):
    return SecurityManager(
        Config(
            security=SecurityConfig(
                allowed_directories=[str(tmp_path)],
                read_only=not writable,
                require_approval=not writable,
            ),
            execution=ExecutionConfig(timeout=2, max_output_bytes=cap),
        )
    )


def repo(tmp_path):
    directory = tmp_path / "repo"
    directory.mkdir()
    subprocess.run(
        ["git", "init", "-q", str(directory)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    (directory / "hello.py").write_text("print('test')\n")
    return directory


def test_readonly_terminal_executes_safe_command(tmp_path):
    tool = TerminalTool(security(tmp_path))
    result = run(tool.execute_command("pwd", [], cwd=str(tmp_path), timeout=1))
    assert result.success
    assert str(tmp_path) in result.data["stdout"]
    assert result.data["exit_code"] == 0


def test_terminal_denies_shell_and_args_without_approval(tmp_path):
    tool = TerminalTool(security(tmp_path))
    for executable, args in (
        ("sh", ["-c", "echo no"]),
        ("date", ["--file=/etc/shadow"]),
        ("/bin/date", []),
        ("python3", ["-c", "print('no')"]),
    ):
        result = run(tool.execute_command(executable, args, cwd=str(tmp_path)))
        assert not result.success


def test_terminal_needs_explicit_directory_allowlist():
    tool = TerminalTool(SecurityManager(Config()))
    result = run(tool.execute_command("pwd", []))
    assert result.error["code"] == "FORBIDDEN"


def test_terminal_symlinked_parent_does_not_escape(tmp_path):
    working = tmp_path / "allowed"
    external = tmp_path / "external"
    working.mkdir()
    external.mkdir()
    (working / "shortcut").symlink_to(external, target_is_directory=True)
    tool = TerminalTool(security(working))
    result = run(tool.execute_command("pwd", [], cwd=str(working / "shortcut")))
    assert result.error["code"] == "FORBIDDEN"


def test_terminal_output_limit_applies_to_approved_command(tmp_path):
    tool = TerminalTool(security(tmp_path, writable=True, cap=64))
    result = run(
        tool.execute_command(
            "python3", ["-c", "print('x' * 4000)"],
            cwd=str(tmp_path), timeout=2,
        )
    )
    assert result.error["code"] == "OUTPUT_LIMIT"


def test_terminal_timeout_rejects_invalid_bounds(tmp_path):
    tool = TerminalTool(security(tmp_path, writable=True))
    for timeout in (0, 3, -1, True, "30"):
        result = run(tool.execute_command("date", [], timeout=timeout))
        assert result.error["code"] == "INVALID_ARGUMENT"


def test_git_readonly_status_and_log(tmp_path):
    directory = repo(tmp_path)
    tool = GitTool(security(tmp_path))
    result = run(tool.git_status(str(directory)))
    assert result.success
    assert "hello.py" in result.data["status"]
    missing = run(tool.git_log(str(directory)))
    assert not missing.success
    assert missing.error["code"] == "COMMAND_FAILED"


def test_git_limit_and_invalid_branch_names(tmp_path):
    directory = repo(tmp_path)
    tool = GitTool(security(tmp_path, writable=True))
    for limit in (-1, 0, True, 101):
        assert run(tool.git_log(str(directory), limit)).error["code"] == "INVALID_ARGUMENT"
    for name in ("-C", "../escape", "feature//oops", ".lock"):
        assert run(tool.git_create_branch(str(directory), name)).error["code"] == "INVALID_ARGUMENT"


def test_git_add_pathspecs_reject_option_and_traversal(tmp_path):
    directory = repo(tmp_path)
    tool = GitTool(security(tmp_path, writable=True))
    for pathspec in ("--all", "../../etc/passwd", "/etc/passwd", "bad\x00name"):
        result = run(tool.git_add(str(directory), [pathspec]))
        assert result.error["code"] == "INVALID_ARGUMENT"


def test_git_add_is_real_and_uses_safe_pathspec(tmp_path):
    directory = repo(tmp_path)
    tool = GitTool(security(tmp_path, writable=True))
    assert run(tool.git_add(str(directory), ["hello.py"])).success
    result = run(tool.git_status(str(directory)))
    assert result.success
    assert "A  hello.py" in result.data["status"]


def test_git_denies_repo_symlink(tmp_path):
    actual = repo(tmp_path)
    link = tmp_path / "linked"
    link.symlink_to(actual, target_is_directory=True)
    result = run(GitTool(security(tmp_path)).git_status(str(link)))
    assert result.error["code"] == "FORBIDDEN"


def test_git_denies_external_repo_and_missing_allowlist(tmp_path):
    actual = repo(tmp_path)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    result = run(GitTool(security(allowed)).git_status(str(actual)))
    assert result.error["code"] == "FORBIDDEN"


def test_git_remote_sync_does_not_run_even_writable(tmp_path):
    directory = repo(tmp_path)
    tool = GitTool(security(tmp_path, writable=True))
    assert run(tool.git_pull(str(directory))).error["code"] == "REMOTE_DISABLED"
    assert run(tool.git_push(str(directory))).error["code"] == "REMOTE_DISABLED"


def test_git_read_only_denies_mutations(tmp_path):
    directory = repo(tmp_path)
    tool = GitTool(security(tmp_path))
    assert run(tool.git_add(str(directory), ["hello.py"])).error["code"] == "READ_ONLY"
    assert run(tool.git_pull(str(directory))).error["code"] == "READ_ONLY"


def test_git_non_git_directory_is_denied(tmp_path):
    result = run(GitTool(security(tmp_path)).git_status(str(tmp_path)))
    assert result.error["code"] == "FORBIDDEN"
