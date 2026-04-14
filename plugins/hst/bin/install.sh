#!/usr/bin/env bash
# One-time setup: copies bin/ scripts into ~/.local/bin.
# Re-runs when the plugin version changes.

set -euo pipefail

plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
data_dir="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/hst}"
manifest="$plugin_root/.claude-plugin/plugin.json"

version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$manifest" | head -n1)
[[ -z "$version" ]] && version="unknown"

stamp="$data_dir/installed-v${version}"
if [[ -f "$stamp" ]]; then
  exit 0
fi

mkdir -p "$HOME/.local/bin" "$data_dir"

installed=()
for script in "$plugin_root"/bin/*; do
  name=$(basename "$script")
  # skip the installer itself
  [[ "$name" == "install.sh" ]] && continue
  [[ -f "$script" ]] || continue
  cp "$script" "$HOME/.local/bin/$name"
  chmod +x "$HOME/.local/bin/$name"
  installed+=("$name")
done

touch "$stamp"

if (( ${#installed[@]} > 0 )); then
  echo ""
  echo "[hst] Installed shell commands to ~/.local/bin: ${installed[*]}"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *)
      echo "[hst] ~/.local/bin is not on your PATH. Add this line to ~/.zshrc:"
      echo ""
      echo '    export PATH="$HOME/.local/bin:$PATH"'
      echo ""
      ;;
  esac
fi
