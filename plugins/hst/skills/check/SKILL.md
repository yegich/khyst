---
name: check
description: Run a project's test + lint pack as a pre-commit gate. Discovers commands once from project shape (go.mod, package.json, pyproject.toml, Cargo.toml, Makefile), persists them to .hst/checks.yaml, and runs them on demand or via a git/Claude hook. Language-agnostic.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

Run a project's test + lint pack as a pre-commit gate, language-agnostic.

The skill has three modes, controlled by `$ARGUMENTS`:

| `$ARGUMENTS` | Mode | What it does |
|---|---|---|
| empty or `--gate` | **Gate** (default) | Reads `.hst/checks.yaml` and runs every command in `on_commit` sequentially. Aborts on the first failure. |
| `--discover` | **Discover** | Scans the repo for project-shape signals, proposes a `.hst/checks.yaml`, asks the user to confirm/edit, writes the file. |
| `--install-claude-hook` | **Install Claude hook** | Adds a `PreToolUse` matcher to `.claude/settings.json` so `git commit` from a Claude Code session triggers the gate. |
| `--install-git-hook` | **Install git hook** | Writes `.git/hooks/pre-commit` calling `hst-check --gate`. Works for both human and Claude commits. |

If the user types `/hst:check` with no arguments and `.hst/checks.yaml` does not exist, run **Discover** first, then fall through to the gate.

## Gate mode

### 1. Read `.hst/checks.yaml`

If the file does not exist, fall back to `--discover` (after asking the user). If it exists but has no `on_commit:` block, print a notice and exit 0 (nothing to gate).

The file shape:

```yaml
# .hst/checks.yaml
on_commit:
  - go vet ./...
  - go test -race ./...
  - golangci-lint run ./...
on_push:
  - POSTGRES_DSN=$POSTGRES_DSN go test -tags=integration -race ./...
```

Both keys are arrays of shell command strings. `on_commit` is the default the gate runs; `on_push` is reserved for callers that explicitly want the slower set (`--gate on_push`).

### 2. Run each command in order

For each command in the chosen list:
- Print `[hst:check] running: <cmd>`
- Execute via `bash -c "<cmd>"` from the repo root
- On non-zero exit, stop and report the failed command + its exit code; the skill returns failure
- On success, move to the next

Exit 0 only if every command succeeded.

If `bin/hst-check` is on PATH (installed by the plugin's session-start hook), the skill SHOULD shell out to `hst-check --gate <list>` rather than re-implementing the runner. The CLI form is the canonical one — see `bin/hst-check` in this plugin.

## Discover mode

The goal: write a sensible `.hst/checks.yaml` for the current repo by reading what already exists. Do not run any commands during discovery.

### 1. Detect signals

Walk the repo root for these files (top-level only — monorepos can be revisited later):

| Signal file | Proposed `on_commit` entries |
|---|---|
| `go.mod` | `go vet ./...`, `go test -race ./...`. If `.golangci.yml` / `.golangci.yaml` / `.golangci.toml` exists, also add `golangci-lint run ./...`. |
| `package.json` (with a `scripts.test` field) | `npm test`. If `scripts.lint` exists, also `npm run lint`. |
| `pyproject.toml` or `setup.py` | `pytest`. If `ruff.toml` / `[tool.ruff]` / `.flake8` / `setup.cfg` linter config detected, add `ruff check .` (preferred) or `flake8`. |
| `Cargo.toml` | `cargo test`, `cargo clippy --all-targets -- -D warnings`. |
| `Makefile` with a `test:` and/or `lint:` target | `make test`, `make lint` — and skip the auto-detected commands above for the matched language (the Makefile is the explicit user choice). |
| `Gemfile` | `bundle exec rspec` if `spec/` exists; `bundle exec rubocop` if a `.rubocop.yml` exists. |

Multi-language repos: include entries for every signal that fires. The user can prune in `.hst/checks.yaml`.

### 2. Show the proposal

Print:

```
[hst:check] Discovered project signals:
  - go.mod         → go vet ./..., go test -race ./...
  - .golangci.yml  → golangci-lint run ./...
  - workflow/      (Python — but no test runner detected; skipping)

Proposed .hst/checks.yaml:
  on_commit:
    - go vet ./...
    - go test -race ./...
    - golangci-lint run ./...

Save this? (y/N/edit)
```

### 3. Save with the user's chosen content

- `y` / `yes` → write the proposal as-is.
- `edit` → open the proposal in `$EDITOR` (or `vi` if unset), then write what the user saved.
- anything else → cancel; do not write.

The file MUST live at `.hst/checks.yaml` relative to the repo root (`git rev-parse --show-toplevel`). Create `.hst/` if missing. Append `.hst/` to `.gitignore` only if the user opts in (default no — the file is intended to be committed so the whole team shares the same gate).

### 4. Print next-step guidance

After writing, suggest:

```
[hst:check] Saved .hst/checks.yaml.

Wire it as a pre-commit gate:
  /hst:check --install-git-hook       # blocks all commits, human or Claude
  /hst:check --install-claude-hook    # blocks Claude-issued git commit calls only
```

## --install-git-hook

Write `.git/hooks/pre-commit` with content:

```sh
#!/usr/bin/env sh
exec hst-check --gate
```

Make it executable. If the file already exists and does NOT call `hst-check`, abort with a message — refuse to overwrite a hand-rolled hook. If the existing hook already calls `hst-check`, do nothing.

`hst-check` is installed to `~/.local/bin/` by the plugin's session-start `bin/install.sh`. If `~/.local/bin/` is not on PATH, the install script already prints guidance for adding it; mention that here too.

## --install-claude-hook

Edit (or create) `.claude/settings.json` to add a `PreToolUse` matcher on `Bash` that runs `hst-check --gate` whenever the command starts with `git commit`. Sketch:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "case \"$CLAUDE_TOOL_INPUT_command\" in 'git commit'*) hst-check --gate || exit 1 ;; esac"
          }
        ]
      }
    ]
  }
}
```

If `.claude/settings.json` already exists, merge the new matcher into the existing `hooks.PreToolUse` array; do not overwrite. If the matcher is already present, do nothing.

## Notes on design

- **`.hst/checks.yaml` is the source of truth.** Discovery just seeds it. New languages add a discovery rule; the file format never changes.
- **The skill avoids opinions about which checks should be in the gate.** Whatever the file says, the gate runs.
- **Gate runs are sequential, fail-fast.** A long Go test pack failing first means the lint isn't even attempted — that's intentional. Cheap commands (vet, lint) belong before expensive ones (race-tagged tests) — Discover seeds them in a sensible order, but the user can reorder.
- **Hooks are opt-in.** The skill never installs a hook implicitly; a `--install-*-hook` invocation is required. Removing a hook is out of scope — `git config core.hooksPath` and `.claude/settings.json` are the user's domain.
