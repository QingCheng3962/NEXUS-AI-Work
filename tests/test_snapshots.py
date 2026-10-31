"""工作区快照与撤销测试。"""

from pathlib import Path

from core import snapshots


def test_capture_diff_and_restore(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(snapshots, "SNAPSHOT_ROOT", tmp_path / "snapshots")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("old\nline\n", encoding="utf-8")
    (workspace / "remove.txt").write_text("remove me\n", encoding="utf-8")

    info = snapshots.capture(workspace, label="test")
    assert info.file_count == 2

    (workspace / "keep.txt").write_text("new\nline\n", encoding="utf-8")
    (workspace / "remove.txt").unlink()
    (workspace / "added.txt").write_text("added\n", encoding="utf-8")

    changes = {item.path: item for item in snapshots.diff(info.id)}
    assert changes["keep.txt"].kind == "modified"
    assert changes["remove.txt"].kind == "deleted"
    assert changes["added.txt"].kind == "added"
    assert "+new" in changes["keep.txt"].diff

    ok, message = snapshots.restore(info.id)
    assert ok, message
    assert (workspace / "keep.txt").read_text(encoding="utf-8") == "old\nline\n"
    assert (workspace / "remove.txt").exists()
    assert not (workspace / "added.txt").exists()


def test_snapshot_ignores_dependency_directories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(snapshots, "SNAPSHOT_ROOT", tmp_path / "snapshots")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src.txt").write_text("ok", encoding="utf-8")
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "huge.txt").write_text("skip", encoding="utf-8")

    info = snapshots.capture(workspace)
    assert info.file_count == 1
