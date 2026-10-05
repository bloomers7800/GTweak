"""Human-readable formatting helpers."""

from __future__ import annotations


def format_bytes(num: int | float) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024.0:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} EB"
