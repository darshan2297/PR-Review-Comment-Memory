import json

from team_coding_dna import mcp_server


def test_mine_without_token_or_cache_returns_hint(tmp_path, monkeypatch):
    # No git remote (tmp dir), no token, no cache -> graceful guidance, no crash.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    out = json.loads(mcp_server.mine())

    assert out["clusters"] == []
    assert "hint" in out
    assert "GITHUB_TOKEN" in out["hint"]


def test_mine_reads_cache_when_present(tmp_path, monkeypatch):
    # A prior `dna mine` cache is returned when no token is set.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cache_dir = tmp_path / ".dna"
    cache_dir.mkdir()
    sample = [{"representative": "use Decimal for money", "count": 3}]
    (cache_dir / "clusters.json").write_text(json.dumps(sample), encoding="utf-8")

    out = json.loads(mcp_server.mine())

    assert out["source"] == "cache"
    assert out["clusters"] == sample
