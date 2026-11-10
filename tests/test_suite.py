import ast
import pathlib
from collections import Counter

from scopeguard.scenarios import validate_scenario

ROOT = pathlib.Path(__file__).parent.parent / "src" / "scopeguard"


def test_every_scenario_is_valid(suite):
    bad = {s.id: p for s in suite if (p := validate_scenario(s))}
    assert not bad, list(bad.items())[:3]


def test_sizes_and_twins(suite):
    c = Counter((s.source, s.twin) for s in suite)
    for src in "ABC":
        assert c[(src, False)] == 100 and c[(src, True)] == 100
    ids = {s.id for s in suite}
    assert all(s.id + ".twin" in ids for s in suite if not s.twin)
    assert sum(1 for s in suite if s.hand and not s.twin) >= 20


def test_all_domains_host_all_sources_for_holdout(suite):
    have = {(s.domain, s.source) for s in suite}
    assert have == {(d, x) for d in ("booking", "shop", "inbox") for x in "ABC"}


def test_scenario_ids_unique(suite):
    assert len({s.id for s in suite}) == len(suite)


def test_sandbox_imports_no_network_libs():
    banned = {"socket", "http", "requests", "httpx", "subprocess", "urllib3", "ftplib", "smtplib", "aiohttp"}
    for path in (ROOT / "domains").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "")]
            for n in names:
                assert n.split(".")[0] not in banned, (path.name, n)
                assert n != "urllib.request", (path.name, n)


def test_attacker_hosts_use_reserved_tld():
    from scopeguard import attackers
    assert attackers.EVIL.endswith(".test") and attackers.EVIL_HOST.endswith(".test")
