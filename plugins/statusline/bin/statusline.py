#!/usr/bin/env python3
import json, sys, os, subprocess, time

data = json.load(sys.stdin)

# Model name
model = data.get("model", {}).get("display_name", "")

# Tokens: used/total (e.g. 20K/200K)
ctx = data.get("context_window", {})
ctx_size = ctx.get("context_window_size", 0)
used_pct = ctx.get("used_percentage")
tokens_str = ""
if used_pct is not None and ctx_size:
    used = int(ctx_size * used_pct / 100)
    tokens_str = f"{used // 1000}K/{ctx_size // 1000}K"

# Rate limits from Anthropic OAuth API (cached 60s)
CACHE = "/tmp/claude-statusline-usage.json"
CACHE_TTL = 60

def fetch_usage():
    try:
        creds_raw = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=3
        )
        if creds_raw.returncode != 0:
            return None
        creds = json.loads(creds_raw.stdout.strip())
        token = creds.get("claudeAiOauth", {}).get("accessToken")
        if not token:
            return None
        resp = subprocess.run(
            ["curl", "-s", "--max-time", "3",
             "https://api.anthropic.com/api/oauth/usage",
             "-H", f"Authorization: Bearer {token}",
             "-H", "anthropic-beta: oauth-2025-04-20",
             "-H", "Content-Type: application/json"],
            capture_output=True, text=True, timeout=5
        )
        if resp.returncode != 0:
            return None
        usage = json.loads(resp.stdout)
        if "error" in usage:
            return None
        with open(CACHE, "w") as f:
            json.dump(usage, f)
        return usage
    except Exception:
        return None

def get_usage():
    try:
        if os.path.exists(CACHE):
            age = time.time() - os.path.getmtime(CACHE)
            if age < CACHE_TTL:
                with open(CACHE) as f:
                    return json.load(f)
    except Exception:
        pass
    return fetch_usage()

usage = get_usage()
rate_str = ""
if usage:
    parts_rate = []
    fh = usage.get("five_hour", {})
    sd = usage.get("seven_day", {})
    if fh and fh.get("utilization") is not None:
        parts_rate.append(f"5h:{int(fh['utilization'])}%")
    if sd and sd.get("utilization") is not None:
        parts_rate.append(f"7d:{int(sd['utilization'])}%")
    rate_str = " ".join(parts_rate)

# Cost in $ — real for API key, estimate for Pro/Max
# Detect Pro by OAuth token existence (usage API may be rate-limited)
try:
    creds_raw = subprocess.run(
        ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
        capture_output=True, text=True, timeout=3
    )
    has_oauth = creds_raw.returncode == 0 and "claudeAiOauth" in creds_raw.stdout
except Exception:
    has_oauth = False
is_pro = has_oauth or bool(rate_str)
cost_usd = data.get("cost", {}).get("total_cost_usd")
if cost_usd is not None:
    if is_pro:
        cost_str = f"~${cost_usd:.2f} (Pro)"
    else:
        cost_str = f"${cost_usd:.4f} (API)"
else:
    cost_str = ""

# Folder (shorten home to ~)
cwd = data.get("cwd", "")
home = os.environ.get("HOME", "")
folder = cwd.replace(home, "~", 1) if home and cwd.startswith(home) else cwd

# Full session ID (usable with `claude --resume`)
session_id = data.get("session_id", "")

# Build status line
parts = []
if model:
    parts.append(model)
if tokens_str:
    parts.append(tokens_str)
if rate_str:
    parts.append(rate_str)
if cost_str:
    parts.append(cost_str)
if folder:
    parts.append(folder)
if session_id:
    parts.append(session_id)

print(" | ".join(parts))
