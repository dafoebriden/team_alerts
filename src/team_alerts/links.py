"""Optional contextual links (GitHub, etc.) derived from exceptions and config."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Iterator


def github_blob_url(
    *,
    repository: str,
    ref: str,
    repo_path: str,
    line: int | None = None,
    base_url: str = "https://github.com",
) -> str:
    """
    Build a ``/blob/`` URL for a path inside a repository at ``ref``.

    ``repository`` is ``owner/name`` (no leading slash). ``repo_path`` uses forward
    slashes relative to the repo root.
    """
    repo = repository.strip().strip("/")
    path = repo_path.strip().lstrip("/")
    base = base_url.rstrip("/")
    url = f"{base}/{repo}/blob/{ref}/{path}"
    if line is not None and line > 0:
        url = f"{url}#L{line}"
    return url


def iter_traceback_frames(exc: Exception) -> Iterator[tuple[str, int]]:
    """Yield ``(filename, lineno)`` for each frame in ``exc``'s traceback, outermost first."""
    tb = exc.__traceback__
    if tb is None:
        return
    yield from ((f.filename, f.lineno) for f in traceback.extract_tb(tb))


def pick_github_frame(
    exc: Exception,
    *,
    skip_site_packages: bool = True,
) -> tuple[str, int] | None:
    """
    Pick a frame to deep-link: prefer the innermost frame, skipping ``site-packages``
    (and ``dist-packages``) when ``skip_site_packages`` is true.
    """
    frames = list(iter_traceback_frames(exc))
    if not frames:
        return None

    def is_vendor(path: str) -> bool:
        p = path.replace("\\", "/").lower()
        return "site-packages" in p or "dist-packages" in p

    candidates = [f for f in frames if not (skip_site_packages and is_vendor(f[0]))]
    pool = candidates or frames
    return pool[-1]


def repo_relative_path(file_path: str, source_root: str) -> str | None:
    """Return POSIX path relative to ``source_root``, or ``None`` if not under root."""
    try:
        abs_file = Path(file_path).resolve()
        root = Path(source_root).resolve()
        rel = abs_file.relative_to(root)
    except (ValueError, OSError):
        return None
    return rel.as_posix()
