"""Load the `sops/` source files and resolve references to age recipients."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

SOURCE_DIR = "sops"
KEYS_DIR = "keys"
GROUPS_FILE = "groups.yaml"
RULES_FILE = "rules.yaml"
OUTPUT_FILE = ".sops.yaml"
ALL = "all"

AGE_KEY_RE = re.compile(r"^age1[0-9a-z]+$")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ConfigError(Exception):
    """A problem in the source files that makes rendering impossible."""


def round_trip_yaml() -> YAML:
    """YAML instance for editing source files in place, keeping comments."""
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def _read(path: Path) -> Any:
    try:
        return YAML(typ="safe").load(path.read_text())
    except YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from e


@dataclass
class Rule:
    index: int
    path_regex: str
    regex: re.Pattern
    age: list[str]  # references as written
    names: list[str]  # resolved key names, in resolution order, deduplicated
    extra: dict[str, Any] = field(default_factory=dict)  # passed through to sops


@dataclass
class Config:
    root: Path
    keys: dict[str, str]  # dotted key name -> age public key, in file order
    namespaces: list[str]
    groups: dict[str, list[str]]
    rules: list[Rule]

    @property
    def source_dir(self) -> Path:
        return self.root / SOURCE_DIR

    def resolve(self, ref: Any, where: str = "", _stack: tuple[str, ...] = ()) -> list[str]:
        """Resolve a reference (or list of them) to an ordered, deduplicated list
        of key names. A reference is a key name, a namespace or subtree prefix,
        a group, or `all`."""
        if isinstance(ref, list):
            out: list[str] = []
            for r in ref:
                out += self.resolve(r, where, _stack)
            return list(dict.fromkeys(out))
        if not isinstance(ref, str):
            raise ConfigError(f"{where}: reference must be a string or a list, got {ref!r}")
        if ref == ALL:
            return list(self.keys)
        if ref in self.groups:
            if ref in _stack:
                raise ConfigError(f"group cycle: {' -> '.join(_stack + (ref,))}")
            return self.resolve(self.groups[ref], f"group {ref!r}", _stack + (ref,))
        hits = [n for n in self.keys if n == ref or n.startswith(ref + ".")]
        if not hits:
            raise ConfigError(f"{where}: unknown reference {ref!r}")
        return hits

    def first_match(self, path: str) -> Rule | None:
        """The rule sops would use for `path` (relative to the repo root)."""
        return next((r for r in self.rules if r.regex.search(path)), None)


def _collect_keys(node: Any, prefix: str, keys: dict[str, str], file: Path) -> None:
    if not isinstance(node, dict):
        raise ConfigError(f"{file}: {prefix} must be a mapping of names to age keys")
    for name, value in node.items():
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise ConfigError(f"{file}: invalid key name {name!r} under {prefix}")
        dotted = f"{prefix}.{name}"
        if isinstance(value, str):
            if not AGE_KEY_RE.match(value):
                raise ConfigError(f"{file}: {dotted} is not an age public key: {value!r}")
            keys[dotted] = value
        else:
            _collect_keys(value, dotted, keys, file)


def _as_refs(value: Any, where: str) -> list[str]:
    refs = value if isinstance(value, list) else [value]
    if not refs or not all(isinstance(r, str) for r in refs):
        raise ConfigError(f"{where}: expected a reference or a list of references, got {value!r}")
    return refs


def load(root: Path) -> Config:
    src = root / SOURCE_DIR
    keys_dir = src / KEYS_DIR
    if not keys_dir.is_dir():
        raise ConfigError(f"{keys_dir} not found")

    keys: dict[str, str] = {}
    namespaces = []
    for file in sorted(keys_dir.glob("*.yaml")):
        ns = file.stem
        if not NAME_RE.match(ns):
            raise ConfigError(f"{file}: invalid namespace name {ns!r}")
        namespaces.append(ns)
        _collect_keys(_read(file) or {}, ns, keys, file)

    owner: dict[str, str] = {}
    for name, age in keys.items():
        if age in owner:
            raise ConfigError(f"the same age key is named both {owner[age]} and {name}")
        owner[age] = name

    groups_file = src / GROUPS_FILE
    raw_groups = (_read(groups_file) if groups_file.exists() else None) or {}
    if not isinstance(raw_groups, dict):
        raise ConfigError(f"{groups_file}: must be a mapping of group names to references")
    groups = {}
    for name, value in raw_groups.items():
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise ConfigError(f"{groups_file}: invalid group name {name!r}")
        if name == ALL:
            raise ConfigError(f"{groups_file}: {ALL!r} is built in and can't be redefined")
        if name in namespaces:
            raise ConfigError(f"{groups_file}: group {name!r} clashes with key namespace {name!r}")
        groups[name] = _as_refs(value, f"group {name!r}")
    if ALL in namespaces:
        raise ConfigError(f"{keys_dir / (ALL + '.yaml')}: {ALL!r} is built in and can't be a namespace")

    cfg = Config(root=root, keys=keys, namespaces=namespaces, groups=groups, rules=[])

    rules_file = src / RULES_FILE
    if not rules_file.exists():
        raise ConfigError(f"{rules_file} not found")
    raw_rules = _read(rules_file) or []
    if not isinstance(raw_rules, list):
        raise ConfigError(f"{rules_file}: must be a list of rules")
    for i, raw in enumerate(raw_rules):
        where = f"{rules_file.name} rule {i}"
        if not isinstance(raw, dict) or not isinstance(raw.get("path_regex"), str):
            raise ConfigError(f"{where}: every rule needs a path_regex")
        if "age" not in raw:
            raise ConfigError(f"{where} ({raw['path_regex']}): missing age")
        try:
            regex = re.compile(raw["path_regex"])
        except re.error as e:
            raise ConfigError(f"{where}: invalid path_regex {raw['path_regex']!r}: {e}") from e
        refs = _as_refs(raw["age"], where)
        cfg.rules.append(Rule(
            index=i,
            path_regex=raw["path_regex"],
            regex=regex,
            age=refs,
            names=[],
            extra={k: v for k, v in raw.items() if k not in ("path_regex", "age")},
        ))

    # Groups that no rule uses still have to resolve.
    for name in groups:
        cfg.resolve(name, f"group {name!r}")
    for rule in cfg.rules:
        rule.names = cfg.resolve(rule.age, f"{RULES_FILE} rule {rule.index} ({rule.path_regex})")
    return cfg
