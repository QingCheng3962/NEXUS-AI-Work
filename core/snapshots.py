"""工作区快照与红绿 Diff。

每个会修改文件的任务开始前，把工作区复制到 ``data/snapshots/<id>/``；
任务结束后用 ``difflib`` 比较快照与当前文件，界面可以接受修改或整体撤销。
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import security, settings

SNAPSHOT_ROOT = settings.DATA_DIR / "snapshots"
EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".anvil-snapshots",
    "snapshots",
}
TEXT_LIMIT = 512 * 1024


@dataclass
class SnapshotInfo:
    id: str
    workspace: str
    created_at: float
    file_count: int
    total_bytes: int
    skipped: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace": self.workspace,
            "created_at": self.created_at,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "skipped": self.skipped,
        }


@dataclass
class FileDiff:
    path: str
    kind: str  # added / modified / deleted
    additions: int = 0
    deletions: int = 0
    binary: bool = False
    diff: str = ""
    old_size: int = 0
    new_size: int = 0


def _max_bytes() -> int:
    try:
        mb = float(settings.get("dsh.snapshot_max_mb", 256) or 256)
    except (TypeError, ValueError):
        mb = 256.0
    return int(max(16.0, min(mb, 2048.0)) * 1024 * 1024)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:4096]


def _walk_files(root: Path):
    """遍历工作区文件，跳过依赖/版本库目录和符号链接。"""
    snapshot_dir = Path(SNAPSHOT_ROOT).resolve(strict=False)
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            item for item in dirs if item.lower() not in EXCLUDED_DIRS
        )
        current_path = Path(current)
        try:
            current_resolved = current_path.resolve(strict=False)
            if current_resolved == snapshot_dir or snapshot_dir in current_resolved.parents:
                dirs[:] = []
                continue
        except OSError:
            pass
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                continue
            try:
                resolved = path.resolve(strict=False)
                resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            yield path, resolved


def snapshot_root() -> Path:
    root = Path(SNAPSHOT_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def capture(workspace: str | Path, *, label: str = "") -> SnapshotInfo:
    root = security.ensure_workspace(workspace)
    snapshot_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    destination = snapshot_root() / snapshot_id
    files_dir = destination / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "id": snapshot_id,
        "label": label,
        "workspace": str(root),
        "created_at": time.time(),
        "files": [],
        "skipped": [],
    }
    total = 0
    limit = _max_bytes()
    for path, resolved in _walk_files(root):
        relative = resolved.relative_to(root)
        try:
            size = resolved.stat().st_size
        except OSError as exc:
            manifest["skipped"].append({"path": relative.as_posix(), "reason": str(exc)})
            continue
        if total + size > limit:
            manifest["skipped"].append(
                {"path": relative.as_posix(), "reason": "超过快照容量上限"}
            )
            continue
        target = files_dir / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, target)
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as exc:
            manifest["skipped"].append({"path": relative.as_posix(), "reason": str(exc)})
            continue
        total += size
        manifest["files"].append(
            {
                "path": relative.as_posix(),
                "size": size,
                "sha256": digest,
            }
        )
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return SnapshotInfo(
        id=snapshot_id,
        workspace=str(root),
        created_at=float(manifest["created_at"]),
        file_count=len(manifest["files"]),
        total_bytes=total,
        skipped=manifest["skipped"],
    )


def load_manifest(snapshot_id: str) -> dict[str, Any]:
    path = snapshot_root() / snapshot_id / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FileNotFoundError("快照不存在或已损坏。") from exc
    if not isinstance(data, dict):
        raise FileNotFoundError("快照不存在或已损坏。")
    return data


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > TEXT_LIMIT or _is_binary(data):
        return None
    return data.decode("utf-8", "replace")


def _unified(old_path: Path, new_path: Path, relative: str) -> tuple[str, int, int, bool]:
    old_data = old_path.read_bytes() if old_path.exists() else b""
    new_data = new_path.read_bytes() if new_path.exists() else b""
    if _is_binary(old_data) or _is_binary(new_data):
        return "", 0, 0, True
    if len(old_data) > TEXT_LIMIT or len(new_data) > TEXT_LIMIT:
        return "", 0, 0, True
    old_text = old_data.decode("utf-8", "replace")
    new_text = new_data.decode("utf-8", "replace")
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    chunks = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"原文件 · {relative}",
            tofile=f"修改后 · {relative}",
            lineterm="",
            n=3,
        )
    )
    additions = sum(1 for line in chunks if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in chunks if line.startswith("-") and not line.startswith("---"))
    return "\n".join(chunks), additions, deletions, False


def diff(snapshot_id: str) -> list[FileDiff]:
    manifest = load_manifest(snapshot_id)
    workspace = security.ensure_workspace(manifest.get("workspace") or "")
    files_dir = snapshot_root() / snapshot_id / "files"
    old_files = {
        str(item.get("path") or ""): item
        for item in manifest.get("files", [])
        if isinstance(item, dict) and item.get("path")
    }
    skipped = {
        str(item.get("path") or "")
        for item in manifest.get("skipped", [])
        if isinstance(item, dict)
    }
    current: dict[str, Path] = {}
    for path, resolved in _walk_files(workspace):
        relative = resolved.relative_to(workspace).as_posix()
        if relative in skipped:
            continue
        current[relative] = resolved

    results: list[FileDiff] = []
    for relative in sorted(set(old_files) | set(current)):
        old_item = old_files.get(relative)
        new_path = current.get(relative)
        old_path = files_dir / relative
        if old_item is None:
            text, additions, deletions, binary = _unified(Path("__missing__"), new_path, relative)  # type: ignore[arg-type]
            results.append(
                FileDiff(
                    path=relative,
                    kind="added",
                    additions=additions,
                    deletions=deletions,
                    binary=binary,
                    diff=text,
                    new_size=new_path.stat().st_size if new_path else 0,
                )
            )
            continue
        if new_path is None:
            text, additions, deletions, binary = _unified(old_path, Path("__missing__"), relative)  # type: ignore[arg-type]
            results.append(
                FileDiff(
                    path=relative,
                    kind="deleted",
                    additions=additions,
                    deletions=deletions,
                    binary=binary,
                    diff=text,
                    old_size=int(old_item.get("size") or 0),
                )
            )
            continue
        old_bytes = old_path.read_bytes() if old_path.exists() else b""
        new_bytes = new_path.read_bytes()
        if _hash(old_bytes) == _hash(new_bytes):
            continue
        text, additions, deletions, binary = _unified(old_path, new_path, relative)
        results.append(
            FileDiff(
                path=relative,
                kind="modified",
                additions=additions,
                deletions=deletions,
                binary=binary,
                diff=text,
                old_size=len(old_bytes),
                new_size=len(new_bytes),
            )
        )
    return results


def restore(snapshot_id: str) -> tuple[bool, str]:
    """恢复快照。返回 (是否完全恢复, 提示)。"""
    manifest = load_manifest(snapshot_id)
    workspace = security.ensure_workspace(manifest.get("workspace") or "")
    files_dir = snapshot_root() / snapshot_id / "files"
    old_files = {
        str(item.get("path") or ""): item
        for item in manifest.get("files", [])
        if isinstance(item, dict) and item.get("path")
    }
    skipped = {
        str(item.get("path") or "")
        for item in manifest.get("skipped", [])
        if isinstance(item, dict)
    }
    # 删除任务中新创建、且快照中没有记录的文件。
    for path, resolved in list(_walk_files(workspace)):
        relative = resolved.relative_to(workspace).as_posix()
        if relative not in old_files and relative not in skipped:
            try:
                resolved.unlink()
            except OSError:
                pass
    restored = 0
    missing: list[str] = []
    for relative in old_files:
        source = files_dir / relative
        if not source.exists():
            missing.append(relative)
            continue
        try:
            destination = security.resolve_in_workspace(relative, workspace)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            restored += 1
        except (OSError, security.SecurityError):
            missing.append(relative)
    discard(snapshot_id)
    if missing:
        return False, f"已恢复 {restored} 个文件，{len(missing)} 个文件恢复失败。"
    return True, f"已恢复 {restored} 个文件。"


def discard(snapshot_id: str) -> None:
    path = snapshot_root() / snapshot_id
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def prune(days: int = 7) -> int:
    root = snapshot_root()
    cutoff = time.time() - max(1, days) * 86400
    removed = 0
    for item in root.iterdir():
        if not item.is_dir():
            continue
        try:
            if item.stat().st_mtime < cutoff:
                shutil.rmtree(item, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
