from __future__ import annotations

import os
from pathlib import Path

from foldscan.formatters import format_bytes
from foldscan.macos import default_excludes_for_root
from foldscan.scanner import is_excluded, scan_path


def _write(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def test_format_bytes():
    assert format_bytes(512) == "512 B"
    assert format_bytes(1536).endswith("KB")
    assert format_bytes(5 * 1024**2).endswith("MB")


def test_is_excluded_cloud_paths():
    excludes = ["Library/Mobile Documents", "Library/CloudStorage", "Dropbox"]
    assert is_excluded("/Users/a/Library/Mobile Documents/com~apple~CloudDocs", excludes)
    assert is_excluded("/Users/a/Library/CloudStorage/GoogleDrive-x", excludes)
    assert is_excluded("/Users/a/Dropbox/work", excludes)
    assert not is_excluded("/Users/a/Projects/app", excludes)


def test_default_excludes_include_cloud():
    excludes = default_excludes_for_root("/Users/demo")
    assert any("Mobile Documents" in e for e in excludes)
    assert any("CloudStorage" in e for e in excludes)


def test_sizes_all_levels(tmp_path: Path):
    _write(tmp_path / "a" / "f1.txt", b"hello")
    _write(tmp_path / "a" / "b" / "f2.txt", b"world!!")
    _write(tmp_path / "c" / "f3.txt", b"xxxx")

    result = scan_path(tmp_path, excludes=[], min_duplicate_bytes=1, mode="content")
    assert result.tree.size == len(b"hello") + len(b"world!!") + len(b"xxxx")
    assert result.tree.children["a"].size == len(b"hello") + len(b"world!!")
    assert result.tree.children["a"].children["b"].size == len(b"world!!")
    assert result.tree.children["c"].size == len(b"xxxx")


def test_finds_duplicate_folders(tmp_path: Path):
    payload = os.urandom(2048)
    for base in ("left/cache", "right/cache"):
        _write(tmp_path / base / "blob.bin", payload)
        _write(tmp_path / base / "note.txt", b"same-note")

    result = scan_path(tmp_path, excludes=[], min_duplicate_bytes=100, mode="content")
    assert result.duplicates, "expected at least one duplicate group"
    # Outer trees win over nested cache/ folders with the same duplicated content.
    assert len(result.duplicates) == 1
    group = result.duplicates[0]
    assert len(group.paths) == 2
    names = {Path(p).name for p in group.paths}
    assert names == {"left", "right"}
    assert group.reclaimable == group.size  # one extra copy


def test_excludes_skip_directory(tmp_path: Path):
    _write(tmp_path / "keep" / "a.bin", b"12345")
    _write(tmp_path / "Library" / "CloudStorage" / "drive" / "big.bin", b"x" * 1000)

    result = scan_path(
        tmp_path,
        excludes=["Library/CloudStorage"],
        min_duplicate_bytes=1,
        mode="meta",
    )
    assert result.tree.size == 5
    # Excluded branch should not contribute children under the scanned keep path size
    assert "CloudStorage" not in (
        result.tree.children.get("Library").children if "Library" in result.tree.children else {}
    )


def test_nested_duplicate_suppressed(tmp_path: Path):
    # Identical trees nested: outer dup should win, inner not listed separately.
    blob = b"Z" * 500
    for base in ("copyA", "copyB"):
        _write(tmp_path / base / "inner" / "f.bin", blob)

    result = scan_path(tmp_path, excludes=[], min_duplicate_bytes=10, mode="content")
    assert len(result.duplicates) == 1
    group = result.duplicates[0]
    assert set(Path(p).name for p in group.paths) == {"copyA", "copyB"}
    # Paths in any group should not include both parent and its child
    for group in result.duplicates:
        for i, p1 in enumerate(group.paths):
            for p2 in group.paths[i + 1 :]:
                assert not (p1.startswith(p2 + os.sep) or p2.startswith(p1 + os.sep))
