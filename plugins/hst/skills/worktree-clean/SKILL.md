---
name: worktree-clean
description: Remove sibling git worktrees (../{repo}-*) via an interactive multi-select picker. Branches are left intact.
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

### 2. Try fzf picker

Probe `command -v fzf`. If present, feed candidates to:

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

### 6. Remove

For each selected path:

```sh
git worktree remove <path>
```

On failure matching `contains modified or untracked files` or `is dirty`, ask per-item: `{path} is dirty. Force remove? (y/N)`. On `y`, retry with `--force`. Otherwise mark it `skipped`.

Do **not** delete branches.

### 7. Report

Summary table:

```
| Worktree | Branch | Result |
|----------|--------|--------|
| /abs/path/khyst-1-... | khyst-1-... | removed |
| /abs/path/khyst-auth-refactor | khyst-auth-refactor | skipped (dirty) |
```

Use absolute paths.
