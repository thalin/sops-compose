import pytest

from conftest import K, git_add, write


def expect_error(run, repo, needle, *args):
    code, _, err = run(repo, *(args or ("render",)))
    assert code == 1
    assert needle in err
    return err


def test_unknown_reference(repo, run):
    write(repo, "sops/groups.yaml", "me: [users.admin, hosts.nope]\n")
    expect_error(run, repo, "unknown reference 'hosts.nope'")


def test_group_cycle(repo, run):
    write(repo, "sops/groups.yaml", "me: [you]\nyou: [me]\n")
    expect_error(run, repo, "group cycle")


@pytest.mark.parametrize("name", ["hosts", "all"])
def test_group_name_clashes(repo, run, name):
    write(repo, "sops/groups.yaml", f"{name}: [users]\nme: [users]\n")
    expect_error(run, repo, repr(name))


def test_same_key_under_two_names(repo, run):
    write(repo, "sops/keys/extra.yaml", f"dup: {K['alpha']}\n")
    expect_error(run, repo, "named both")


def test_not_an_age_key(repo, run):
    write(repo, "sops/keys/extra.yaml", "bad: ssh-ed25519 AAAA\n")
    expect_error(run, repo, "not an age public key")


def test_rule_without_age(repo, run):
    write(repo, "sops/rules.yaml", "- path_regex: x\n")
    expect_error(run, repo, "missing age")


def test_invalid_regex(repo, run):
    write(repo, "sops/rules.yaml", "- path_regex: '('\n  age: all\n")
    expect_error(run, repo, "invalid path_regex")


def test_shadowed_rule_is_an_error_and_nothing_is_written(repo, run):
    write(repo, "sops/rules.yaml", r"""
        - path_regex: secrets\.yaml
          age: all
        - path_regex: users/admin/secrets\.yaml
          age: me
    """)
    write(repo, "users/admin/secrets.yaml", "")
    git_add(repo, ".")
    expect_error(run, repo, "rule 1 (users/admin/secrets\\.yaml) is shadowed")
    assert not (repo / ".sops.yaml").exists()


def test_unused_rule_and_key_are_warnings(repo, run):
    write(repo, "sops/rules.yaml", r"""
        - path_regex: ^secrets\.yaml$
          age: [me]
        - path_regex: ^future\.yaml$
          age: [me]
    """)
    code, _, err = run(repo, "render")
    assert code == 0
    assert "rule 1 (^future\\.yaml$) matches no tracked file" in err
    assert "key hosts.alpha is not a recipient of any rule" in err
