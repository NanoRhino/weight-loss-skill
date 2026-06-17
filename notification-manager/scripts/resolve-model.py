#!/usr/bin/env python3
"""
resolve-model.py — Resolve the cron job model from gateway config (never hardcode).

Cron jobs created by the reminder scripts must run on a model whose provider the
gateway actually holds credentials for. Historically a model string was hardcoded
(`anthropic/claude-sonnet-4-6`); the gateway only has `amazon-bedrock` credentials,
so those jobs failed at auth ("No API key found for provider anthropic") from the
moment they were created. Instead of hardcoding, read openclaw.json and emit the
model the gateway is actually configured to use — i.e. let the config decide
"amazon-bedrock (ARN) vs anthropic (direct)".

Resolution order:
  1. agents.defaults.model.primary — the gateway's own resolved default, already
     provider-prefixed (e.g. `amazon-bedrock/<arn>` or `anthropic/<id>`). This is
     the single source of truth for "which provider + model has credentials".
  2. Fallback: first configured provider in models.providers (preferring
     amazon-bedrock, then anthropic, then any) + that provider's first model id.

Prints the resolved "<provider>/<model-id>" to stdout on success. On failure
prints nothing to stdout and exits nonzero — callers then omit --model and let
the gateway apply its own default (which is the safe behavior, not the bug).

Config path: $OPENCLAW_STATE_DIR/openclaw.json, defaulting to the repo's
.openclaw-gateway/openclaw.json (same resolution the sibling scripts use).
"""
import json
import os
import sys


def _config_path() -> str:
    state_dir = os.environ.get("OPENCLAW_STATE_DIR")
    if not state_dir:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.normpath(
            os.path.join(script_dir, "..", "..", "..", "..")
        )
        state_dir = os.path.join(project_root, ".openclaw-gateway")
    return os.path.join(state_dir, "openclaw.json")


def resolve_model(cfg: dict):
    """Pick a credential-backed '<provider>/<model-id>' from a parsed config."""
    # 1. The gateway's resolved default — already encodes provider + model + creds.
    primary = (
        cfg.get("agents", {})
        .get("defaults", {})
        .get("model", {})
        .get("primary")
    )
    if isinstance(primary, str) and "/" in primary:
        return primary

    # 2. Fallback: first configured provider that lists a model.
    providers = cfg.get("models", {}).get("providers", {})
    for name in ("amazon-bedrock", "anthropic"):
        p = providers.get(name)
        if isinstance(p, dict) and p.get("models"):
            return f"{name}/{p['models'][0]['id']}"
    for name, p in providers.items():
        if isinstance(p, dict) and p.get("models"):
            return f"{name}/{p['models'][0]['id']}"
    return None


def resolve():
    """Read the gateway config and return the model string, or None on failure."""
    try:
        with open(_config_path()) as f:
            cfg = json.load(f)
    except Exception:
        return None
    return resolve_model(cfg)


def main() -> int:
    try:
        with open(_config_path()) as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"resolve-model: cannot read config: {e}", file=sys.stderr)
        return 1
    model = resolve_model(cfg)
    if not model:
        print("resolve-model: no model resolvable from config", file=sys.stderr)
        return 1
    print(model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
