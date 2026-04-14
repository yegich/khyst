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

Derive the slug from the title:
- Lowercase
- Replace non-alphanumeric characters with hyphens
- Collapse consecutive hyphens
- Trim to 50 characters
- Strip leading/trailing hyphens

Worktree folder: `{repo}-{N}-{slug}` (e.g. `khyst-1-git-worktree-management`)
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

### 7. Create CLAUDE.md in the worktree

Write a `CLAUDE.md` file inside the new worktree directory.

For issues:
```markdown
# Issue #{N}: {title}

{issue_url}

## Description

{issue_body}

## Branch

`{branch_name}`
```

For custom names:
```markdown
# {name}

## Branch

`{branch_name}`
```

### 8. Report

After processing all arguments, print a summary table:

```
| Worktree | Branch | Source |
|----------|--------|--------|
| ../khyst-1-git-worktree-management | khyst-1-git-worktree-management | Issue #1 |
| ../khyst-auth-refactor | khyst-auth-refactor | custom |
```

Include the absolute paths so the user can `cd` into them.
