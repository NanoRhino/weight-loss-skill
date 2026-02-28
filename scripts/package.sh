#!/usr/bin/env bash
#
# package.sh — Auto-package weight-loss-skill for Claude Code & OpenClaw/ClawHub
#
# Usage:
#   ./scripts/package.sh                  # Package all formats
#   ./scripts/package.sh --claude         # Claude Code plugin only
#   ./scripts/package.sh --openclaw       # OpenClaw/ClawHub skills only
#   ./scripts/package.sh --publish        # Package + publish to ClawHub
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
VERSION=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Read version from plugin.json ─────────────────────────────────────────────
get_version() {
  if command -v jq &>/dev/null; then
    VERSION=$(jq -r '.version' "$ROOT_DIR/.claude-plugin/plugin.json")
  elif command -v python3 &>/dev/null; then
    VERSION=$(python3 -c "import json; print(json.load(open('$ROOT_DIR/.claude-plugin/plugin.json'))['version'])")
  elif command -v node &>/dev/null; then
    VERSION=$(node -e "console.log(require('$ROOT_DIR/.claude-plugin/plugin.json').version)")
  else
    err "Need jq, python3, or node to read version from plugin.json"
    exit 1
  fi
  info "Version: $VERSION"
}

# ── Skill directories ─────────────────────────────────────────────────────────
SKILLS=(
  "daily-notification-skill"
  "diet-tracking-analysis"
  "exercise-logging"
  "exercise-programming"
  "habit-builder"
  "meal-planner"
  "user-onboarding-profile"
  "weight-loss-planner"
)

# ── Validate all SKILL.md files ───────────────────────────────────────────────
validate_skills() {
  info "Validating SKILL.md files..."
  local errors=0

  for skill in "${SKILLS[@]}"; do
    local skill_file="$ROOT_DIR/$skill/SKILL.md"
    if [[ ! -f "$skill_file" ]]; then
      err "Missing: $skill/SKILL.md"
      errors=$((errors + 1))
      continue
    fi

    # Check frontmatter exists
    if ! head -1 "$skill_file" | grep -q "^---"; then
      err "$skill/SKILL.md: missing YAML frontmatter"
      errors=$((errors + 1))
      continue
    fi

    # Check required fields
    if ! grep -q "^name:" "$skill_file"; then
      err "$skill/SKILL.md: missing 'name' field"
      errors=$((errors + 1))
    fi
    if ! grep -q "^description:" "$skill_file"; then
      err "$skill/SKILL.md: missing 'description' field"
      errors=$((errors + 1))
    fi
    if ! grep -q "^version:" "$skill_file"; then
      warn "$skill/SKILL.md: missing 'version' field (will use plugin version)"
    fi
  done

  if [[ $errors -gt 0 ]]; then
    err "Validation failed with $errors error(s)"
    exit 1
  fi
  ok "All SKILL.md files valid"
}

# ── Sync version from plugin.json → SKILL.md files ───────────────────────────
sync_versions() {
  info "Syncing version $VERSION to all SKILL.md files..."
  for skill in "${SKILLS[@]}"; do
    local skill_file="$ROOT_DIR/$skill/SKILL.md"
    if grep -q "^version:" "$skill_file"; then
      if command -v sed &>/dev/null; then
        sed -i "s/^version:.*$/version: $VERSION/" "$skill_file"
      fi
    fi
  done
  ok "Versions synced"
}

# ── Build Claude Code plugin package ──────────────────────────────────────────
build_claude_plugin() {
  local out="$DIST_DIR/claude-plugin/weight-loss-skill"
  info "Building Claude Code plugin → $out"
  rm -rf "$out"
  mkdir -p "$out/.claude-plugin"

  # Copy plugin manifest
  cp "$ROOT_DIR/.claude-plugin/plugin.json" "$out/.claude-plugin/plugin.json"

  # Copy each skill directory
  for skill in "${SKILLS[@]}"; do
    cp -r "$ROOT_DIR/$skill" "$out/$skill"
  done

  # Copy metadata files
  cp "$ROOT_DIR/README.md" "$out/README.md"
  cp "$ROOT_DIR/LICENSE" "$out/LICENSE"

  # Create ZIP archive
  (cd "$DIST_DIR/claude-plugin" && zip -qr "weight-loss-skill-v${VERSION}-claude.zip" "weight-loss-skill/")
  ok "Claude Code plugin: dist/claude-plugin/weight-loss-skill-v${VERSION}-claude.zip"
}

