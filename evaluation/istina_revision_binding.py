"""Bind an evidence-producing command to the repository revision it runs."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


NON_SOURCE_OUTPUT_PREFIXES = ("evidence/", "paper/", "runs/")


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


def source_worktree_changes(project_root: Path) -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    changed_paths = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not path.startswith(NON_SOURCE_OUTPUT_PREFIXES):
            changed_paths.append(path)
    return changed_paths


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
    changed_paths = source_worktree_changes(project_root)
    if changed_paths:
        preview = ", ".join(changed_paths[:5])
        if len(changed_paths) > 5:
            preview += f", and {len(changed_paths) - 5} more"
        raise ValueError(
            "executing repository has uncommitted source changes: " + preview
        )
    return observed


__all__ = [
    "NON_SOURCE_OUTPUT_PREFIXES",
    "current_git_revision",
    "require_current_git_revision",
    "source_worktree_changes",
]
