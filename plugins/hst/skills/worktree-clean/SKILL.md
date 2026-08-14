---
name: worktree-clean
description: Remove sibling git worktrees (../{repo}-*) via an interactive multi-select picker, tearing down each one's Docker Compose stack with it. Branches and volumes are left intact.
allowed-tools: Bash
---

Remove sibling git worktrees created by the `worktree` skill. Primary picker is `fzf --multi`; falls back to a numbered list when fzf isn't available.

## Steps

### 1. Enumerate candidate worktrees

From the current repo, determine siblings:

```sh
root=$(git rev-parse --show-toplevel)
repo=$(basename "$root")
parent=$(dirname "$root")
git worktree list --porcelain
```

Parse `worktree <path>` / `branch refs/heads/<name>` pairs. Keep entries where:
- path's parent equals `$parent`
- basename starts with `${repo}-`
- path is **not** `$root` (exclude current worktree)

If none, print `No sibling worktrees to clean.` and stop.

### 2. Ensure fzf is installed

Probe `command -v fzf`. If it is **not** present, you MUST first run step 3 (offer to install). Do not proceed to the numbered-list fallback until the user has explicitly declined the install offer. Only after install succeeds or is declined, continue below.

Once fzf is available, feed candidates to:

```sh
fzf --multi --height=60% --reverse \
    --header='space: toggle   ctrl-a: select all   enter: confirm' \
    --bind 'ctrl-a:toggle-all' \
    --prompt='worktrees to remove> '
```

Each input line: `<path>\t<branch>`. Capture selected lines.

- Exit 0, empty output → user confirmed nothing → print `Nothing selected.` and stop.
- Exit 130 (esc/ctrl-c) → print `Cancelled.` and stop.
- TTY-related failure (`Failed to get the terminal`, `stdin is not a tty`, etc.) → go to step 4 (numbered fallback); installing won't help.

### 3. Offer to install fzf if missing

If `fzf` is not on PATH, detect a package manager and ask:

| OS / PM     | Check            | Install command            |
|-------------|------------------|----------------------------|
| Homebrew    | `command -v brew`| `brew install fzf`         |
| apt         | `command -v apt-get` | `sudo apt-get install -y fzf` |
| dnf         | `command -v dnf` | `sudo dnf install -y fzf`  |
| pacman      | `command -v pacman` | `sudo pacman -S --noconfirm fzf` |

Prompt: `fzf isn't installed. Install with `{cmd}`? (y/N/skip)`

- `y` / `yes` → run the command, then retry step 2.
- anything else, or no package manager detected → continue to step 4.

### 4. Numbered-list fallback

Print:

```
#  worktree                         branch
1  ../khyst-1-worktree-mgmt         khyst-1-worktree-mgmt
2  ../khyst-auth-refactor           khyst-auth-refactor
```

Ask: `Which to remove? (e.g. 1,3-5 or 'all', empty to cancel)`

Parse the user's next reply:
- `all` → all candidates
- comma/range list (`1,3-5`) → resolve to indices; ignore out-of-range with a warning
- empty → print `Cancelled.` and stop

### 5. Confirm

Show the resolved selection and ask: `Remove these N worktrees? (y/N)`. Proceed only on `y`/`yes`.

If any selected worktree has a live Compose stack (step 6 explains how to tell), say so in the same breath — e.g. `2 of these have a running Compose stack, which will be stopped.` The user is agreeing to both.

### 6. Remove

For each selected path, tear down its Compose stack first, then remove the worktree.

#### 6a. The Compose stack

A worktree that runs its own services leaves them behind: `git worktree remove` deletes the directory, and the containers and networks keep running, attached to nothing. They accumulate — one project per worktree — until something that needs a fresh network fails with `all predefined address pools have been fully subnetted`, which reads as a Docker problem rather than an uncleaned worktree.

Compose derives its project name from the directory name, so a worktree at `../{repo}-{slug}` owns the project `{repo}-{slug}`. **Probe before acting** — an explicit `COMPOSE_PROJECT_NAME`, or a `name:` in the compose file, means the guess is wrong, and tearing down a project you inferred rather than observed is how you stop something you did not mean to:

```sh
command -v docker >/dev/null 2>&1 || skip          # no docker, nothing to do
proj=$(basename "<path>")
docker compose -p "$proj" ps -q 2>/dev/null | grep -q . || skip   # no such stack
docker compose -p "$proj" down
```

Notes:

- **No `-v`.** `down` removes containers and networks; named volumes survive. A worktree's database usually holds throwaway data, but "usually" is not a licence to delete someone's volume on the way past — and a volume left behind costs a little disk, while a volume deleted by surprise costs the afternoon.
- A missing `docker`, or a worktree that never ran a stack, is a **no-op, not a failure**. Most worktrees are just directories.
- A teardown that errors does not block removing the worktree. Report it and carry on: the worktree is the thing the user asked to remove.

#### 6b. The worktree

```sh
git worktree remove <path>
```

On failure matching `contains modified or untracked files` or `is dirty`, ask per-item: `{path} is dirty. Force remove? (y/N)`. On `y`, retry with `--force`. Otherwise mark it `skipped`.

If the user declines to force-remove a dirty worktree, its stack is already down — say so in the report rather than leaving them to discover it. Bringing it back is one `docker compose up` in that directory.

Do **not** delete branches.

### 7. Report

Summary table:

```
| Worktree | Branch | Compose | Result |
|----------|--------|---------|--------|
| /abs/path/khyst-1-... | khyst-1-... | stopped | removed |
| /abs/path/khyst-auth-refactor | khyst-auth-refactor | none | removed |
| /abs/path/khyst-spike | khyst-spike | stopped | skipped (dirty) |
```

Use absolute paths. `Compose` is `stopped`, `none` (no stack, or no docker), or `failed: {reason}` — never blank, so "there was nothing to stop" is visibly different from "nobody looked."
