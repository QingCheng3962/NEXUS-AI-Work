"""后端权限与路径穿越校验。"""

from pathlib import Path

import pytest

from core import security


def test_permission_aliases() -> None:
    assert security.permission_mode("full") == "danger-full-access"
    assert security.permission_mode("read-write") == "workspace-write"
    assert security.permission_mode("unknown") == "read-only"


def test_resolve_in_workspace_blocks_parent_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    with pytest.raises(security.PathTraversalError):
        security.resolve_in_workspace("../secret.txt", workspace)
    assert security.resolve_in_workspace("inside.txt", workspace) == workspace / "inside.txt"


def test_read_only_blocks_write_and_shell(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(security.PermissionDenied):
        security.inspect_tool_call("write_file", {"path": "a.txt"}, workspace, "read-only")
    with pytest.raises(security.PermissionDenied):
        security.inspect_tool_call("pwsh", {"command": "dir"}, workspace, "read-only")


def test_workspace_write_blocks_nested_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(security.PathTraversalError):
        security.inspect_tool_call(
            "read_file", {"path": "../../outside.txt"}, workspace, "workspace-write"
        )
