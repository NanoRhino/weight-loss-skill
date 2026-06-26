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

Two tiers (analysis vs reminder):
  - Analysis (default, used by weekly insight / diet pattern / etc):
    `agents.defaults.model.primary` — the gateway's resolved default,
    typically Opus for quality.
  - Reminder (用于 breakfast/lunch/dinner reminder, product tips, etc):
    `agents.defaults.modelTiers.reminder` — operator-configurable cheaper
    model (typically Sonnet on Bedrock) to save ~$3800/mo on hot-path cron.
    Falls back to a hardcoded Bedrock Sonnet ARN if the config field is
    absent (matches what 181/200 prod cron jobs already use).

CLI:
  $ resolve-model.py                # analysis tier (primary)
  $ resolve-model.py --tier reminder  # reminder tier

Prints the resolved "<provider>/<model-id>" to stdout on success. On failure
prints nothing to stdout and exits nonzero — callers then omit --model and let
the gateway apply its own default (which is the safe behavior, not the bug).

Config path: $OPENCLAW_STATE_DIR/openclaw.json, defaulting to the repo's
.openclaw-gateway/openclaw.json (same resolution the sibling scripts use).
"""
import argparse
import json
import os
import sys

# Reminder-tier fallback when openclaw.json has no agents.defaults.modelTiers.reminder.
# Matches the Bedrock Sonnet ARN already used by 181/200 prod cron jobs (2026-06-26).
_REMINDER_FALLBACK = (
    "amazon-bedrock/arn:aws:bedrock:us-east-1:405912452115:"
    "inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"
)


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


def resolve_reminder_model(cfg: dict) -> str:
    """Reminder-tier model: openclaw.json override → hardcoded Bedrock Sonnet fallback.

    Reads agents.defaults.modelTiers.reminder. The fallback is a last-resort
    only — it matches what prod is already running today, so it is safe even
    if the config field is missing. Operators wanting a different reminder
    model just add the field to openclaw.json (no code change needed).
    """
    override = (
        cfg.get("agents", {})
        .get("defaults", {})
        .get("modelTiers", {})
        .get("reminder")
    )
    if isinstance(override, str) and "/" in override:
        return override
    return _REMINDER_FALLBACK


def _load_config():
    try:
        with open(_config_path()) as f:
            return json.load(f)
    except Exception:
        return None


def resolve():
    """Read the gateway config and return the analysis-tier model, or None on failure."""
    cfg = _load_config()
    if cfg is None:
        return None
    return resolve_model(cfg)


def resolve_reminder():
    """Reminder-tier model. Never returns None — falls back to a known-good Bedrock ARN."""
    cfg = _load_config() or {}
    return resolve_reminder_model(cfg)


def main() -> int:
    p = argparse.ArgumentParser(description="Resolve cron job model from gateway config.")
    p.add_argument("--tier", choices=["analysis", "reminder"], default="analysis",
                   help="analysis (default, Opus-class) or reminder (Sonnet-class)")
    args = p.parse_args()

    if args.tier == "reminder":
        print(resolve_reminder())
        return 0

    cfg = _load_config()
    if cfg is None:
        print("resolve-model: cannot read config", file=sys.stderr)
        return 1
    model = resolve_model(cfg)
    if not model:
        print("resolve-model: no model resolvable from config", file=sys.stderr)
        return 1
    print(model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
