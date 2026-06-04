#!/usr/bin/env python3
"""One-time setup for the khyst statusline plugin.

Edits ~/.claude/settings.json so the plugin's statusline takes effect globally:
- Adds "statusline@khyst" to enabledPlugins (so the plugin is active in every project).
- Writes a user-level "statusLine" block pointing at the plugin's bin/statusline.py.

Why we write the statusLine at the user level rather than relying on the plugin's
own settings.json: in current Claude Code versions a plugin's settings.json
statusLine is not auto-merged into the active config. Writing it to the user's
settings.json is the reliable way to make it take effect, and uses ${HOME} so it
follows the plugin's installed path.

Safe by default: prints the diff and asks for confirmation. Backs up to
~/.claude/settings.json.<timestamp>.bak before writing.

Flags:
  --dry-run   Print the diff and exit without writing.
  --yes / -y  Skip the confirmation prompt (still backs up).
  --force     Allow REPLACING a user-level statusLine that does NOT point at our
              plugin (default: refuse if it looks like a different intentional
              config, so we don't silently clobber the user's setup).
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


def desired_statusline_block() -> dict:
    """Build the statusLine block that points at this plugin's installed script.

    setup.py lives at <plugin_root>/bin/setup.py, so statusline.py is its sibling.
    We translate the absolute path back into a ${HOME}-prefixed string so the
    settings.json is portable across machines where ${HOME} differs.
    """
    script_path = (Path(__file__).resolve().parent / "statusline.py").resolve()
    home = Path.home().resolve()
    try:
        relative = script_path.relative_to(home)
        command_path = "${HOME}/" + str(relative)
    except ValueError:
        command_path = str(script_path)
    return {
        "type": "command",
        "command": f"python3 {command_path}",
    }


def blocks_equal(a: object, b: object) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def existing_block_points_at_plugin(block: object) -> bool:
    """Return True if the existing statusLine block already targets this plugin.

    Loose match — we accept any command containing the plugin path fragment
    `plugins/statusline` or our well-known package id, so users who set this up
    on a different machine path still get treated as configured.
    """
    if not isinstance(block, dict):
        return False
    cmd = block.get("command", "")
    return (
        "statusline@khyst" in cmd
        or "/plugins/statusline/" in cmd
        or "khyst/plugins/statusline" in cmd
    )


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    yes = "--yes" in args or "-y" in args
    force = "--force" in args

    settings = load_settings()
    desired = desired_statusline_block()
    changes: list[tuple[str, str, object]] = []

    enabled = settings.get("enabledPlugins", {}) or {}
    if enabled.get(PLUGIN_KEY) is not True:
        changes.append(("add", f"enabledPlugins.{PLUGIN_KEY}", True))

    existing = settings.get("statusLine")
    refuse_reason: str | None = None
    if existing is None:
        changes.append(("add", "statusLine", desired))
    elif blocks_equal(existing, desired):
        pass
    elif existing_block_points_at_plugin(existing):
        changes.append(("replace", "statusLine", desired))
    elif force:
        changes.append(("replace", "statusLine", desired))
    else:
        existing_cmd = existing.get("command", "<no command>") if isinstance(existing, dict) else str(existing)
        refuse_reason = (
            f"Existing statusLine points at: {existing_cmd}\n"
            f"This does not look like our plugin. Refusing to overwrite it without --force."
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
        symbol = "+" if kind == "add" else "~"
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
    settings["statusLine"] = desired

    SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Updated: {SETTINGS}")
    print("Restart Claude Code (or open a new session) to see the new statusline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
