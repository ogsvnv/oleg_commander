"""Security regressions for descriptor-relative filesystem MCP tools."""

import asyncio
from pathlib import Path

from oleg_commander.config import Config, ExecutionConfig, SecurityConfig
from oleg_commander.security import SecurityManager
from oleg_commander.tools.filesystem import FilesystemTool


def run(coro):
    return asyncio.run(coro)


def tool_for(directory, *, writable=False, cap=512):
    return FilesystemTool(
        SecurityManager(
            Config(
                security=SecurityConfig(
                    allowed_directories=[str(directory)],
                    read_only=not writable,
                    require_approval=not writable,
                ),
                execution=ExecutionConfig(timeout=2, max_output_bytes=cap),
            )
        )
    )


def test_omitted_allowlist_denies_home_and_directory(tmp_path):
    security = SecurityManager(Config())
    assert not security.is_path_allowed(str(Path.home()))
    assert not security.is_path_allowed(str(tmp_path))
    result = run(FilesystemTool(security).list_directory(str(tmp_path)))
    assert result.error["code"] == "FORBIDDEN"


def test_relative_parent_traversal_is_rejected(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "ok.txt").write_text("ok")
    tool = tool_for(allowed)
    attempt = f"{allowed}/folder/../ok.txt"
    result = run(tool.read_file(attempt))
    assert result.error["code"] == "FORBIDDEN"


def test_read_write_edit_copy_move_and_delete(tmp_path):
    tool = tool_for(tmp_path, writable=True)
    nested = tmp_path / "new" / "folder"
    assert run(tool.create_directory(str(nested))).success
    path = nested / "text.txt"
    assert run(tool.write_file(str(path), "Привет!")).success
    assert run(tool.read_file(str(path), 1, 3)).data["content"] == "рив"
    assert run(tool.edit_file(str(path), "Привет", "Пока")).success
    assert path.read_text() == "Пока!"
    copied = nested / "copy.txt"
    assert run(tool.copy_file(str(path), str(copied))).success
    moved = nested / "moved.txt"
    assert run(tool.move_file(str(copied), str(moved))).success
    assert not copied.exists()
    assert moved.read_text() == "Пока!"
    assert run(tool.delete_file(str(moved))).success
    assert not moved.exists()


def test_read_only_blocks_all_mutations(tmp_path):
    tool = tool_for(tmp_path)
    file_path = tmp_path / "read.txt"
    file_path.write_text("old")
    assert run(tool.read_file(str(file_path))).success
    operations = [
        tool.write_file(str(file_path), "new"),
        tool.edit_file(str(file_path), "old", "new"),
        tool.delete_file(str(file_path)),
        tool.create_directory(str(tmp_path / "folder")),
        tool.copy_file(str(file_path), str(tmp_path / "copy")),
        tool.move_file(str(file_path), str(tmp_path / "moved")),
    ]
    for operation in operations:
        assert run(operation).error["code"] == "READ_ONLY"
    assert file_path.read_text() == "old"


def test_existing_symlink_outside_is_not_read_or_written(tmp_path):
    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("CONFIDENTIAL")
    link = allowed / "link.txt"
    link.symlink_to(secret)
    tool = tool_for(allowed, writable=True)
    for response in [
        run(tool.read_file(str(link))),
        run(tool.write_file(str(link), "changed")),
        run(tool.edit_file(str(link), "CONFIDENTIAL", "changed")),
        run(tool.delete_file(str(link))),
        run(tool.copy_file(str(link), str(allowed / "copy.txt"))),
        run(tool.move_file(str(link), str(allowed / "moved.txt"))),
        run(tool.get_file_info(str(link))),
    ]:
        assert not response.success
    assert secret.read_text() == "CONFIDENTIAL"
    assert link.is_symlink()


def test_symlinked_parent_denies_all_paths(tmp_path):
    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("outside")
    (allowed / "folder").symlink_to(outside, target_is_directory=True)
    tool = tool_for(allowed, writable=True)
    assert not run(tool.read_file(str(allowed / "folder" / "secret.txt"))).success
    assert not run(tool.write_file(str(allowed / "folder" / "created"), "oops")).success
    assert not run(tool.create_directory(str(allowed / "folder" / "nested"))).success
    assert not (outside / "created").exists()
    assert not (outside / "nested").exists()


def test_symlinks_not_followed_during_search_or_listing(tmp_path):
    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "private.txt").write_text("SENSITIVE")
    (allowed / "linked").symlink_to(outside, target_is_directory=True)
    (allowed / "inside.txt").write_text("SENSITIVE")
    tool = tool_for(allowed)
    files = run(tool.search_content(str(allowed), "SENSITIVE"))
    assert files.success
    assert [Path(d["path"]).name for d in files.data["files"]] == ["inside.txt"]
    names = [d["name"] for d in run(tool.list_directory(str(allowed))).data["items"]]
    assert "linked" not in names
    assert "inside.txt" in names


