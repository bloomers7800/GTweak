"""macOS-oriented default excludes (cloud sync, system firmlinks, noise)."""

from __future__ import annotations

# Relative to home (~) or absolute path segments used as fnmatch / suffix matches.
DEFAULT_MACOS_EXCLUDES: tuple[str, ...] = (
    # iCloud Drive + Desktop/Documents sync
    "Library/Mobile Documents",
    "Library/CloudStorage",
    # Common cloud / sync clients
    "Dropbox",
    "Google Drive",
    "OneDrive",
    "Box",
    # Local caches & noise that dominate scans without being "your files"
    "Library/Caches",
    "Library/Logs",
    ".Trash",
    # Time Machine / volume noise when scanning broadly
    ".Spotlight-V100",
    ".fseventsd",
    ".TemporaryItems",
    ".Trashes",
    "System Volume Information",
)

# Absolute path prefixes often present on macOS system scans.
DEFAULT_MACOS_SYSTEM_EXCLUDES: tuple[str, ...] = (
    "/System",
    "/private/var/vm",
    "/private/var/folders",
    "/dev",
    "/Volumes/Macintosh HD",  # firmlink alias of root data
)


def default_excludes_for_root(root: str) -> list[str]:
    """Return sensible exclude patterns for a scan root."""
    excludes = list(DEFAULT_MACOS_EXCLUDES)
    # When scanning from filesystem root, also skip heavy system trees.
    if root.rstrip("/") in ("", "/"):
        excludes.extend(DEFAULT_MACOS_SYSTEM_EXCLUDES)
    return excludes
