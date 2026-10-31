"""后端安全边界：权限映射、工作区路径规范化和工具调用硬拦截。

这些检查刻意放在核心层，而不是只依赖界面按钮：
- 任何任务进入 DSH 前都必须通过权限与工作区校验；
- 文件路径先用 ``os.path.normpath`` 规范化，再解析真实路径；
- 读写模式下，AI 工具参数里的相对路径不能逃逸工作区；
- 只读模式下，写入/命令类工具直接拒绝，不等待 DSH 授权。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable

from . import settings


class SecurityError(RuntimeError):
    """可展示给用户的安全边界错误。"""


class PermissionDenied(SecurityError):
    """当前权限不允许该操作。"""


class PathTraversalError(SecurityError):
    """路径越过了工作区边界。"""


PERMISSION_ALIASES = {
    "read-only": "read-only",
    "readonly": "read-only",
    "read": "read-only",
    "只读": "read-only",
    "workspace-write": "workspace-write",
    "read-write": "workspace-write",
    "readwrite": "workspace-write",
    "write": "workspace-write",
    "读写": "workspace-write",
    "danger-full-access": "danger-full-access",
    "full": "danger-full-access",
    "full-access": "danger-full-access",
    "完全控制": "danger-full-access",
}

_READ_ONLY_BLOCKED = (
    "write",
    "edit",
    "patch",
    "replace",
    "create",
    "delete",
    "remove",
    "move",
    "rename",
    "mkdir",
    "rmdir",
    "chmod",
    "chown",
    "truncate",
    "append",
    "shell",
    "bash",
    "powershell",
    "pwsh",
    "exec",
    "command",
    "terminal",
    "process",
    "spawn",
    "apply",
)

_PATH_KEYS = {
    "path",
    "paths",
    "file",
    "files",
    "filepath",
    "file_path",
    "filename",
    "file_name",
    "dir",
    "directory",
    "folder",
    "cwd",
    "workdir",
    "workspace",
    "root",
    "target",
    "source",
    "src",
    "dest",
    "destination",
    "output",
    "output_path",
    "input_path",
    "save_path",
    "pattern",
    "glob",
}
_COMMAND_KEYS = {"command", "cmd", "script", "shell", "powershell", "bash"}
_PATH_TOKEN = re.compile(
    r"""(?P<token>(?:[A-Za-z]:[\\/]|\\\\|(?:\.\.?[\\/])|~[\\/]|/)[^\s"'`|&;<>()]*)"""
)


def permission_mode(value: str | None, default: str = "read-only") -> str:
    """把 UI 值/DSH 值统一成 DSH 的三级权限名。"""
    return PERMISSION_ALIASES.get(str(value or "").strip().lower(), default)


def can_write(permission: str | None) -> bool:
    return permission_mode(permission) in ("workspace-write", "danger-full-access")


def workspace_root(value: str | Path | None = None, *, create: bool = True) -> Path:
    """返回规范化后的工作区根目录。"""
    raw = Path(str(value or settings.get("dsh.workspace") or settings.WORKSPACE_DIR))
    path = raw.expanduser()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    # 先 normpath，再 resolve，避免 ../ 与符号链接绕过。
    normalized = Path(os.path.normpath(str(path)))
    return normalized.resolve(strict=False)


def ensure_workspace(value: str | Path | None = None) -> Path:
    root = workspace_root(value)
    if not root.is_dir():
        raise SecurityError(f"工作区不存在或不是目录：{root}")
    return root


def resolve_in_workspace(
    value: str | Path,
    workspace: str | Path | None = None,
    *,
    allow_workspace: bool = True,
) -> Path:
    """解析路径，并确保它仍然位于工作区内部。

    相对路径按工作区解析；绝对路径也必须是工作区内的路径。符号链接按
    解析后的真实路径判断，不使用字符串前缀比较。
    """
    root = workspace_root(workspace, create=False)
    raw = Path(str(value)).expanduser()
    if not raw.is_absolute():
        raw = root / raw
    normalized = Path(os.path.normpath(str(raw)))
    resolved = normalized.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathTraversalError(f"路径越出工作区：{value}") from exc
    if not allow_workspace and resolved == root:
        raise PathTraversalError("这个操作不能直接作用于工作区根目录。")
    return resolved


def is_within(path: str | Path, workspace: str | Path | None = None) -> bool:
    try:
        resolve_in_workspace(path, workspace)
        return True
    except SecurityError:
        return False


def _tool_name(tool: str) -> str:
    return str(tool or "").strip().lower()


def _is_read_only_blocked(tool: str) -> bool:
    name = _tool_name(tool)
    return any(word in name for word in _READ_ONLY_BLOCKED)


def _walk_values(value: Any, key: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _walk_values(child, str(child_key).lower())
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_values(child, key)
    else:
        yield key, value


def _scan_command(command: str, workspace: Path, original: str) -> None:
    for match in _PATH_TOKEN.finditer(command):
        token = match.group("token").strip("\"'")
        if not token or token.startswith("//"):
            continue
        # Windows 命令常见 /F、/PID 这类参数，不是文件路径。
        if re.fullmatch(r"/[A-Za-z]{1,4}", token):
            continue
        try:
            resolve_in_workspace(token, workspace)
        except PathTraversalError as exc:
            raise PathTraversalError(
                f"命令包含工作区外路径：{token}"
            ) from exc
    # 兜底：命令里出现父目录跳转时直接拒绝。
    if re.search(r"(^|[\\/])\.\.([\\/]|$)", command):
        raise PathTraversalError(f"命令包含父目录跳转：{original[:120]}")


def inspect_tool_call(
    tool: str,
    tool_input: Any,
    workspace: str | Path | None = None,
    permission: str = "read-only",
) -> None:
    """在工具执行前检查参数。

    DSH 自己的权限层仍然生效；这里额外做应用层硬拦截，防止 UI 绕过或
    AI 构造路径穿越参数。
    """
    mode = permission_mode(permission)
    root = workspace_root(workspace, create=False)

    if mode == "read-only" and _is_read_only_blocked(tool):
        raise PermissionDenied(f"只读模式不允许调用工具：{tool}")

    if isinstance(tool_input, str):
        text = tool_input
        values: list[tuple[str, Any]] = [("command" if _tool_name(tool) in _COMMAND_KEYS or "shell" in _tool_name(tool) else "path", text)]
    else:
        values = list(_walk_values(tool_input))

    for key, value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        text = value.strip()
        if mode != "danger-full-access" and (key in _PATH_KEYS or key in _COMMAND_KEYS):
            if key in _COMMAND_KEYS:
                _scan_command(text, root, text)
            else:
                resolve_in_workspace(text, root)
        elif mode != "danger-full-access" and key in _COMMAND_KEYS:
            _scan_command(text, root, text)

    # 工具名本身也可能暗示写入；读写模式仍要求路径在工作区内。
    if mode == "read-only" and _is_read_only_blocked(tool):
        raise PermissionDenied(f"只读模式不允许调用工具：{tool}")


def task_timeout_seconds() -> float:
    try:
        value = float(settings.get("dsh.task_timeout", 300) or 300)
    except (TypeError, ValueError):
        value = 300.0
    return max(15.0, min(value, 3600.0))


def command_timeout_seconds() -> float:
    try:
        value = float(settings.get("dsh.command_timeout", 30) or 30)
    except (TypeError, ValueError):
        value = 30.0
    return max(5.0, min(value, 300.0))