def test_file_limits_and_multi_file_cumulative_cap(tmp_path):
    tool = tool_for(tmp_path, cap=16)
    big = tmp_path / "big.txt"
    big.write_text("x" * 17)
    assert not run(tool.read_file(str(big))).success
    small1, small2 = tmp_path / "one", tmp_path / "two"
    small1.write_text("1234567890")
    small2.write_text("abcdefghij")
    result = run(tool.read_multiple_files([str(small1), str(small2)]))
    assert result.success
    assert result.data["results"][0]["success"]
    assert not result.data["results"][1]["success"]
    assert run(tool.read_multiple_files([str(small1)] * 21)).error["code"] == "INVALID_ARGUMENT"


def test_limits_prevent_large_writes(tmp_path):
    tool = tool_for(tmp_path, writable=True, cap=8)
    target = tmp_path / "test"
    target.write_text("unchanged")
    assert not run(tool.write_file(str(target), "x" * 9)).success
    assert target.read_text() == "unchanged"
    assert not any(p.name.startswith(".oleg-tmp-") for p in tmp_path.iterdir())


def test_atomic_edit_detects_concurrent_edit(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    path = allowed / "doc"
    path.write_text("original")
    tool = tool_for(allowed, writable=True)
    from oleg_commander.services import secure_filesystem

    original_replace = secure_filesystem.SecureFilesystem._atomic_replace

    def raced(self, parent, name, content, expected=None):
        if expected is not None:
            path.write_text("changed by someone else")
        return original_replace(self, parent, name, content, expected=expected)

    monkeypatch.setattr(secure_filesystem.SecureFilesystem, "_atomic_replace", raced)
    result = run(tool.edit_file(str(path), "original", "edited"))
    assert result.error["code"] == "CONFLICT"
    assert path.read_text() == "changed by someone else"


def test_entry_substitution_with_symlink_cannot_escape(tmp_path, monkeypatch):
    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    target = allowed / "file"
    target.write_text("before")
    external = outside / "secret"
    external.write_text("secret")
    tool = tool_for(allowed, writable=True)
    from oleg_commander.services import secure_filesystem

    native_replace = secure_filesystem.os.replace

    def swap_before_rename(src, dst, **kwargs):
        target.unlink()
        target.symlink_to(external)
        return native_replace(src, dst, **kwargs)

    monkeypatch.setattr(secure_filesystem.os, "replace", swap_before_rename)
    result = run(tool.write_file(str(target), "approved"))
    assert result.success
    assert target.read_text() == "approved"
    assert external.read_text() == "secret"
    assert not target.is_symlink()


def test_path_limit_and_basic_search(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hello.py").write_text("print('hello')")
    tool = tool_for(tmp_path)
    matched = run(tool.search_files(str(tmp_path), "*.py"))
    assert [m["name"] for m in matched.data["files"]] == ["hello.py"]
    result = run(tool.list_directory(str(tmp_path), 9))
    assert result.error["code"] == "INVALID_ARGUMENT"
    info = run(tool.get_file_info(str(nested / "hello.py")))
    assert info.data["info"]["is_file"]


def test_ancestor_symlink_swap_cannot_retarget_approved_root(tmp_path):
    """Changing an ancestor after setup must not broaden the allowlist."""
    parent = tmp_path / "anchor"
    approved = parent / "approved"
    approved.mkdir(parents=True)
    (approved / "ok.txt").write_text("original")
    tool = tool_for(approved, writable=True)

    # Move the original subtree, then point the old ancestor at a completely
    # different subtree which contains a matching relative filename.
    replacement = tmp_path / "replacement"
    (replacement / "approved").mkdir(parents=True)
    outside = replacement / "approved" / "secret.txt"
    outside.write_text("private")
    parent.rename(tmp_path / "moved-anchor")
    parent.symlink_to(replacement, target_is_directory=True)

    via_old_path = run(
        tool.read_file(str(parent / "approved" / "secret.txt"))
    )
    assert via_old_path.error["code"] == "FORBIDDEN"

    via_actual_path = run(tool.read_file(str(outside)))
    assert via_actual_path.error["code"] == "FORBIDDEN"

    overwrite = run(
        tool.write_file(str(parent / "approved" / "secret.txt"), "leaked")
    )
    assert overwrite.error["code"] == "FORBIDDEN"
    assert outside.read_text() == "private"


def test_direct_symlink_is_not_accepted_as_approved_root(tmp_path):
    """A symlink supplied as a root is never silently followed at use time."""
    from oleg_commander.services.secure_filesystem import SecureFilesystem

    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "secret").write_text("secret")
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)

    filesystem = SecureFilesystem([link], max_bytes=1024)
    try:
        filesystem.read_bytes(str(link / "secret"))
    except (PermissionError, OSError):
        pass
    else:
        raise AssertionError("Root symlink must be denied")
