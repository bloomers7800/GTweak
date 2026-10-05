"""Local FastAPI UI for browsing scan results."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from foldscan.formatters import format_bytes
from foldscan.models import ScanResult
from foldscan.scanner import find_node, flatten_dirs


STATIC_DIR = Path(__file__).parent / "static"


def create_app(result: ScanResult) -> FastAPI:
    app = FastAPI(title="FoldScan", version="0.1.0")
    app.state.result = result  # type: ignore[attr-defined]

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    @app.get("/api/summary")
    def summary() -> dict:
        r: ScanResult = app.state.result  # type: ignore[attr-defined]
        reclaim = sum(g.reclaimable for g in r.duplicates)
        return {
            "root": r.root,
            "total_size": r.tree.size,
            "total_size_human": format_bytes(r.tree.size),
            "scanned_files": r.scanned_files,
            "scanned_dirs": r.scanned_dirs,
            "elapsed_seconds": r.elapsed_seconds,
            "duplicate_groups": len(r.duplicates),
            "reclaimable": reclaim,
            "reclaimable_human": format_bytes(reclaim),
            "mode": r.mode,
            "min_duplicate_bytes": r.min_duplicate_bytes,
            "excludes": r.excludes,
        }

    @app.get("/api/tree")
    def tree(path: str | None = None, depth: int = Query(2, ge=0, le=8)) -> dict:
        r: ScanResult = app.state.result  # type: ignore[attr-defined]
        node = r.tree if not path else find_node(r.tree, path)
        if node is None:
            raise HTTPException(status_code=404, detail="Path not found in scan tree")
        data = node.to_dict(depth=depth)
        data["size_human"] = format_bytes(node.size)
        return data

    @app.get("/api/largest")
    def largest(limit: int = Query(50, ge=1, le=500), min_bytes: int = 0) -> list[dict]:
        r: ScanResult = app.state.result  # type: ignore[attr-defined]
        nodes = flatten_dirs(r.tree, min_bytes=min_bytes)[:limit]
        return [
            {
                "path": n.path,
                "name": n.name,
                "size": n.size,
                "size_human": format_bytes(n.size),
                "file_count": n.file_count,
                "dir_count": n.dir_count,
            }
            for n in nodes
        ]

    @app.get("/api/duplicates")
    def duplicates(limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
        r: ScanResult = app.state.result  # type: ignore[attr-defined]
        out = []
        for g in r.duplicates[:limit]:
            d = g.to_dict()
            d["size_human"] = format_bytes(g.size)
            d["reclaimable_human"] = format_bytes(g.reclaimable)
            out.append(d)
        return out

    return app


def run_server(app: FastAPI, *, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FoldScan</title>
  <link rel="stylesheet" href="/static/app.css" />
</head>
<body>
  <div class="atmosphere" aria-hidden="true"></div>
  <header class="top">
    <div class="brand">FoldScan</div>
    <p class="tagline" id="tagline">Directory sizes and large duplicate folders</p>
  </header>
  <main>
    <section class="summary" id="summary"></section>
    <section class="panel">
      <h2>Largest directories</h2>
      <div id="largest"></div>
    </section>
    <section class="panel">
      <h2>Duplicate folders</h2>
      <div id="duplicates"></div>
    </section>
    <section class="panel">
      <h2>Browse tree</h2>
      <div id="breadcrumb" class="breadcrumb"></div>
      <div id="tree"></div>
    </section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
"""
