"""FoldScan command-line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from foldscan import __version__
from foldscan.formatters import format_bytes
from foldscan.macos import default_excludes_for_root
from foldscan.scanner import flatten_dirs, scan_path

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Scan directory sizes at every level and find large duplicate folders (macOS-friendly).",
)
console = Console(stderr=True)
out = Console()


def _parse_size(text: str) -> int:
    raw = text.strip().upper().replace(" ", "")
    multipliers = {
        "B": 1,
        "K": 1024,
        "KB": 1024,
        "M": 1024**2,
        "MB": 1024**2,
        "G": 1024**3,
        "GB": 1024**3,
        "T": 1024**4,
        "TB": 1024**4,
    }
    for suffix, mult in sorted(multipliers.items(), key=lambda kv: -len(kv[0])):
        if raw.endswith(suffix):
            return int(float(raw[: -len(suffix)]) * mult)
    return int(raw)


@app.callback()
def main() -> None:
    """FoldScan — directory sizes + big duplicate folders."""


@app.command("scan")
def scan_cmd(
    path: Path = typer.Argument(Path.home(), help="Directory to scan (default: home)"),
    mode: str = typer.Option(
        "meta",
        "--mode",
        "-m",
        help="Fingerprint mode: meta (fast) or content (sha256)",
    ),
    min_size: str = typer.Option(
        "10MB",
        "--min-size",
        help="Minimum folder size to consider as a duplicate (e.g. 50MB, 1GB)",
    ),
    exclude: Optional[list[str]] = typer.Option(
        None,
        "--exclude",
        "-x",
        help="Extra exclude pattern (repeatable). Cloud data excluded by default on macOS.",
    ),
    no_default_excludes: bool = typer.Option(
        False,
        "--no-default-excludes",
        help="Do not apply built-in macOS/cloud excludes",
    ),
    top: int = typer.Option(25, "--top", "-n", help="Show top N largest directories"),
    depth: int = typer.Option(2, "--depth", "-d", help="Tree display depth"),
    follow_symlinks: bool = typer.Option(False, "--follow-symlinks"),
    cross_fs: bool = typer.Option(False, "--cross-fs", help="Allow crossing filesystem boundaries"),
    json_out: Optional[Path] = typer.Option(None, "--json", help="Write full results to JSON file"),
) -> None:
    """Scan a path, print size breakdown, and list large duplicate folders."""
    if mode not in {"meta", "content"}:
        raise typer.BadParameter("mode must be 'meta' or 'content'")

    root = str(path.expanduser())
    excludes: list[str] = []
    if not no_default_excludes:
        excludes.extend(default_excludes_for_root(root))
    if exclude:
        excludes.extend(exclude)

    min_bytes = _parse_size(min_size)
    console.print(
        f"[bold]FoldScan[/bold] v{__version__}  root=[cyan]{Path(root).expanduser().resolve()}[/cyan]  "
        f"mode=[yellow]{mode}[/yellow]  min-dupe=[yellow]{format_bytes(min_bytes)}[/yellow]"
    )
    if excludes:
        console.print(f"Excludes: {', '.join(excludes[:8])}{'…' if len(excludes) > 8 else ''}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Scanning…", total=None)
        state = {"files": 0, "dirs": 0}

        def on_progress(files: int, dirs: int, current: str) -> None:
            state["files"] = files
            state["dirs"] = dirs
            short = current if len(current) < 80 else "…" + current[-77:]
            progress.update(task, description=f"Scanning {short} ({files} files, {dirs} dirs)")

        result = scan_path(
            root,
            excludes=excludes,
            mode=mode,
            min_duplicate_bytes=min_bytes,
            follow_symlinks=follow_symlinks,
            one_filesystem=not cross_fs,
            progress=on_progress,
        )

    out.print(
        f"\nScanned [bold]{result.scanned_files:,}[/bold] files / "
        f"[bold]{result.scanned_dirs:,}[/bold] dirs in "
        f"[bold]{result.elapsed_seconds:.2f}s[/bold]. "
        f"Total size: [bold green]{format_bytes(result.tree.size)}[/bold green]\n"
    )

    # Largest directories
    largest = flatten_dirs(result.tree, min_bytes=0)[:top]
    table = Table(title=f"Top {len(largest)} directories by size", show_lines=False)
    table.add_column("Size", justify="right", style="green")
    table.add_column("Files", justify="right")
    table.add_column("Path")
    for node in largest:
        table.add_row(format_bytes(node.size), f"{node.file_count:,}", node.path)
    out.print(table)

    # Compact tree
    tree = Tree(
        f"[bold]{result.tree.name or result.tree.path}[/bold]  ({format_bytes(result.tree.size)})"
    )
    _fill_rich_tree(tree, result.tree, depth=depth)
    out.print("\n")
    out.print(tree)

    # Duplicates
    out.print("\n")
    if not result.duplicates:
        out.print("[dim]No large duplicate folders found at this threshold.[/dim]")
    else:
        dup_table = Table(
            title=f"Large duplicate folders ({len(result.duplicates)} groups)",
            show_lines=True,
        )
        dup_table.add_column("Each", justify="right", style="green")
        dup_table.add_column("Reclaimable", justify="right", style="magenta")
        dup_table.add_column("Copies", justify="right")
        dup_table.add_column("Paths")
        for group in result.duplicates[:50]:
            paths_txt = "\n".join(group.paths)
            dup_table.add_row(
                format_bytes(group.size),
                format_bytes(group.reclaimable),
                str(len(group.paths)),
                paths_txt,
            )
        out.print(dup_table)
        reclaim = sum(g.reclaimable for g in result.duplicates)
        out.print(f"\nPotential reclaimable space: [bold magenta]{format_bytes(reclaim)}[/bold magenta]")

    if json_out:
        json_out = json_out.expanduser()
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(result.to_dict(tree_depth=None), indent=2), encoding="utf-8")
        console.print(f"Wrote JSON → {json_out}")


def _fill_rich_tree(rich_tree: Tree, node, depth: int) -> None:
    if depth <= 0:
        return
    children = sorted(node.children.values(), key=lambda c: c.size, reverse=True)
    for child in children[:40]:
        label = f"{child.name}  [green]{format_bytes(child.size)}[/green]"
        if child.error:
            label += f"  [red]({child.error})[/red]"
        branch = rich_tree.add(label)
        _fill_rich_tree(branch, child, depth - 1)


@app.command("serve")
def serve_cmd(
    path: Path = typer.Argument(Path.home(), help="Directory to scan (default: home)"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8741, "--port"),
    mode: str = typer.Option("meta", "--mode", "-m"),
    min_size: str = typer.Option("10MB", "--min-size"),
    exclude: Optional[list[str]] = typer.Option(None, "--exclude", "-x"),
    no_default_excludes: bool = typer.Option(False, "--no-default-excludes"),
    cross_fs: bool = typer.Option(False, "--cross-fs"),
) -> None:
    """Scan, then open a local web UI to browse sizes and duplicates."""
    from foldscan.webapp import create_app, run_server

    root = str(path.expanduser())
    excludes: list[str] = []
    if not no_default_excludes:
        excludes.extend(default_excludes_for_root(root))
    if exclude:
        excludes.extend(exclude)

    console.print(f"Scanning [cyan]{Path(root).expanduser().resolve()}[/cyan] before starting UI…")
    result = scan_path(
        root,
        excludes=excludes,
        mode=mode,
        min_duplicate_bytes=_parse_size(min_size),
        one_filesystem=not cross_fs,
        progress=lambda f, d, p: console.print(f"[dim]{f} files / {d} dirs[/dim]", end="\r"),
    )
    console.print(
        f"\nScan complete: {format_bytes(result.tree.size)} — "
        f"{len(result.duplicates)} duplicate groups. Starting http://{host}:{port}"
    )
    application = create_app(result)
    run_server(application, host=host, port=port)


@app.command("version")
def version_cmd() -> None:
    """Print version."""
    out.print(__version__)


if __name__ == "__main__":
    app()
    sys.exit(0)
