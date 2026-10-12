# sops-compose

Write your [sops](https://github.com/getsops/sops) creation rules as small YAML files, with
**named keys** and **groups that can contain groups**. sops-compose renders them into the flat
`.sops.yaml` sops reads.

A big `.sops.yaml` turns into a wall of `age1…` strings and YAML anchors. Anchors can't
concatenate lists, so every "admins plus this host" combination becomes another hand-maintained
key group. sops-compose replaces that with names:

```yaml
# sops/keys/hosts.yaml
sidewinder: age1td3g…  # MS-01, runs services
es1: age1xjl4…         # validator

# sops/keys/users.yaml
alice:
  laptop: age10ak0…

# sops/keys/yubikey.yaml
everyday: age1yubikey1q2na…
backup: age1yubikey1qgqv…

# sops/groups.yaml
admin: [users.alice.laptop, yubikey]

# sops/rules.yaml (ordered: sops uses the first matching rule)
- path_regex: ^secrets\.yaml$
  age: all
- path_regex: systems/es1/.*$
  age: [admin, hosts.es1]
- path_regex: services/paperless/.*$
  age: [admin, hosts.sidewinder]
  encrypted_regex: ^(data|stringData)$   # any other sops field passes through
```

`sops-compose render` writes `.sops.yaml` with each key labelled by name:

```yaml
creation_rules:
  - path_regex: 'systems/es1/.*$'
    age:
      - age10ak0…  # users.alice.laptop
      - age1yubikey1q2na…  # yubikey.everyday
      …
```

Commit the rendered file, so plain `sops`, editor plugins and CI keep working without
sops-compose installed.

## Layout and references

- `sops/keys/<namespace>.yaml`: keys, as `name: age1…`. Nested maps add dotted segments
  (`users.alice.laptop`). The file name is the namespace.
- `sops/groups.yaml`: `name: [references…]`. Optional.
- `sops/rules.yaml`: an ordered list of rules with `path_regex` and `age` (one reference or a list).

A **reference** is one of:
- a key name (`hosts.es1`)
- a namespace or subtree, meaning every key under it (`yubikey`, `users.alice`)
- a group name
- `all`, meaning every key

Recipients are flattened and deduplicated.

These are hard errors: unknown references, group cycles, a group named like a namespace or `all`,
the same age key under two names, and a **shadowed rule**: one that matches tracked files, but an
earlier rule wins every one of them. A rule that matches no tracked file, or a key no rule uses,
gets a warning.

See [CONTEXT.md](CONTEXT.md) for the vocabulary.

## Commands

Run them from anywhere inside the repo; the root is the nearest directory with `sops/rules.yaml`.
Pass `--root` to override.

| Command | Does |
|---|---|
| `sops-compose render` | Write `.sops.yaml`. Refuses (exit 1) on errors. |
| `sops-compose check` | Exit 1 on errors, or if `.sops.yaml` differs from a fresh render (stale or hand-edited). |
| `sops-compose explain <path>…` | Show the rule sops would use for each path, with recipients by name. |
| `sops-compose add-key <name> <age-key> [--comment …]` | Add or update a key (keeps comments), then render. |
| `sops-compose grant <ref> <path>… [--with <ref>]… [--allow-broad] [--note …]` | Make `<ref>` a recipient of each path, then render. |

`grant` looks at the rule sops would use for each path:
- **The ref is already a recipient:** nothing changes.
- **A rule matches without it:** the ref is appended to that rule. It refuses if the rule also
  covers other tracked files, unless you pass `--allow-broad`.
- **No rule matches:** a rule for exactly that path (`^path$`) is appended at the end, with the ref
  plus any `--with` recipients.

## Keeping `.sops.yaml` fresh

- **A sops wrapper** that renders first, so sops never runs on a stale config. For example, in a
  devenv shell:
  ```nix
  scripts.sops.exec = ''sops-compose render >/dev/null && exec ${pkgs.sops}/bin/sops "$@"'';
  ```
- **A pre-commit hook** that re-renders and fails the commit if anything changed, so you can stage
  the file. With [git-hooks.nix](https://github.com/cachix/git-hooks.nix) / devenv:
  ```nix
  git-hooks.hooks.sops-compose = {
    enable = true;
    entry = "sops-compose render";
    files = "^(sops/|\\.sops\\.yaml$)";
    pass_filenames = false;
  };
  ```
  With plain [pre-commit](https://pre-commit.com):
  ```yaml
  - repo: https://github.com/thalin/sops-compose
    rev: v0.1.0
    hooks: [{ id: sops-compose }]
  ```
- `sops-compose check` in CI or a `just check` recipe as a backstop.

## Install

```sh
nix run github:thalin/sops-compose -- render
```

or add `github:thalin/sops-compose` as a flake input and use `packages.<system>.default`.
`nix flake check` runs the test suite.

## Companion

[noa-install](https://github.com/thalin/noa-install) provisions NixOS hosts with nixos-anywhere.
When a secrets repo has a `sops/` directory, it registers each new host's key with
`sops-compose add-key` and grants it access with `sops-compose grant`.

## License

MIT