# ── Build individual ClawHub-ready skill packages ─────────────────────────────
build_clawhub_skills() {
  local out="$DIST_DIR/clawhub"
  info "Building ClawHub skill packages → $out"
  rm -rf "$out"
  mkdir -p "$out"

  for skill in "${SKILLS[@]}"; do
    local skill_out="$out/$skill"
    mkdir -p "$skill_out"

    # Copy skill directory contents
    cp -r "$ROOT_DIR/$skill/"* "$skill_out/"

    # Create individual ZIP
    (cd "$out" && zip -qr "${skill}-v${VERSION}.zip" "$skill/")
    ok "ClawHub package: dist/clawhub/${skill}-v${VERSION}.zip"
  done

  # Also build an all-in-one bundle
  local bundle_dir="$out/weight-loss-skill-bundle"
  mkdir -p "$bundle_dir"
  for skill in "${SKILLS[@]}"; do
    cp -r "$ROOT_DIR/$skill" "$bundle_dir/$skill"
  done
  cp "$ROOT_DIR/README.md" "$bundle_dir/README.md"
  cp "$ROOT_DIR/LICENSE" "$bundle_dir/LICENSE"
  (cd "$out" && zip -qr "weight-loss-skill-bundle-v${VERSION}.zip" "weight-loss-skill-bundle/")
  ok "ClawHub bundle: dist/clawhub/weight-loss-skill-bundle-v${VERSION}.zip"
}

# ── Publish to ClawHub ────────────────────────────────────────────────────────
publish_clawhub() {
  if ! command -v clawhub &>/dev/null; then
    warn "clawhub CLI not found. Install with: npm i -g clawhub"
    warn "Then run: clawhub publish <skill-path>"
    info "Skill directories ready at: $DIST_DIR/clawhub/"
    echo ""
    info "Manual publish commands:"
    for skill in "${SKILLS[@]}"; do
      echo "  clawhub publish $DIST_DIR/clawhub/$skill"
    done
    return
  fi

  info "Publishing skills to ClawHub..."
  local published=0
  local failed=0

  for skill in "${SKILLS[@]}"; do
    local skill_path="$DIST_DIR/clawhub/$skill"
    info "Publishing $skill..."
    if clawhub publish "$skill_path"; then
      ok "Published: $skill"
      published=$((published + 1))
    else
      err "Failed to publish: $skill"
      failed=$((failed + 1))
    fi
  done

  echo ""
  ok "Published: $published, Failed: $failed"
}

# ── Print install instructions ────────────────────────────────────────────────
print_install_info() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo -e "${GREEN}Packaging complete!${NC}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Install methods:"
  echo ""
  echo -e "${CYAN}Claude Code (plugin):${NC}"
  echo "  claude plugin install ./dist/claude-plugin/weight-loss-skill"
  echo "  # or from GitHub:"
  echo "  claude plugin install NanoRhino/weight-loss-skill"
  echo ""
  echo -e "${CYAN}OpenClaw (clawhub):${NC}"
  echo "  clawhub install NanoRhino/daily-notification"
  echo "  clawhub install NanoRhino/diet-tracking-analysis"
  echo "  clawhub install NanoRhino/exercise-logging"
  echo "  clawhub install NanoRhino/exercise-programming"
  echo "  clawhub install NanoRhino/habit-builder"
  echo "  clawhub install NanoRhino/meal-planner"
  echo "  clawhub install NanoRhino/user-onboarding-profile"
  echo "  clawhub install NanoRhino/weight-loss-planner"
  echo ""
  echo -e "${CYAN}OpenClaw (manual):${NC}"
  echo "  # Copy skill folders to ~/.openclaw/skills/"
  echo "  cp -r daily-notification-skill  ~/.openclaw/skills/"
  echo "  cp -r diet-tracking-analysis    ~/.openclaw/skills/"
  echo "  cp -r exercise-logging          ~/.openclaw/skills/"
  echo "  cp -r exercise-programming      ~/.openclaw/skills/"
  echo "  cp -r habit-builder             ~/.openclaw/skills/"
  echo "  cp -r meal-planner              ~/.openclaw/skills/"
  echo "  cp -r user-onboarding-profile   ~/.openclaw/skills/"
  echo "  cp -r weight-loss-planner       ~/.openclaw/skills/"
  echo ""
  echo -e "${CYAN}Claude Code (manual):${NC}"
  echo "  # Copy skill folders to ~/.claude/skills/"
  echo "  cp -r daily-notification-skill  ~/.claude/skills/"
  echo "  cp -r diet-tracking-analysis    ~/.claude/skills/"
  echo "  cp -r exercise-logging          ~/.claude/skills/"
  echo "  cp -r exercise-programming      ~/.claude/skills/"
  echo "  cp -r habit-builder             ~/.claude/skills/"
  echo "  cp -r meal-planner              ~/.claude/skills/"
  echo "  cp -r user-onboarding-profile   ~/.claude/skills/"
  echo "  cp -r weight-loss-planner       ~/.claude/skills/"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  local mode="${1:-all}"

  echo ""
  echo "╔═══════════════════════════════════════════════════════════════╗"
  echo "║  Weight Loss Skill — Packager                               ║"
  echo "╚═══════════════════════════════════════════════════════════════╝"
  echo ""

  get_version
  validate_skills

  case "$mode" in
    --claude)
      sync_versions
      build_claude_plugin
      ;;
    --openclaw)
      sync_versions
      build_clawhub_skills
      ;;
    --publish)
      sync_versions
      build_clawhub_skills
      publish_clawhub
      ;;
    all|*)
      sync_versions
      build_claude_plugin
      build_clawhub_skills
      ;;
  esac

  print_install_info
}

main "$@"
