---
description: One-time setup for the khyst statusline plugin. Edits ~/.claude/settings.json so the plugin's statusline takes effect globally (adds enabledPlugins entry, removes any existing user-level statusLine block). Backs up the file and prints a diff before applying. Use this once after `/plugin install statusline@khyst`.
argument-hint: [--dry-run | --force | --yes]
allowed-tools: Bash
---

Run the setup script that ships with this plugin:

```
python3 ${CLAUDE_PLUGIN_ROOT}/bin/setup.py $ARGUMENTS
```

Default behavior:
1. Reads `~/.claude/settings.json`.
2. Plans the changes: add `enabledPlugins.statusline@khyst = true`, remove any existing `statusLine` block (so the plugin's declaration can take effect — user-level always wins over plugin-level).
3. Prints the diff.
4. **The script will refuse to remove a `statusLine` block that doesn't already point at our plugin, unless `--force` is passed** — that protects the user's existing config from silent overwrites.
5. With `--dry-run` the script prints the diff and exits without writing.
6. With `--yes` the script skips the interactive prompt.
7. Backs up `~/.claude/settings.json` to `~/.claude/settings.json.<timestamp>.bak` before writing.

Since this is invoked via Claude Code (not a real TTY), prefer this two-step flow when no flags are passed:

1. Run with `--dry-run` first and show the user the planned diff in the conversation.
2. Ask the user whether to apply.
3. If they agree, run with `--yes` to apply non-interactively.

If the script refuses with a "does not look like our plugin" message, surface that to the user and let them decide whether to re-run with `--force`.
