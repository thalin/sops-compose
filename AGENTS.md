# sops-compose

Python CLI that renders a flat `.sops.yaml` from split YAML sources under `sops/` (named keys,
nested groups, ordered rules). Usage, commands and error semantics are in
[README.md](README.md); the vocabulary (reference, group, shadowed rule, grant, …) is in
[CONTEXT.md](CONTEXT.md). Use those terms in code, docs and messages.

## Layout

- `src/sops_compose/`: the package (see [its AGENTS.md](src/sops_compose/AGENTS.md)). Entry point
  `sops-compose = sops_compose.cli:main` in `pyproject.toml`.
- `tests/`: pytest suite. `conftest.py` provides a `repo` fixture (a temp git repo with key files,
  a group, rules and git-tracked secret files) and a `run` fixture that calls `cli.main` with
  `--root` and returns `(exit code, stdout, stderr)`. The age keys in `conftest.py` are throwaway
  public keys. New tests should build on these fixtures; files must be `git add`ed to count as
  tracked for the shadowing and unused-rule checks.
- `.pre-commit-hooks.yaml`: the `sops-compose` hook for plain pre-commit users (runs `render`
  on changes under `sops/` or to `.sops.yaml`).
- `flake.nix`: `packages.<system>.default` (buildPythonApplication), `checks.pytest` (the package
  build, which runs pytest), and a devShell with python + ruamel-yaml + pytest + pyyaml + git.

## Commands

- Tests: `nix flake check`, or `pytest` inside `nix develop`.
- Run locally: `nix run . -- render --root <secrets-repo>`.

## Gotchas

- Runtime needs the `git` binary: the shadowing and unused-rule checks run `git ls-files` (and
  only fall back to walking the disk when the root isn't a git repo). The flake wraps the binary
  with git on `PATH`; keep that if you change packaging.
- The version (`0.1.0`) lives in three places: `pyproject.toml`, `flake.nix` and
  `src/sops_compose/__init__.py`. Bump all three together. README's pre-commit example pins
  `rev: v0.1.0`.
- `pyproject.toml` deps and `flake.nix` `dependencies`/`nativeCheckInputs` must stay in sync
  (`ruamel.yaml` at runtime; `pytest`, `pyyaml`, `git` for tests).

## Consumers (cross-repo)

Changing CLI flags, output or exit codes can break these:

- `nix-secrets`: devenv input (`devenv.yaml`); `devenv.nix` wraps `sops` to render first and adds
  a git-hooks `render` hook; its `justfile` calls `render`, `check` and `explain`.
- `noa-install`: flake input. `packages/upsert-sops-age-key` shells out to
  `sops-compose add-key` and `sops-compose grant` when the secrets repo has `sops/rules.yaml`;
  `packages/sync-sops-recipients` reads the `hosts.<host>` key from the sources. See
  `noa-install/INTEGRATION.md`.

## Subdirectories

- [src/sops_compose/](src/sops_compose/AGENTS.md) — the package: config loading/resolution, checks, render, in-place edits, argparse CLI
