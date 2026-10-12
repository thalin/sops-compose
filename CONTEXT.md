# sops-compose glossary

- **Recipient**: one age public key that a secret is encrypted to.
- **Namespace**: the name of a key file under `sops/keys/` (`hosts`, `users`, `yubikey`, …). It's the first segment of every key name in that file.
- **Key name**: the dotted path to one recipient, e.g. `hosts.titan` or `users.thalin.titan`.
- **Reference**: a name used in a group or rule. It points at one key (`hosts.titan`), every key under a subtree (`yubikey`, `users.thalin`), a group, or the built-in `all` (every key).
- **Recipient set**: references, groups, or nestings of them, flattened and deduplicated in resolution order.
- **Group**: a named recipient set, defined in `sops/groups.yaml`. Groups may contain other groups.
- **Rule**: an entry in the ordered `sops/rules.yaml`: a `path_regex`, the recipient set under `age`, and any other sops fields, passed through untouched. As in sops, the first matching rule wins.
- **Shadowed rule**: a rule that matches some tracked file, but every such file is won by an earlier rule. It's an error, because the rule can never apply.
- **Host-keys file**: `sops/keys/hosts.yaml`, the namespace provisioning tools such as noa-install write to.
- **Grant**: making a reference able to decrypt a path, either by extending the path's first-matching rule, or by appending a rule for exactly that path.
- **Render**: turning the sources into `.sops.yaml`, the flat file sops reads. It's committed, and never edited by hand.
