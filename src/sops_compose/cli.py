"""sops-compose: author sops creation rules as split YAML with named keys and
composable groups, and render them to `.sops.yaml`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .checks import analyse
from .config import OUTPUT_FILE, RULES_FILE, SOURCE_DIR, ConfigError, load
from .edit import add_key, grant
from .render import render


def find_root(start: Path) -> Path:
    """The nearest directory at or above `start` that has sops/rules.yaml."""
    for d in [start, *start.parents]:
        if (d / SOURCE_DIR / RULES_FILE).is_file():
            return d
    raise ConfigError(f"no {SOURCE_DIR}/{RULES_FILE} found in {start} or any parent; pass --root")


def repo_path(root: Path, path: str) -> str:
    """A path given on the command line (relative to the cwd), as sops sees it:
    relative to the root."""
    rel = os.path.relpath(os.path.abspath(path), root)
    if rel == ".." or rel.startswith("../"):
        raise ConfigError(f"{path} is outside {root}")
    return rel


def _report(findings) -> bool:
    """Print findings; return True if any is an error."""
    for f in findings:
        print(f"sops-compose: {f.level}: {f.message}", file=sys.stderr)
    return any(f.level == "error" for f in findings)


def do_render(root: Path, quiet: bool = False) -> int:
    cfg = load(root)
    if _report(analyse(cfg)):
        print(f"sops-compose: {OUTPUT_FILE} not written", file=sys.stderr)
        return 1
    text = render(cfg)
    out = root / OUTPUT_FILE
    if out.exists() and out.read_text() == text:
        if not quiet:
            print(f"{OUTPUT_FILE} is up to date")
        return 0
    out.write_text(text)
    print(f"wrote {OUTPUT_FILE}")
    return 0


def do_check(root: Path) -> int:
    cfg = load(root)
    failed = _report(analyse(cfg))
    out = root / OUTPUT_FILE
    if not out.exists():
        print(f"sops-compose: error: {OUTPUT_FILE} is missing; run `sops-compose render`", file=sys.stderr)
        failed = True
    elif out.read_text() != render(cfg):
        print(
            f"sops-compose: error: {OUTPUT_FILE} is stale or was edited by hand. "
            f"Edit {SOURCE_DIR}/ and run `sops-compose render`.",
            file=sys.stderr,
        )
        failed = True
    if not failed:
        print(f"{OUTPUT_FILE} is up to date")
    return 1 if failed else 0


def do_explain(root: Path, paths: list[str]) -> int:
    cfg = load(root)
    status = 0
    for p in paths:
        rel = repo_path(root, p)
        rule = cfg.first_match(rel)
        if rule is None:
            print(f"{rel}: no rule matches")
            status = 1
            continue
        print(f"{rel}: rule {rule.index} ({rule.path_regex})")
        for name in rule.names:
            print(f"  {name}  {cfg.keys[name]}")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sops-compose", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", type=Path, help=f"repo root (default: nearest directory with {SOURCE_DIR}/{RULES_FILE})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("render", help=f"write {OUTPUT_FILE} from {SOURCE_DIR}/")
    sub.add_parser("check", help=f"fail on errors or if {OUTPUT_FILE} is stale")

    p = sub.add_parser("explain", help="show the rule and recipients sops would use for a path")
    p.add_argument("paths", nargs="+")

    p = sub.add_parser("add-key", help="add or update a key, then render")
    p.add_argument("name", help="dotted key name, e.g. hosts.titan")
    p.add_argument("age_key")
    p.add_argument("--comment", help="trailing comment for the key")

    p = sub.add_parser("grant", help="make a reference a recipient of paths, then render")
    p.add_argument("ref", help="key name, namespace or group")
    p.add_argument("paths", nargs="+")
    p.add_argument("--with", dest="with_refs", action="append", default=[], metavar="REF",
                   help="extra recipient for rules created by this command (repeatable)")
    p.add_argument("--allow-broad", action="store_true",
                   help="extend a matching rule even if it also covers other files")
    p.add_argument("--note", help="comment to put above rules created by this command")

    args = parser.parse_args(argv)
    try:
        root = (args.root or find_root(Path.cwd())).resolve()
        if args.command == "render":
            return do_render(root)
        if args.command == "check":
            return do_check(root)
        if args.command == "explain":
            return do_explain(root, args.paths)
        if args.command == "add-key":
            status = add_key(root, args.name, args.age_key, args.comment)
            print(f"{args.name}: {status}")
            return do_render(root, quiet=True)
        if args.command == "grant":
            paths = [repo_path(root, p) for p in args.paths]
            for msg in grant(root, args.ref, paths, args.with_refs, args.allow_broad, args.note):
                print(msg)
            return do_render(root, quiet=True)
    except ConfigError as e:
        print(f"sops-compose: error: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
