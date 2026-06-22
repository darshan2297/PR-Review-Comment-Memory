"""``dna`` — the Team Coding DNA command line (Typer).

    dna init       scaffold a seed git_comment_memory.md
    dna mine       fetch + cluster recurring PR review comments
    dna distill    turn clusters into rules and write the DNA file
    dna serve      start the LLM-less MCP server (stdio)
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import typer

from . import DEFAULT_MEMORY_FILE
from . import memory
from .mining import git_source
from .mining.cluster import cluster_comments
from .mining.github_source import ReviewComment, fetch_review_comments
from .seeds import SEED_RULES

app = typer.Typer(
    add_completion=False,
    help="Mine your team's PR review DNA and serve it to any AI tool via MCP.",
    no_args_is_help=True,
)

CACHE_DIR = Path(".dna")
COMMENTS_CACHE = CACHE_DIR / "comments.json"
CLUSTERS_CACHE = CACHE_DIR / "clusters.json"


def _today() -> str:
    return date.today().isoformat()


@app.command()
def init(
    path: str = typer.Option(DEFAULT_MEMORY_FILE, "--path", help="Where to write the DNA file."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
):
    """Create a seed git_comment_memory.md so the server runs immediately."""
    target = Path(path)
    if target.exists() and not force:
        typer.echo(f"{target} already exists. Use --force to overwrite.")
        raise typer.Exit(code=1)
    repo = git_source.current_repo_slug() or ""
    memory.write(SEED_RULES, target, repo=repo, generated=_today())
    typer.echo(f"Wrote {len(SEED_RULES)} seed rules to {target}")
    typer.echo("Next: edit the rules, or run `dna mine` + `dna distill` on your history.")


@app.command()
def mine(
    repo: str = typer.Option(None, "--repo", help="owner/name (default: origin remote)."),
    since: str = typer.Option("90d", "--since", help="Time window, e.g. 90d, 12w, 6mo, or ISO date."),
    limit: int = typer.Option(50, "--limit", help="Max recently-updated PRs to scan."),
    min_count: int = typer.Option(2, "--min-count", help="Min recurrences to count as DNA."),
    token: str = typer.Option(None, "--token", help="GitHub token (else $GITHUB_TOKEN)."),
):
    """Fetch PR review comments and cluster the recurring ones (read-only)."""
    repo = repo or git_source.current_repo_slug()
    if not repo:
        typer.echo("No --repo given and no github origin remote found.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Mining {repo} (since {since}, up to {limit} PRs)…")
    comments = fetch_review_comments(repo, since=since, limit=limit, token=token)
    typer.echo(f"Fetched {len(comments)} review comments.")

    clusters = cluster_comments(comments, min_count=min_count)
    typer.echo(f"Found {len(clusters)} recurring clusters (min_count={min_count}).")

    CACHE_DIR.mkdir(exist_ok=True)
    COMMENTS_CACHE.write_text(
        json.dumps({"repo": repo, "comments": [c.to_dict() for c in comments]}, indent=2),
        encoding="utf-8",
    )
    CLUSTERS_CACHE.write_text(
        json.dumps([cl.to_dict() for cl in clusters], indent=2), encoding="utf-8"
    )
    typer.echo(f"Cached to {COMMENTS_CACHE} and {CLUSTERS_CACHE}.")
    for cl in clusters[:10]:
        typer.echo(f"  [{cl.count}x] {cl.representative()[:80]}")
    typer.echo("Next: `dna distill` (or let your AI client distill via the `mine` MCP tool).")


@app.command()
def distill(
    path: str = typer.Option(DEFAULT_MEMORY_FILE, "--path", help="DNA file to write/merge into."),
    model: bool = typer.Option(False, "--model", help="Use the optional headless DNA_MODEL (CI)."),
    min_count: int = typer.Option(2, "--min-count", help="Min recurrences to count as DNA."),
):
    """Turn cached clusters into rules and merge them into the DNA file."""
    from .distill import distill as distill_clusters  # local import keeps httpx optional

    if not COMMENTS_CACHE.exists():
        typer.echo("No mining cache found. Run `dna mine` first.", err=True)
        raise typer.Exit(code=1)

    cached = json.loads(COMMENTS_CACHE.read_text(encoding="utf-8"))
    comments = [ReviewComment(**c) for c in cached.get("comments", [])]
    clusters = cluster_comments(comments, min_count=min_count)
    if not clusters:
        typer.echo("No recurring clusters to distill.", err=True)
        raise typer.Exit(code=1)

    existing = memory.parse(path)
    new_rules = distill_clusters(clusters, existing, use_model=model, generated=_today())
    merged = memory.merge(existing, new_rules)
    memory.write(merged, path, repo=cached.get("repo", ""), generated=_today())
    typer.echo(f"Distilled {len(new_rules)} rules; {path} now has {len(merged)} rules.")
    if model:
        typer.echo(f"Used headless model: {os.environ.get('DNA_MODEL', '(unset)')}")


@app.command()
def serve(
    path: str = typer.Option(DEFAULT_MEMORY_FILE, "--path", help="DNA file to serve."),
):
    """Start the MCP server over stdio (runs no LLM of its own)."""
    os.environ["DNA_MEMORY_FILE"] = str(Path(path).resolve())
    from .mcp_server import run  # imported here so `dna --help` stays fast

    run()


if __name__ == "__main__":
    app()
