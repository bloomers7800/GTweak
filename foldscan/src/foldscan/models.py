"""Shared data models for scan results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DirNode:
    path: str
    name: str
    size: int = 0
    file_count: int = 0
    dir_count: int = 0
    fingerprint: str = ""
    children: dict[str, DirNode] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self, *, depth: int | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "path": self.path,
            "name": self.name,
            "size": self.size,
            "file_count": self.file_count,
            "dir_count": self.dir_count,
            "fingerprint": self.fingerprint,
            "error": self.error,
        }
        if depth is None or depth > 0:
            next_depth = None if depth is None else depth - 1
            data["children"] = [
                child.to_dict(depth=next_depth)
                for child in sorted(self.children.values(), key=lambda c: c.size, reverse=True)
            ]
        else:
            data["children"] = []
        return data


@dataclass(slots=True)
class DuplicateGroup:
    fingerprint: str
    size: int
    paths: list[str]
    reclaimable: int  # size * (n - 1) keeping one copy

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScanResult:
    root: str
    tree: DirNode
    duplicates: list[DuplicateGroup]
    scanned_files: int
    scanned_dirs: int
    elapsed_seconds: float
    excludes: list[str]
    min_duplicate_bytes: int
    mode: str

    def to_dict(self, *, tree_depth: int | None = 3) -> dict[str, Any]:
        return {
            "root": self.root,
            "tree": self.tree.to_dict(depth=tree_depth),
            "duplicates": [d.to_dict() for d in self.duplicates],
            "scanned_files": self.scanned_files,
            "scanned_dirs": self.scanned_dirs,
            "elapsed_seconds": self.elapsed_seconds,
            "excludes": self.excludes,
            "min_duplicate_bytes": self.min_duplicate_bytes,
            "mode": self.mode,
        }
