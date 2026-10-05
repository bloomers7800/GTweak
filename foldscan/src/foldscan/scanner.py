"""Filesystem walker that computes sizes and Merkle-style folder fingerprints."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from foldscan.models import DirNode, DuplicateGroup, ScanResult

ProgressCallback = Callable[[int, int, str], None]


def _normalize_excludes(patterns: Iterable[str]) -> list[str]:
    return [p.rstrip("/") for p in patterns if p]


def is_excluded(path: str, excludes: list[str]) -> bool:
    """Return True if path matches any exclude pattern (basename, suffix, or absolute)."""
    if not excludes:
        return False
    p = path.rstrip("/")
    for pattern in excludes:
        if not pattern:
            continue
        pat = pattern.rstrip("/")
        # Absolute prefix
        if pat.startswith("/") and (p == pat or p.startswith(pat + "/")):
            return True
        # Exact / suffix / contained path segment sequence
        if p == pat or p.endswith("/" + pat) or ("/" + pat + "/") in ("/" + p + "/"):
            return True
        # Basename exact (e.g. "Dropbox")
        if os.path.basename(p) == pat:
            return True
        # Single path-component anywhere
        if "/" not in pat and pat in p.split("/"):
            return True
    return False


def _file_identity(path: Path, *, mode: str, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    """Return (fingerprint, size) for a regular file."""
    try:
        st = path.stat(follow_symlinks=False)
    except OSError:
        return ("error", 0)
    size = int(st.st_size)
    if mode == "meta":
        # Fast: size + mtime ns + name. Good for finding likely clones, not byte-identical proof.
        payload = f"{size}:{st.st_mtime_ns}:{path.name}".encode()
        return (hashlib.sha256(payload).hexdigest(), size)

    # Accurate content hash (sha256), streamed.
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return ("error", size)
    return (h.hexdigest(), size)


def _dir_fingerprint(entries: list[tuple[str, str, bool]]) -> str:
    """
    Merkle-like directory fingerprint.

    entries: list of (name, child_fingerprint, is_dir)
    Sorted so order of discovery does not matter.
    """
    h = hashlib.sha256()
    for name, fp, is_dir in sorted(entries, key=lambda e: e[0]):
        kind = "d" if is_dir else "f"
        h.update(f"{kind}:{name}:{fp}\n".encode())
    return h.hexdigest()


def scan_path(
    root: str | Path,
    *,
    excludes: Iterable[str] | None = None,
    mode: str = "meta",
    min_duplicate_bytes: int = 10 * 1024 * 1024,
    follow_symlinks: bool = False,
    one_filesystem: bool = True,
    progress: ProgressCallback | None = None,
) -> ScanResult:
    """
    Scan `root`, compute size for every directory, and find large duplicate folders.

    mode:
      - "meta": size+mtime+name (fast, recommended for huge trees)
      - "content": full file sha256 (slower, stronger duplicate proof)
    """
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Path does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_path}")

    exclude_list = _normalize_excludes(excludes or [])
    started = time.perf_counter()
    scanned_files = 0
    scanned_dirs = 0

    root_dev: int | None = None
    if one_filesystem:
        try:
            root_dev = root_path.stat().st_dev
        except OSError:
            root_dev = None

    # fingerprint -> list of DirNode for dirs above min size
    fp_index: dict[str, list[DirNode]] = {}

    def walk(path: Path) -> DirNode:
        nonlocal scanned_files, scanned_dirs
        node = DirNode(path=str(path), name=path.name or str(path))
        scanned_dirs += 1
        if progress and scanned_dirs % 200 == 0:
            progress(scanned_files, scanned_dirs, str(path))

        if is_excluded(str(path), exclude_list) and path != root_path:
            node.error = "excluded"
            return node

        try:
            entries = list(os.scandir(path))
        except OSError as exc:
            node.error = str(exc)
            return node

        child_entries: list[tuple[str, str, bool]] = []

        for entry in entries:
            name = entry.name
            child_path = Path(entry.path)

            if name in (".", ".."):
                continue
            if is_excluded(str(child_path), exclude_list):
                continue

            try:
                is_symlink = entry.is_symlink()
            except OSError:
                continue

            if is_symlink and not follow_symlinks:
                continue

            try:
                is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
                is_file = entry.is_file(follow_symlinks=follow_symlinks)
            except OSError:
                continue

            if is_dir:
                if one_filesystem and root_dev is not None:
                    try:
                        if entry.stat(follow_symlinks=False).st_dev != root_dev:
                            continue
                    except OSError:
                        continue
                child = walk(child_path)
                node.children[name] = child
                node.size += child.size
                node.file_count += child.file_count
                node.dir_count += 1 + child.dir_count
                if child.fingerprint and child.error != "excluded":
                    child_entries.append((name, child.fingerprint, True))
            elif is_file:
                fp, size = _file_identity(child_path, mode=mode)
                scanned_files += 1
                node.size += size
                node.file_count += 1
                if fp != "error":
                    child_entries.append((name, fp, False))

        node.fingerprint = _dir_fingerprint(child_entries) if child_entries else "empty"
        if (
            node.size >= min_duplicate_bytes
            and node.fingerprint
            and node.fingerprint != "empty"
            and node.error is None
        ):
            fp_index.setdefault(node.fingerprint, []).append(node)
        return node

    tree = walk(root_path)
    duplicates = _build_duplicate_groups(fp_index, min_duplicate_bytes)
    elapsed = time.perf_counter() - started

    return ScanResult(
        root=str(root_path),
        tree=tree,
        duplicates=duplicates,
        scanned_files=scanned_files,
        scanned_dirs=scanned_dirs,
        elapsed_seconds=elapsed,
        excludes=exclude_list,
        min_duplicate_bytes=min_duplicate_bytes,
        mode=mode,
    )


def _build_duplicate_groups(
    fp_index: dict[str, list[DirNode]],
    min_duplicate_bytes: int,
) -> list[DuplicateGroup]:
    groups: list[DuplicateGroup] = []
    for fp, nodes in fp_index.items():
        if len(nodes) < 2:
            continue
        # Deduplicate exact same path (shouldn't happen) and suppress nested pairs
        # where both parent and child share the same fingerprint chain.
        paths = sorted({n.path for n in nodes})
        paths = _suppress_nested_paths(paths)
        if len(paths) < 2:
            continue
        size = max(n.size for n in nodes if n.path in paths)
        if size < min_duplicate_bytes:
            continue
        groups.append(
            DuplicateGroup(
                fingerprint=fp,
                size=size,
                paths=paths,
                reclaimable=size * (len(paths) - 1),
            )
        )
    # Prefer larger reclaimable space, then outermost trees (shallower paths).
    groups.sort(
        key=lambda g: (
            -g.reclaimable,
            min(p.count(os.sep) for p in g.paths),
            -g.size,
        )
    )
    return _suppress_nested_groups(groups)


def _suppress_nested_paths(paths: list[str]) -> list[str]:
    """If A is parent of B and both are in the same duplicate set, keep outermost."""
    kept: list[str] = []
    ordered = sorted(paths, key=lambda p: (p.count(os.sep), len(p)))
    for path in ordered:
        if any(path == parent or path.startswith(parent + os.sep) for parent in kept):
            continue
        kept.append(path)
    return kept


def _suppress_nested_groups(groups: list[DuplicateGroup]) -> list[DuplicateGroup]:
    """Drop child duplicate groups already explained by an outer duplicate group."""
    kept: list[DuplicateGroup] = []
    claimed: list[str] = []
    for group in groups:
        if group.paths and all(
            any(p == anc or p.startswith(anc + os.sep) for anc in claimed) for p in group.paths
        ):
            continue
        kept.append(group)
        claimed.extend(group.paths)
    return kept


def find_node(tree: DirNode, path: str) -> DirNode | None:
    target = str(Path(path).expanduser())
    if tree.path == target or Path(tree.path).resolve() == Path(target).resolve():
        return tree

    # Walk by relative segments when possible
    try:
        rel = Path(target).resolve().relative_to(Path(tree.path).resolve())
    except (ValueError, OSError):
        # Fallback linear search
        stack = [tree]
        while stack:
            node = stack.pop()
            if node.path == target:
                return node
            stack.extend(node.children.values())
        return None

    node = tree
    for part in rel.parts:
        if part not in node.children:
            return None
        node = node.children[part]
    return node


def flatten_dirs(tree: DirNode, *, min_bytes: int = 0) -> list[DirNode]:
    out: list[DirNode] = []
    stack = [tree]
    while stack:
        node = stack.pop()
        if node.size >= min_bytes:
            out.append(node)
        stack.extend(node.children.values())
    out.sort(key=lambda n: n.size, reverse=True)
    return out
