"""Checks that need the repo's files: shadowed rules, unused rules and keys."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import OUTPUT_FILE, SOURCE_DIR, Config


@dataclass
class Finding:
    level: str  # "error" or "warning"
    message: str


def tracked_files(root: Path) -> list[str]:
    """Files sops rules can apply to, relative to the root: git-tracked files
    if this is a git repo, otherwise everything on disk. The sops-compose
    sources and output are excluded."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True,
    )
    if result.returncode == 0:
        files = [f for f in result.stdout.split("\0") if f]
    else:
        files = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for name in filenames:
                files.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(
        f for f in files
        if f != OUTPUT_FILE and not f.startswith(SOURCE_DIR + "/")
    )


def analyse(cfg: Config, files: list[str] | None = None) -> list[Finding]:
    if files is None:
        files = tracked_files(cfg.root)
    findings = []

    won: set[int] = set()
    for f in files:
        rule = cfg.first_match(f)
        if rule is not None:
            won.add(rule.index)
    for rule in cfg.rules:
        matching = [f for f in files if rule.regex.search(f)]
        if matching and rule.index not in won:
            shown = ", ".join(matching[:3]) + (" ..." if len(matching) > 3 else "")
            findings.append(Finding("error", (
                f"rule {rule.index} ({rule.path_regex}) is shadowed: every file it matches "
                f"({shown}) is taken by an earlier rule"
            )))
        elif not matching:
            findings.append(Finding("warning", f"rule {rule.index} ({rule.path_regex}) matches no tracked file"))

    used = {n for rule in cfg.rules for n in rule.names}
    for name in cfg.keys:
        if name not in used:
            findings.append(Finding("warning", f"key {name} is not a recipient of any rule"))
    return findings
