from foldscan.scanner import scan_path
from foldscan.webapp import create_app


def test_api_summary(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("hi", encoding="utf-8")
    result = scan_path(tmp_path, excludes=[], min_duplicate_bytes=1, mode="meta")
    app = create_app(result)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    summary = client.get("/api/summary").json()
    assert summary["scanned_files"] == 1
    assert summary["root"] == str(tmp_path.resolve())
    largest = client.get("/api/largest").json()
    assert largest[0]["path"] == str(tmp_path.resolve())
    tree = client.get("/api/tree").json()
    assert "children" in tree
    assert client.get("/").status_code == 200
