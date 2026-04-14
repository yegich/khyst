#!/usr/bin/env bash
# One-time setup: copies bin/ scripts into ~/.local/bin.
# Re-runs when the plugin version changes.

set -euo pipefail

plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
data_dir="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/hst}"

# Hash the contents of bin/ (excluding this installer) so any script change
# retriggers install without needing a version bump.
hash_input=$(find "$plugin_root/bin" -type f ! -name 'install.sh' -print0 \
  | sort -z \
  | xargs -0 shasum 2>/dev/null || true)
current_hash=$(printf '%s' "$hash_input" | shasum | awk '{print $1}')

stamp="$data_dir/installed.hash"
if [[ -f "$stamp" && "$(cat "$stamp" 2>/dev/null)" == "$current_hash" ]]; then
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

printf '%s' "$current_hash" > "$stamp"

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
