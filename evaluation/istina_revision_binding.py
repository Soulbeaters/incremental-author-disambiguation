"""Bind an evidence-producing command to the repository revision it runs."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def current_git_revision(project_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip().lower()
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("git rev-parse HEAD did not return a full 40-hex revision")
    return revision


def require_current_git_revision(
    requested_revision: str,
    project_root: Path,
) -> str:
    requested = str(requested_revision or "").lower()
    if re.fullmatch(r"[0-9a-f]{40}", requested) is None:
        raise ValueError("code-revision must be a full 40-hex Git commit")
    observed = current_git_revision(project_root)
    if requested != observed:
        raise ValueError(
            "code-revision does not match the executing repository HEAD: "
            f"requested {requested}, observed {observed}"
        )
    return observed


__all__ = ["current_git_revision", "require_current_git_revision"]
