import subprocess
import textwrap
from pathlib import Path

import pytest

from sops_compose.cli import main

# Throwaway public keys from age-keygen; the identities were discarded.
K = {
    "alpha": "age1hr8s8aqhp7a5lq5cvng9jl55d0qtm24r5g0egff6df8s6sthgyfqhr2t8g",
    "beta": "age157gxkk22knt5mmeccz0jkzy9tkyd53mccngtm54k2l8m09rdm4gs45j4yq",
    "gamma": "age1m954plugdejelz86wdqphaqv56ed8w8sgs9yfttu0mqljryuva8q598x4h",
    "admin": "age14hc2jc42gjaj0slq8f7ptvegqg7672xm5qd70ywe5gqyn8flduvs2gd7vd",
    "token1": "age1q2gs2jshmtnven8r76gpm98vc952hr4lj0lv4hl56e07vffvwuvqvuhdyv",
    "token2": "age14p6h480vh3ce7ehfewl76scpyhh5k5mccm3pdps3klacgfj5kf6q4jqppv",
}


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"))
    return path


def git_add(root: Path, *paths: str) -> None:
    subprocess.run(["git", "add", "--", *paths], cwd=root, check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small secrets repo: three hosts, one user key, two tokens, a group
    and a handful of rules, with secret files tracked in git."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    write(tmp_path, "sops/keys/hosts.yaml", f"""
        # Hosts
        alpha: {K['alpha']} # first host
        beta: {K['beta']}
        gamma: {K['gamma']}
    """)
    write(tmp_path, "sops/keys/users.yaml", f"""
        admin:
          laptop: {K['admin']}
    """)
    write(tmp_path, "sops/keys/tokens.yaml", f"""
        one: {K['token1']}
        two: {K['token2']}
    """)
    write(tmp_path, "sops/groups.yaml", """
        me: [users.admin, tokens]
    """)
    write(tmp_path, "sops/rules.yaml", r"""
        # Shared
        - path_regex: ^secrets\.yaml$
          age: all
        - path_regex: systems/.*/sshkeys/.*\.yaml$
          age: me
        - path_regex: systems/alpha/.*$
          age: [me, hosts.alpha]
        - path_regex: systems/beta/.*$
          age: [me, hosts.beta]
          encrypted_regex: ^(data|stringData)$
    """)
    for f in ["secrets.yaml", "systems/alpha/a.yaml", "systems/beta/b.yaml",
              "systems/beta/sshkeys/ed25519.yaml"]:
        write(tmp_path, f, "x: 1\n")
    git_add(tmp_path, ".")
    return tmp_path


@pytest.fixture
def run(capsys):
    """Run the CLI against a root; returns (exit code, stdout, stderr)."""
    def _run(root: Path, *args: str):
        code = main(["--root", str(root), *args])
        out = capsys.readouterr()
        return code, out.out, out.err
    return _run
