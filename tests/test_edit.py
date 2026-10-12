import yaml

from conftest import K

# Made up: only needs to look like an age key, nothing is ever encrypted to it.
NEW = "age1zqy8vmm5gq0n5m0yp9n6a5w8mmkqm0f4c6n7d0yqxkw0xg9sqx0s0p4h5k"


def rules_src(repo):
    return yaml.safe_load((repo / "sops/rules.yaml").read_text())


def rendered(repo):
    return yaml.safe_load((repo / ".sops.yaml").read_text())["creation_rules"]


# --- add-key

def test_add_key_preserves_comments_and_renders(repo, run):
    code, out, _ = run(repo, "add-key", "hosts.delta", NEW, "--comment", "new box")
    assert code == 0 and "hosts.delta: added" in out
    text = (repo / "sops/keys/hosts.yaml").read_text()
    assert "# Hosts" in text and "# first host" in text
    assert f"delta: {NEW} # new box" in text
    # Rendered straight away: `all` now includes the new key.
    assert NEW in rendered(repo)[0]["age"]


def test_add_key_keeps_comments_in_a_file_with_no_keys_yet(repo, run):
    (repo / "sops/keys/servers.yaml").write_text("# Server keys, managed by noa-install\n")
    code, _, err = run(repo, "add-key", "servers.delta", NEW, "--comment", "x")
    assert code == 0, err
    text = (repo / "sops/keys/servers.yaml").read_text()
    assert text.startswith("# Server keys, managed by noa-install\n")
    assert f"delta: {NEW} # x" in text


def test_add_key_is_idempotent(repo, run):
    run(repo, "add-key", "hosts.delta", NEW)
    before = (repo / "sops/keys/hosts.yaml").read_text()
    code, out, _ = run(repo, "add-key", "hosts.delta", NEW)
    assert code == 0 and "unchanged" in out
    assert (repo / "sops/keys/hosts.yaml").read_text() == before


def test_add_key_updates_a_rotated_key(repo, run):
    code, out, _ = run(repo, "add-key", "hosts.alpha", NEW)
    assert code == 0 and "updated" in out
    assert NEW in (repo / "sops/keys/hosts.yaml").read_text()
    assert K["alpha"] not in (repo / ".sops.yaml").read_text()


def test_add_key_creates_nested_namespace_file(repo, run):
    code, _, _ = run(repo, "add-key", "yubikey.backup.nano", NEW)
    assert code == 0
    assert yaml.safe_load((repo / "sops/keys/yubikey.yaml").read_text()) == {"backup": {"nano": NEW}}


def test_add_key_refuses_a_key_already_named_elsewhere(repo, run):
    code, _, err = run(repo, "add-key", "hosts.delta", K["alpha"])
    assert code == 1 and "already named hosts.alpha" in err


def test_add_key_refuses_to_replace_a_namespace(repo, run):
    code, _, err = run(repo, "add-key", "users.admin", NEW)
    assert code == 1 and "is a namespace" in err


def test_add_key_rejects_non_age_keys(repo, run):
    code, _, err = run(repo, "add-key", "hosts.delta", "ssh-ed25519 AAAA")
    assert code == 1 and "not an age public key" in err


# --- grant

def test_grant_is_a_noop_when_already_a_recipient(repo, run):
    before = (repo / "sops/rules.yaml").read_text()
    code, out, _ = run(repo, "grant", "hosts.gamma", str(repo / "secrets.yaml"))
    assert code == 0 and "already a recipient" in out
    assert (repo / "sops/rules.yaml").read_text() == before


def test_grant_extends_the_matching_rule(repo, run):
    code, out, _ = run(repo, "grant", "hosts.gamma", str(repo / "systems/alpha/a.yaml"))
    assert code == 0 and "added hosts.gamma to rule 2" in out
    assert rules_src(repo)[2]["age"] == ["me", "hosts.alpha", "hosts.gamma"]
    assert K["gamma"] in rendered(repo)[2]["age"]
    # The rest of the file, comments included, is left alone.
    assert (repo / "sops/rules.yaml").read_text().startswith("# Shared\n")


def test_grant_turns_a_single_reference_into_a_list(repo, run):
    code, _, _ = run(repo, "grant", "hosts.beta", str(repo / "systems/beta/sshkeys/ed25519.yaml"),
                     "--allow-broad")
    assert code == 0
    assert rules_src(repo)[1]["age"] == ["me", "hosts.beta"]


def test_grant_refuses_a_broad_rule(repo, run):
    (repo / "systems/alpha/sshkeys").mkdir(parents=True)
    (repo / "systems/alpha/sshkeys/ed25519.yaml").write_text("")
    import subprocess
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    before = (repo / "sops/rules.yaml").read_text()
    code, _, err = run(repo, "grant", "hosts.beta", str(repo / "systems/beta/sshkeys/ed25519.yaml"))
    assert code == 1
    assert "also covers systems/alpha/sshkeys/ed25519.yaml" in err and "--allow-broad" in err
    assert (repo / "sops/rules.yaml").read_text() == before


def test_grant_appends_a_rule_when_none_matches(repo, run):
    code, out, err = run(repo, "grant", "hosts.gamma", str(repo / "systems/gamma/app.env"),
                         "--with", "me", "--note", "added by noa-install for gamma")
    assert code == 0, err
    assert "no rule matched" in out
    src = (repo / "sops/rules.yaml").read_text()
    assert "# added by noa-install for gamma" in src
    last = rules_src(repo)[-1]
    assert last == {"path_regex": r"^systems/gamma/app\.env$", "age": ["hosts.gamma", "me"]}
    assert rendered(repo)[-1]["path_regex"] == r"^systems/gamma/app\.env$"


def test_grant_warns_about_a_single_recipient_rule(repo, run):
    code, out, _ = run(repo, "grant", "hosts.gamma", str(repo / "systems/gamma/app.env"))
    assert code == 0 and "single recipient" in out
