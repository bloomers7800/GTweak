# FoldScan

macOS-friendly platform that scans a filesystem tree, computes **directory sizes at every level**, and finds **large duplicate folders**.

## Features

- Recursive size rollup for every directory (bottom-up)
- Merkle-style folder fingerprints to detect duplicate directory trees
- Two modes:
  - `meta` — fast (size + mtime + name); great for large home directories
  - `content` — full SHA-256 file hashes; stronger proof of identical contents
- Built-in macOS excludes for cloud data (`iCloud`, `CloudStorage`, Dropbox, etc.)
- CLI report (table + tree) and local web UI

## Install (macOS)

```bash
cd foldscan
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

Scan your home directory (default excludes skip iCloud / cloud sync trees):

```bash
foldscan scan ~
```

Scan a project tree and write JSON:

```bash
foldscan scan ~/Projects --min-size 50MB --mode content --json ~/foldscan-report.json
```

Add excludes / disable defaults:

```bash
foldscan scan / --exclude /Applications --exclude ".git"
foldscan scan ~ --no-default-excludes
```

Launch the local web UI after scanning:

```bash
foldscan serve ~
# open http://127.0.0.1:8741
```

### Tips for macOS

- Prefer scanning `~` or a project folder instead of `/` (system volumes are noisy).
- Cloud-synced data is excluded by default so iCloud / Drive placeholders do not dominate results.
- Use `--mode content` when you need confidence before deleting a duplicate.
- FoldScan never deletes files; it only reports reclaimable space.

## How duplicate folders are detected

1. Each file gets a fingerprint (`meta` or content hash).
2. Each directory fingerprint is a hash of its sorted children `(kind, name, child_fingerprint)`.
3. Directories that share a fingerprint and exceed `--min-size` are grouped.
4. Nested pairs inside the same group are suppressed so you see the outermost duplicates.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
