from conftest import K, write


def test_check_passes_when_fresh(repo, run):
    run(repo, "render")
    code, out, _ = run(repo, "check")
    assert code == 0 and "up to date" in out


def test_check_fails_when_missing(repo, run):
    code, _, err = run(repo, "check")
    assert code == 1 and "missing" in err


def test_check_fails_when_sources_change(repo, run):
    run(repo, "render")
    write(repo, "sops/groups.yaml", "me: [users.admin]\n")
    code, _, err = run(repo, "check")
    assert code == 1 and "stale" in err


def test_check_fails_on_hand_edit(repo, run):
    run(repo, "render")
    out = repo / ".sops.yaml"
    out.write_text(out.read_text().replace("# hosts.alpha", "# edited"))
    code, _, err = run(repo, "check")
    assert code == 1 and "edited by hand" in err


def test_explain(repo, run):
    code, out, _ = run(repo, "explain", str(repo / "systems/alpha/a.yaml"))
    assert code == 0
    assert "systems/alpha/a.yaml: rule 2 (systems/alpha/.*$)" in out
    assert f"hosts.alpha  {K['alpha']}" in out


def test_explain_unmatched(repo, run):
    code, out, _ = run(repo, "explain", str(repo / "nothing/here.yaml"))
    assert code == 1 and "no rule matches" in out


def test_root_is_found_from_a_subdirectory(repo, capsys, monkeypatch):
    from sops_compose.cli import main
    monkeypatch.chdir(repo / "systems" / "alpha")
    assert main(["explain", "a.yaml"]) == 0
    assert "systems/alpha/a.yaml: rule 2" in capsys.readouterr().out
