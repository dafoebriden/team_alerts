"""Tests for GitHub / traceback link helpers."""

from __future__ import annotations

from team_alerts.links import github_blob_url, pick_github_frame, repo_relative_path


def test_github_blob_url_with_line() -> None:
    url = github_blob_url(
        repository="acme/demo",
        ref="abc123",
        repo_path="src/app.py",
        line=42,
    )
    assert url == "https://github.com/acme/demo/blob/abc123/src/app.py#L42"


def test_github_blob_url_custom_base() -> None:
    url = github_blob_url(
        repository="acme/demo",
        ref="main",
        repo_path="README.md",
        base_url="https://git.example.com",
    )
    assert url == "https://git.example.com/acme/demo/blob/main/README.md"


def test_pick_github_frame_points_at_this_file() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        frame = pick_github_frame(exc, skip_site_packages=True)
    assert frame is not None
    path, lineno = frame
    assert "test_links.py" in path.replace("\\", "/")
    assert lineno >= 1


def test_repo_relative_path() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent
    child = root / "test_links.py"
    rel = repo_relative_path(str(child), str(root))
    assert rel == "test_links.py"
