#!/usr/bin/env python3
"""
agents-activation-strip.py — Shed the activation-only block from a workspace's
AGENTS.md once the user activates (warm → active).

This is the FIRST sanctioned precedent of a skill mutating AGENTS.md (see
SKILL-ROUTING.md + docs/CONVENTIONS.md). It exists because the handoff AGENTS.md
variant carries the First-Meal Mode / Gate / reminder-first-trigger block
permanently (~2-3KB always-injected), which is what blew the 12,288 B bootstrap
cap. backend-service wraps that block in the fences below; once the user activates
there is no reason to keep injecting it, so we strip it.

Markers (exact, authored by backend-service in AGENTS-handoff.md):
    <!-- activation-only -->
    ...
    <!-- /activation-only -->

Behavior:
  - If workspace AGENTS.md contains `<!-- activation-only -->`:
      1. back up to AGENTS.md.pre-activation-strip
      2. regex-remove ALL fenced blocks (inclusive of both markers)
      3. write back
      4. ASSERT result <= 12,288 B AND required load-bearing markers present
         (System Confidentiality, a "## Cron" heading, a "## Tools" heading —
         matched variant-tolerantly). On any assertion failure → restore the
         backup, exit non-zero, log.
  - Idempotent: no opening fence → no-op, exit 0.
  - No AGENTS.md at all → no-op, exit 0 (nothing to strip).

Usage:
  python3 agents-activation-strip.py --workspace-dir <ws>

Output (stdout): JSON
  {"status":"stripped","bytes_before":N,"bytes_after":M,"blocks":K}
  {"status":"noop","reason":"..."}        # no fence / no file
  {"status":"error","error":"..."}        # assertion failed (backup restored)
Exit code 0 on success/noop, 1 on hard failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys


AGENTS_CAP_BYTES = 12288
OPEN_MARKER = "<!-- activation-only -->"
CLOSE_MARKER = "<!-- /activation-only -->"
BACKUP_SUFFIX = ".pre-activation-strip"

# Required load-bearing markers that must survive the strip, matched
# variant-tolerantly (the handoff variant names its tail "## Tools & Formatting"
# while older/standard variants use "## Tools"; both use "## Cron & Heartbeats").
# Match the heading prefix by regex so a header rename can't trip a false
# strip-failure. "System Confidentiality" is a plain substring (present in the
# handoff variant that carries the activation fence).
REQUIRED_MARKERS = (
    ("System Confidentiality", re.compile(r"System Confidentiality")),
    ("Cron", re.compile(r"^##\s*Cron\b", re.MULTILINE)),
    ("Tools", re.compile(r"^##\s*Tools\b", re.MULTILINE)),
)

# Non-greedy block remover, DOTALL so it spans newlines. Also swallows a trailing
# newline after the close marker to avoid leaving a blank-line scar.
_FENCE_RE = re.compile(
    re.escape(OPEN_MARKER) + r".*?" + re.escape(CLOSE_MARKER) + r"\n?",
    re.DOTALL,
)


def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    return re.sub(
        r'(workspace-(?:wechat|wecom)-dm-)([^/]+)',
        lambda m: m.group(1) + m.group(2).lower(), p,
    )


def log(msg):
    print(f"[agents-activation-strip] {msg}", file=sys.stderr)


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="Strip <!-- activation-only --> blocks from workspace AGENTS.md"
    )
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    args = parser.parse_args()
    workspace_dir = _normalize_path(args.workspace_dir)

    agents_path = os.path.join(workspace_dir, "AGENTS.md")

    if not os.path.exists(agents_path):
        _emit({"status": "noop", "reason": "AGENTS.md not found"})
        return 0

    try:
        with open(agents_path, encoding="utf-8") as f:
            original = f.read()
    except IOError as e:
        log(f"could not read AGENTS.md: {e}")
        _emit({"status": "error", "error": f"read failed: {e}"})
        return 1

    # Idempotent: no opening fence → nothing to do.
    if OPEN_MARKER not in original:
        _emit({"status": "noop", "reason": "no activation-only fence"})
        return 0

    bytes_before = len(original.encode("utf-8"))

    stripped, n_blocks = _FENCE_RE.subn("", original)

    # Defensive: an unbalanced/leftover opening marker means the regex didn't
    # consume a block (e.g. missing close marker). Do NOT write a half-stripped
    # file — bail without touching anything.
    if OPEN_MARKER in stripped or CLOSE_MARKER in stripped:
        log("unbalanced activation-only markers after strip — aborting (no write)")
        _emit({"status": "error",
               "error": "unbalanced activation-only markers (missing close?)"})
        return 1

    bytes_after = len(stripped.encode("utf-8"))

    # Back up the pristine original BEFORE writing.
    backup_path = agents_path + BACKUP_SUFFIX
    try:
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(original)
    except IOError as e:
        log(f"could not write backup: {e}")
        _emit({"status": "error", "error": f"backup write failed: {e}"})
        return 1

    # Write the stripped content.
    try:
        with open(agents_path, "w", encoding="utf-8") as f:
            f.write(stripped)
    except IOError as e:
        # Try to restore from the backup we just made.
        _restore(backup_path, agents_path)
        log(f"write failed, restored backup: {e}")
        _emit({"status": "error", "error": f"write failed: {e}"})
        return 1

    # --- Assertions: cap + required markers. Any failure → restore + exit 1. ---
    failures = []
    if bytes_after > AGENTS_CAP_BYTES:
        failures.append(f"result {bytes_after}B > cap {AGENTS_CAP_BYTES}B")
    for label, rx in REQUIRED_MARKERS:
        if not rx.search(stripped):
            failures.append(f"missing required marker '{label}'")

    if failures:
        _restore(backup_path, agents_path)
        reason = "; ".join(failures)
        log(f"assertion failed ({reason}) — restored original AGENTS.md")
        _emit({"status": "error", "error": reason, "restored": True})
        return 1

    log(f"stripped {n_blocks} activation-only block(s): "
        f"{bytes_before}B → {bytes_after}B (backup at {backup_path})")
    _emit({
        "status": "stripped",
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
        "blocks": n_blocks,
    })
    return 0


def _restore(backup_path, agents_path):
    """Best-effort restore of the backup over AGENTS.md."""
    try:
        with open(backup_path, encoding="utf-8") as f:
            content = f.read()
        with open(agents_path, "w", encoding="utf-8") as f:
            f.write(content)
    except IOError as e:
        log(f"CRITICAL: restore failed: {e} — backup remains at {backup_path}")


if __name__ == "__main__":
    sys.exit(main())
