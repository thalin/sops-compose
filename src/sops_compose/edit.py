"""Commands that edit the source files in place: add-key and grant.

Edits go through ruamel's round-trip mode so hand-written comments and layout
survive. Both functions only touch sources; the caller re-renders.
"""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .checks import tracked_files
from .config import (
    AGE_KEY_RE, KEYS_DIR, NAME_RE, RULES_FILE, SOURCE_DIR, Config, ConfigError,
    load, round_trip_yaml,
)

_REGEX_SPECIAL = set(r".^$*+?()[]{}|\\")


def path_regex_for(path: str) -> str:
    """An anchored path_regex matching exactly `path`. Only escapes what RE2
    (sops) and Python treat as special, so the rule stays readable."""
    return "^" + "".join("\\" + c if c in _REGEX_SPECIAL else c for c in path) + "$"


def _flow_seq(items: list[str]) -> CommentedSeq:
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq


def add_key(root: Path, name: str, age_key: str, comment: str | None = None) -> str:
    """Upsert one key. `name` is `<namespace>.<name>[.<name>...]`. Returns
    "added", "updated" or "unchanged"."""
    if not AGE_KEY_RE.match(age_key):
        raise ConfigError(f"not an age public key: {age_key!r}")
    parts = name.split(".")
    if len(parts) < 2 or not all(NAME_RE.match(p) for p in parts):
        raise ConfigError(f"key name must be <namespace>.<name>, got {name!r}")

    cfg = load(root)
    for other, existing in cfg.keys.items():
        if existing == age_key and other != name:
            raise ConfigError(f"that age key is already named {other}")
    ns = parts[0]
    if ns in cfg.groups:
        raise ConfigError(f"namespace {ns!r} clashes with group {ns!r}")

    y = round_trip_yaml()
    file = root / SOURCE_DIR / KEYS_DIR / f"{ns}.yaml"
    doc = (y.load(file) if file.exists() else None) or CommentedMap()

    node = doc
    for i, part in enumerate(parts[1:-1], start=1):
        child = node.get(part)
        if child is None:
            child = node[part] = CommentedMap()
        elif not isinstance(child, dict):
            raise ConfigError(f"{'.'.join(parts[:i + 1])} is a key, not a namespace")
        node = child

    leaf = parts[-1]
    current = node.get(leaf)
    if isinstance(current, dict):
        raise ConfigError(f"{name} is a namespace with keys under it, not a key")
    status = "added" if current is None else ("unchanged" if current == age_key else "updated")
    node[leaf] = age_key
    if comment:
        node.yaml_add_eol_comment(f"# {comment}", leaf)
        if status == "unchanged":
            status = "updated"
    if status != "unchanged":
        file.parent.mkdir(parents=True, exist_ok=True)
        y.dump(doc, file)
    return status


def grant(
    root: Path,
    ref: str,
    paths: list[str],
    with_refs: list[str] = (),
    allow_broad: bool = False,
    note: str | None = None,
) -> list[str]:
    """Make `ref` a recipient of each path (relative to the root). For each path:
    if its first-matching rule already includes `ref`, nothing changes; if a
    rule matches, `ref` is appended to that rule's age (refusing when the rule
    also governs other tracked files, unless `allow_broad`); if no rule
    matches, a rule for exactly that path is appended, with `ref` plus
    `with_refs` as recipients. Validates everything before writing anything.
    Returns messages describing what was done."""
    cfg = load(root)
    wanted = set(cfg.resolve(ref, "grant"))
    cfg.resolve(list(with_refs), "--with")

    files = tracked_files(root)
    targets: dict[int, list[str]] = {}
    unmatched: list[str] = []
    for p in dict.fromkeys(paths):
        rule = cfg.first_match(p)
        if rule is None:
            unmatched.append(p)
        else:
            targets.setdefault(rule.index, []).append(p)

    messages = []
    extend: list[int] = []
    for index, ps in targets.items():
        rule = cfg.rules[index]
        if wanted <= set(rule.names):
            messages.append(f"{', '.join(ps)}: {ref} is already a recipient (rule {index}: {rule.path_regex})")
            continue
        others = [f for f in files if f not in ps and cfg.first_match(f) is rule]
        if others and not allow_broad:
            shown = ", ".join(others[:5]) + (" ..." if len(others) > 5 else "")
            raise ConfigError(
                f"rule {index} ({rule.path_regex}) also covers {shown}; adding {ref} to it "
                f"would let {ref} decrypt those too. Add a narrower rule first, or pass --allow-broad."
            )
        extend.append(index)
        messages.append(f"{', '.join(ps)}: added {ref} to rule {index} ({rule.path_regex})")

    new_rules = []
    for p in unmatched:
        recipients = list(dict.fromkeys([ref, *with_refs]))
        new_rules.append((p, recipients))
        messages.append(f"{p}: no rule matched; added rule {path_regex_for(p)} -> {', '.join(recipients)}")
        if len(cfg.resolve(recipients, "grant")) == 1:
            messages.append(f"warning: {p} has a single recipient; add more with --with or you may not be able to decrypt it")

    if not extend and not new_rules:
        return messages

    y = round_trip_yaml()
    file = root / SOURCE_DIR / RULES_FILE
    doc = y.load(file)
    for index in extend:
        entry = doc[index]
        age = entry["age"]
        if isinstance(age, list):
            age.append(ref)
        else:
            entry["age"] = _flow_seq([age, ref])
    for p, recipients in new_rules:
        entry = CommentedMap()
        entry["path_regex"] = path_regex_for(p)
        entry["age"] = _flow_seq(recipients)
        if note:
            entry.yaml_set_start_comment(note)
        doc.append(entry)
    y.dump(doc, file)
    return messages
