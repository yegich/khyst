#!/usr/bin/env python3
"""Deterministic helpers for /hst:prime-knowledge.

Two jobs that are easy to get subtly wrong by hand and identical on every run:

  status    Which .hst/kb/ artifacts have gone stale, and which path to take.
  hotspots  Churn x size ranking and change coupling, straight from git.

Both print a human summary to stderr and JSON to stdout, so a caller can read
either. No third-party dependencies: the manifest is JSON precisely so this
runs anywhere python3 does.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from itertools import combinations

MANIFEST = ".hst/kb/MANIFEST.json"


def git(args, root, default=""):
    try:
        out = subprocess.run(
            ["git"] + args, cwd=root, capture_output=True, text=True, check=True
        )
        return out.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return default


def repo_root(start):
    root = git(["rev-parse", "--show-toplevel"], start).strip()
    if not root:
        sys.exit("not a git repository")
    return root


def changed_since(sha, root):
    """Paths changed between sha and HEAD. None means the sha is unknown."""
    out = git(["diff", "--name-only", f"{sha}..HEAD"], root, default=None)
    if out is None:
        return None
    return [p for p in out.splitlines() if p]


def touched(watched, changed):
    """Which watched paths the changed set hits.

    A watched entry may be a file or a directory prefix; `migrations/` is hit by
    `migrations/0007_x.sql`. Directories are the common case for sweep lanes.
    """
    hits = []
    for w in watched:
        w_norm = w.rstrip("/")
        for c in changed:
            if c == w_norm or c.startswith(w_norm + "/"):
                hits.append(c)
    return sorted(set(hits))


def cmd_status(args):
    root = repo_root(args.root)
    path = os.path.join(root, MANIFEST)

    if not os.path.exists(path):
        result = {"path": "cold", "reason": "no manifest", "stale": [], "fresh": []}
        print("[prime] cold — no .hst/kb/ yet", file=sys.stderr)
        print(json.dumps(result, indent=2))
        return

    with open(path) as fh:
        man = json.load(fh)

    stale, fresh, unknown = [], [], []

    def check(kind, name, entry):
        sha = entry.get("sha")
        watched = entry.get("files") or []
        changed = changed_since(sha, root) if sha else None
        if changed is None:
            unknown.append(f"{kind}/{name}")
            return
        # An artifact with no watched files (history.md) can't be invalidated
        # by content; refresh it on --deep instead.
        hits = touched(watched, changed) if watched else []
        (stale if hits else fresh).append(
            {"artifact": f"{kind}/{name}", "changed": hits[:20], "n_changed": len(hits)}
        )

    for name, entry in (man.get("base") or {}).items():
        check("base", name, entry)
    for name, entry in (man.get("slices") or {}).items():
        check("slices", name, entry)

    base_stale = [s for s in stale if s["artifact"].startswith("base/")]
    slice_names = list((man.get("slices") or {}).keys())

    if base_stale or not man.get("base"):
        path_name = "cold"
    elif args.slug and args.slug in slice_names and not any(
        s["artifact"] == f"slices/{args.slug}" for s in stale
    ):
        path_name = "hot"
    else:
        path_name = "warm"

    result = {
        "path": path_name,
        "head": git(["rev-parse", "--short", "HEAD"], root).strip(),
        "stale": stale,
        "fresh": [f["artifact"] for f in fresh],
        "unknown_sha": unknown,
        "slices": slice_names,
    }

    print(
        f"[prime] {path_name} — {len(fresh)} fresh, {len(stale)} stale"
        + (f", {len(unknown)} unresolvable sha" if unknown else ""),
        file=sys.stderr,
    )
    for s in stale:
        print(f"  stale: {s['artifact']} ({s['n_changed']} watched files changed)", file=sys.stderr)
    print(json.dumps(result, indent=2))


def cmd_hotspots(args):
    root = repo_root(args.root)
    log = git(
        [
            "log",
            f"--since={args.months} months ago",
            "--pretty=format:%H",
            "--name-only",
            "--no-merges",
        ]
        + (["--", args.path] if args.path else []),
        root,
    )

    commits, current = [], []
    for line in log.splitlines():
        if not line.strip():
            continue
        # A 40-char hex line starts a new commit record.
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
            if current:
                commits.append(current)
            current = []
        else:
            current.append(line)
    if current:
        commits.append(current)

    churn = Counter()
    for files in commits:
        churn.update(files)

    rows = []
    for f, n in churn.items():
        full = os.path.join(root, f)
        if not os.path.isfile(full):
            continue  # deleted or renamed away; not worth studying
        try:
            with open(full, "rb") as fh:
                lines = sum(1 for _ in fh)
        except OSError:
            continue
        rows.append({"file": f, "commits": n, "lines": lines, "score": n * lines})
    rows.sort(key=lambda r: -r["score"])
    rows = rows[: args.top]

    # Change coupling: how often B changes in the same commit as A. Reported as
    # a share of A's own commits, because raw counts just re-rank by churn.
    pair = Counter()
    for files in commits:
        files = [f for f in set(files) if churn[f] >= args.min_commits]
        if len(files) > args.max_commit_size:
            continue  # sweeping refactors couple everything; they teach nothing
        for a, b in combinations(sorted(files), 2):
            pair[(a, b)] += 1

    coupling = []
    for (a, b), n in pair.most_common(args.top * 4):
        share = n / max(churn[a], churn[b])
        if share >= args.min_share:
            coupling.append(
                {"a": a, "b": b, "together": n, "of": max(churn[a], churn[b]),
                 "share": round(share, 2)}
            )
    coupling = coupling[: args.top]

    print(f"[prime] {len(commits)} commits over {args.months} months", file=sys.stderr)
    for r in rows[:10]:
        print(f"  {r['score']:>9}  {r['commits']:>3} x {r['lines']:>5}  {r['file']}", file=sys.stderr)
    print(json.dumps({"hotspots": rows, "coupling": coupling}, indent=2))


def main():
    # --root is accepted on BOTH sides of the subcommand, because argparse binds an
    # option to whichever parser declares it: a top-level-only --root rejects
    # `kb.py status --root R`, which is the form a caller naturally types. The two
    # copies use distinct dests and are merged below -- a shared dest does not work,
    # because a subparser parses into a fresh namespace and copies every attribute
    # onto the parent's, so its default silently overwrites a value given earlier.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", dest="root_sub", default=None,
                        help="path inside the target repo (accepted before or after the subcommand)")

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", dest="root_top", default=None,
                   help="path inside the target repo (accepted before or after the subcommand)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", parents=[common], help="staleness check + path recommendation")
    s.add_argument("--slug", help="slice slug being primed; enables the hot path")
    s.set_defaults(fn=cmd_status)

    h = sub.add_parser("hotspots", parents=[common],
                       help="churn x size ranking and change coupling")
    h.add_argument("--path", help="restrict to a subtree")
    h.add_argument("--months", type=int, default=12)
    h.add_argument("--top", type=int, default=20)
    h.add_argument("--min-commits", type=int, default=3,
                   help="ignore files below this churn when computing coupling")
    h.add_argument("--max-commit-size", type=int, default=25,
                   help="skip commits touching more files than this")
    h.add_argument("--min-share", type=float, default=0.3,
                   help="report a pair only if they change together this often")
    h.set_defaults(fn=cmd_hotspots)

    args = p.parse_args()
    # Nearest wins: a --root after the subcommand overrides one before it.
    args.root = args.root_sub or args.root_top or "."
    args.fn(args)


if __name__ == "__main__":
    main()
