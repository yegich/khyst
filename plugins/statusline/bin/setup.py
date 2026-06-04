#!/usr/bin/env python3
"""One-time setup for the khyst statusline plugin.

Edits ~/.claude/settings.json so the plugin's statusline takes effect globally:
- Adds "statusline@khyst" to enabledPlugins (so the plugin is active in every project).
- Removes any existing user-level "statusLine" block (user-level > plugin-level,
  so an existing block would silently override the plugin's declaration).

Safe by default: prints the diff and asks for confirmation. Backs up to
~/.claude/settings.json.<timestamp>.bak before writing.

Flags:
  --dry-run   Print the diff and exit without writing.
  --yes / -y  Skip the confirmation prompt (still backs up).
  --force     Allow removing a custom statusLine that does NOT point at our plugin
              (default: refuse if it looks like a different intentional config).
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

PLUGIN_KEY = "statusline@khyst"
SETTINGS = Path.home() / ".claude" / "settings.json"


def load_settings() -> dict:
    if not SETTINGS.exists():
        return {}
    raw = SETTINGS.read_text().strip()
    if not raw:
        return {}
    return json.loads(raw)


def existing_statusline_is_ours(block: dict) -> bool:
    """Return True if the existing statusLine block already points at our plugin."""
    if not isinstance(block, dict):
        return False
    cmd = block.get("command", "")
    return "statusline" in cmd and "khyst" in cmd or "${CLAUDE_PLUGIN_ROOT}" in cmd and "statusline" in cmd


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    yes = "--yes" in args or "-y" in args
    force = "--force" in args

    settings = load_settings()
    changes: list[tuple[str, str, object]] = []

    enabled = settings.get("enabledPlugins", {}) or {}
    if enabled.get(PLUGIN_KEY) is not True:
        changes.append(("add", f"enabledPlugins.{PLUGIN_KEY}", True))

    existing = settings.get("statusLine")
    refuse_reason: str | None = None
    if existing is not None:
        if existing_statusline_is_ours(existing):
            pass
        elif force:
            changes.append(("remove", "statusLine", existing))
        else:
            existing_cmd = existing.get("command", "<no command>") if isinstance(existing, dict) else str(existing)
            refuse_reason = (
                f"Existing statusLine points at: {existing_cmd}\n"
                f"This does not look like our plugin. Refusing to remove it without --force."
            )

    if refuse_reason:
        print(refuse_reason)
        print("\nOptions:")
        print("  1. Remove your existing statusLine from ~/.claude/settings.json manually, rerun this.")
        print("  2. Re-run with --force to overwrite (a backup will be made).")
        return 2

    if not changes:
        print("Already configured. No changes needed.")
        return 0

    print("Planned changes to ~/.claude/settings.json:")
    for kind, path, value in changes:
        rendered = json.dumps(value, separators=(", ", ": "))
        if len(rendered) > 100:
            rendered = rendered[:97] + "..."
        symbol = "+" if kind == "add" else "-"
        print(f"  {symbol} {path} = {rendered}")

    if dry_run:
        print("\n--dry-run: not applying.")
        return 0

    if not yes:
        resp = input("\nApply these changes? [y/N] ").strip().lower()
        if resp not in ("y", "yes"):
            print("Aborted.")
            return 1

    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    if SETTINGS.exists():
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup = SETTINGS.parent / f"settings.json.{ts}.bak"
        shutil.copy2(SETTINGS, backup)
        print(f"Backed up: {backup}")

    enabled[PLUGIN_KEY] = True
    settings["enabledPlugins"] = enabled
    if "statusLine" in settings:
        del settings["statusLine"]

    SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Updated: {SETTINGS}")
    print("Restart Claude Code (or open a new session) to see the new statusline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
