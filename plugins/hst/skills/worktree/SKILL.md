---
name: worktree
description: Create git worktrees from GitHub issue numbers, URLs, or custom names. Accepts multiple arguments to create several worktrees at once.
allowed-tools: Read, Write, Bash, Glob, Grep
---

Create git worktrees as sibling directories to the current repo.

## Input

`$ARGUMENTS` contains one or more space-separated arguments. Each argument is one of:

- **Issue number** (digits only, e.g. `1`, `42`) — fetch the GitHub issue and derive the worktree name from it
- **GitHub issue URL** (e.g. `https://github.com/owner/repo/issues/7`) — extract the issue number and repo
- **Custom name** (anything else, e.g. `auth-refactor`) — use directly as the worktree/branch name

## Steps

For each argument:

### 1. Determine repo context

Run `basename $(git rev-parse --show-toplevel)` to get the repo name (e.g. `khyst`).

### 2. Classify the argument

- If it matches `^[0-9]+$` → it's an issue number
- If it contains `github.com` and `/issues/` → extract the issue number (and `--repo owner/repo` if it's a different repo)
- Otherwise → it's a custom name

### 3. For issue numbers

Fetch the issue:
```
gh issue view {N} --json number,title,body,url
```

Derive the slug by **reading the issue title (and body if it helps) and writing a short, descriptive kebab-case phrase** — do not mechanically truncate the title. The slug goes in a filesystem path and a branch name, so it needs to be short enough to type and informative enough to remember which worktree is which.

### Slug rules
- **Length:** aim for 2–4 tokens, ~20 characters max. Shorter is fine when the essence fits in fewer words.
- **Format:** `[a-z0-9-]+` only — lowercase, kebab-case, no other punctuation, no leading/trailing hyphens.
- **Keep** identifying markers when present: milestone tags (`phase-1-1`, `v2`, `rc-3`), ticket IDs, version numbers.
- **Keep** the most distinguishing noun or verb — the "what this worktree is for" (`scaffold`, `migration`, `rate-limiter`, `retry`, `flaky-test`).
- **Drop** generic filler: *implement, add, update, fix the …*; language names obvious from the repo (`go`, `python`, `ts`); scaffolding nouns (`project, module, package`); parenthetical detail; common stop words.
- If the title is already short and clean, just lowercase + hyphenate it.

### Examples

| Issue title | Slug |
|---|---|
| *Phase 1.1: Go project scaffold (chi router, health check)* | `phase-1-1-scaffold` |
| *Implement authentication flow with JWT* | `auth-jwt` |
| *Add retry logic to the payment processor* | `payment-retry` |
| *v2: migrate users table to UUIDs* | `v2-users-uuid` |
| *Fix flaky TestConcurrentBookings in CI* | `flaky-bookings` |
| *Git worktree management* | `worktree-mgmt` |

Worktree folder: `{repo}-{N}-{slug}` (e.g. `khyst-1-worktree-mgmt`, `bayka-4-phase-1-1-scaffold`)
Branch name: same as folder name

### 4. For custom names

Worktree folder: `{repo}-{name}` (e.g. `khyst-auth-refactor`)
Branch name: same as folder name

### 5. Check for conflicts

Check if `../{worktree_folder}` already exists. If it does, report it and skip to the next argument.

### 6. Create the worktree

From the git root, run:
```
git worktree add ../{worktree_folder} -b {branch_name}
```

If the branch already exists (error from git), retry without `-b`:
```
git worktree add ../{worktree_folder} {branch_name}
```

### 7. Report

After processing all arguments, print a summary table:

```
| Worktree | Branch | Source |
|----------|--------|--------|
| ../khyst-1-git-worktree-management | khyst-1-git-worktree-management | Issue #1 |
| ../khyst-auth-refactor | khyst-auth-refactor | custom |
```

Include the absolute paths so the user can `cd` into them.
