# sops_compose package

The whole CLI (entry `sops_compose.cli:main`). User-facing usage and error semantics: [../../README.md](../../README.md). Terms (recipient, namespace, reference, group, rule, shadowed rule, grant, render): [../../CONTEXT.md](../../CONTEXT.md). Tests: `../../tests` (pytest; `repo` fixture builds a git-tracked temp secrets repo, `run` calls `cli.main`).

## Modules and data flow

- `config.py`: path constants (`sops/`, `keys/`, `groups.yaml`, `rules.yaml`, `.sops.yaml`, `all`), `load(root) -> Config`, `ConfigError`, `Config.resolve` (reference -> ordered, deduplicated key names; handles `all`, groups with cycle detection, namespace/subtree prefixes) and `Config.first_match`. `load` validates everything up front (names, age key format, duplicate age keys, group/namespace clashes, bad regexes, unresolvable refs, even in unused groups), so later stages assume a valid `Config`.
- `checks.py`: `tracked_files` (`git ls-files`, falls back to an os.walk when not a git repo; excludes `sops/` and `.sops.yaml`) and `analyse(cfg) -> [Finding]`. Shadowed rule is an error; rule matching nothing and key used by no rule are warnings.
- `render.py`: `render(cfg) -> str`, the `.sops.yaml` text. Must stay deterministic; `check` compares bytes against the file on disk.
- `edit.py`: `add_key` and `grant` edit the source files in place via ruamel round-trip mode (comments survive). They only touch sources and never render.
- `cli.py`: argparse, `find_root`, `repo_path`, and `do_render` / `do_check` / `do_explain`. `add-key` and `grant` call the edit function, then `do_render(quiet=True)`.

Flow: `load` -> `analyse` -> `render` -> write. `do_render` refuses to write `.sops.yaml` if `analyse` yields any error.

## Invariants

- All user-facing failures raise `ConfigError`; `main` prints `sops-compose: error: ...` and returns 1. Return 2 is only for an unknown command.
- Rule order is significant (first match wins, like sops); `grant` and `analyse` both rely on `first_match`.
- Rules' extra keys (anything besides `path_regex`/`age`) are passed through to the output untouched.
- `grant` validates everything before writing anything, and refuses to extend a rule that also governs other tracked files unless `--allow-broad`.
- Paths given to `explain`/`grant` are relative to cwd on the command line but converted to root-relative by `repo_path` before use.

## Where to add things

- New command: add a subparser and a branch in `main` (`cli.py`); put source-editing logic in `edit.py`, read-only logic as a `do_*` function.
- New check: append `Finding`s in `checks.analyse`; level `"error"` blocks render and fails `check`, `"warning"` only prints.
- New validation of the source files: in `config.load`, raising `ConfigError`.

## Gotchas

- `__version__` in `__init__.py` is a third copy of the version; it is also set in `../../pyproject.toml` and `../../flake.nix`. Bump all three.
- `git` is required at runtime for the shadowing check on real repos (`tracked_files`); untracked files are invisible to it.
- `render.py` uses an explicit eol-comment column because ruamel's default spacing differs for the first list item; `edit.add_key` does the same for key comments. Don't remove those columns without checking output byte-for-byte.
- A keys file containing only comments loads as `None` in ruamel; `add_key` keeps the text as a preamble to avoid dropping comments.
- Two YAML loaders are used on purpose: `typ="safe"` for reading in `config._read`, round-trip (`round_trip_yaml`) for editing.
