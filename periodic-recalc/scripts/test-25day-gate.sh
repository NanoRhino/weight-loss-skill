#!/bin/bash
# Test script for 25-day gate logic using last-recalc-summary.json

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_ROOT="/tmp/periodic-recalc-test-$$"
PERIODIC_RECALC="$SCRIPT_DIR/periodic-recalc.py"

# Mock planner-calc.py (returns fixed output)
MOCK_PLANNER="$TEST_ROOT/mock-planner-calc.py"

echo "=== Creating test environment ==="
mkdir -p "$TEST_ROOT"

cat > "$MOCK_PLANNER" << 'EOF'
#!/usr/bin/env python3
import json
import sys
# Mock planner-calc.py — return fixed values
output = {
    "daily_cal": 1400,
    "tdee": {
        "tdee": 1800,
        "bmr": 1400,
        "activity_multiplier": 1.3
    },
    "rate_kg_per_week": 0.5,
    "macros": {
        "protein": {"min": 70, "max": 93},
        "fat": {"min": 31, "max": 54},
        "carb": {"min": 120, "max": 175}
    },
    "floor_clamped": False
}
print(json.dumps(output, ensure_ascii=False, indent=2))
EOF
chmod +x "$MOCK_PLANNER"

# Helper: create workspace with USER.md (required)
create_workspace() {
    local ws="$1"
    mkdir -p "$ws/data"
    cat > "$ws/USER.md" << 'EOF'
# USER

**Name:** Test User
**Sex:** female
**Age:** 30
**Height:** 165 cm
**Language:** zh-CN
EOF
}

# Helper: create weight.json
create_weight() {
    local ws="$1"
    local days_ago="${2:-0}"
    local date_iso=$(date -d "$days_ago days ago" '+%Y-%m-%dT08:00:00+08:00')
    cat > "$ws/data/weight.json" << EOF
{
  "$date_iso": {"value": 58.5, "unit": "kg"}
}
EOF
}

# Helper: create PLAN.md (free-form Chinese, no Updated field)
create_plan_free_form() {
    local ws="$1"
    cat > "$ws/PLAN.md" << 'EOF'
# 减重计划

目标体重：55 kg
每日热量：1500 大卡
活动水平：轻度活动
饮食模式：均衡饮食
EOF
}

# Helper: create last-recalc-summary.json
create_last_recalc() {
    local ws="$1"
    local days_ago="$2"
    local date_iso=$(date -d "$days_ago days ago" '+%Y-%m-%d')
    cat > "$ws/data/last-recalc-summary.json" << EOF
{
  "date": "$date_iso",
  "weight_from": 60.0,
  "weight_to": 58.5,
  "old_calories": 1500,
  "new_calories": 1400
}
EOF
}

run_test() {
    local scenario="$1"
    local ws="$TEST_ROOT/ws-$scenario"
    shift

    echo ""
    echo "=== Scenario $scenario ==="

    # Run periodic-recalc and capture output
    if python3 "$PERIODIC_RECALC" --workspace "$ws" --planner-calc "$MOCK_PLANNER" "$@" > "$ws/output.json" 2>&1; then
        local exit_code=0
    else
        local exit_code=$?
    fi

    echo "Exit code: $exit_code"
    cat "$ws/output.json"

    # Return results for caller to check
    echo "$exit_code|$(cat "$ws/output.json")"
}

echo ""
echo "=== Scenario A: No PLAN.md, no last-recalc-summary.json ==="
WS_A="$TEST_ROOT/ws-A"
create_workspace "$WS_A"
# No weight.json — should fail with error
python3 "$PERIODIC_RECALC" --workspace "$WS_A" --planner-calc "$MOCK_PLANNER" 2>&1 || echo "Expected failure: exit $?"

echo ""
echo "=== Scenario B: Free-form PLAN, no last-recalc-summary, fresh weight, CLI args ==="
WS_B="$TEST_ROOT/ws-B"
create_workspace "$WS_B"
create_plan_free_form "$WS_B"
create_weight "$WS_B" 0
python3 "$PERIODIC_RECALC" --workspace "$WS_B" --planner-calc "$MOCK_PLANNER" \
  --current-calories 1500 --target-weight 55 --tdee 1800 \
  --activity lightly_active --diet-mode balanced 2>&1
echo "Expected: action=recalculated (not blocked by 25-day gate)"

echo ""
echo "=== Scenario C: last-recalc-summary date = today - 10 days ==="
WS_C="$TEST_ROOT/ws-C"
create_workspace "$WS_C"
create_plan_free_form "$WS_C"
create_weight "$WS_C" 0
create_last_recalc "$WS_C" 10
python3 "$PERIODIC_RECALC" --workspace "$WS_C" --planner-calc "$MOCK_PLANNER" \
  --current-calories 1500 --target-weight 55 --tdee 1800 \
  --activity lightly_active --diet-mode balanced 2>&1
echo "Expected: action=skipped, days_since_last=10"

echo ""
echo "=== Scenario D: last-recalc-summary date = today - 30 days, CLI args ==="
WS_D="$TEST_ROOT/ws-D"
create_workspace "$WS_D"
create_plan_free_form "$WS_D"
create_weight "$WS_D" 0
create_last_recalc "$WS_D" 30
python3 "$PERIODIC_RECALC" --workspace "$WS_D" --planner-calc "$MOCK_PLANNER" \
  --current-calories 1500 --target-weight 55 --tdee 1800 \
  --activity lightly_active --diet-mode balanced 2>&1
echo "Expected: action=recalculated"

echo ""
echo "=== Scenario E: last-recalc-summary date field corrupt ==="
WS_E="$TEST_ROOT/ws-E"
create_workspace "$WS_E"
create_plan_free_form "$WS_E"
create_weight "$WS_E" 0
cat > "$WS_E/data/last-recalc-summary.json" << 'EOF'
{
  "date": "",
  "weight_from": 60.0
}
EOF
python3 "$PERIODIC_RECALC" --workspace "$WS_E" --planner-calc "$MOCK_PLANNER" \
  --current-calories 1500 --target-weight 55 --tdee 1800 \
  --activity lightly_active --diet-mode balanced 2>&1
echo "Expected: action=recalculated (treat as never recalc)"

echo ""
echo "=== Scenario F: Dry-run, should NOT write last-recalc-summary.json ==="
WS_F="$TEST_ROOT/ws-F"
create_workspace "$WS_F"
create_plan_free_form "$WS_F"
create_weight "$WS_F" 0
create_last_recalc "$WS_F" 30
python3 "$PERIODIC_RECALC" --workspace "$WS_F" --planner-calc "$MOCK_PLANNER" \
  --current-calories 1500 --target-weight 55 --tdee 1800 \
  --activity lightly_active --diet-mode balanced --dry-run 2>&1
if [ -f "$WS_F/data/last-recalc-summary.json" ]; then
    RECALC_DATE=$(python3 -c "import json; print(json.load(open('$WS_F/data/last-recalc-summary.json')).get('date'))")
    if [ "$RECALC_DATE" == "$(date '+%Y-%m-%d')" ]; then
        echo "FAIL: last-recalc-summary.json was updated in dry-run!"
        exit 1
    else
        echo "PASS: last-recalc-summary.json not updated (still 30 days ago)"
    fi
else
    echo "FAIL: last-recalc-summary.json disappeared!"
    exit 1
fi

echo ""
echo "=== Scenario G: Real run, check last-recalc-summary.json written with date ==="
WS_G="$TEST_ROOT/ws-G"
create_workspace "$WS_G"
create_plan_free_form "$WS_G"
create_weight "$WS_G" 0
create_last_recalc "$WS_G" 30
python3 "$PERIODIC_RECALC" --workspace "$WS_G" --planner-calc "$MOCK_PLANNER" \
  --current-calories 1500 --target-weight 55 --tdee 1800 \
  --activity lightly_active --diet-mode balanced 2>&1
if [ -f "$WS_G/data/last-recalc-summary.json" ]; then
    RECALC_DATE=$(python3 -c "import json; print(json.load(open('$WS_G/data/last-recalc-summary.json')).get('date'))")
    if [ "$RECALC_DATE" == "$(date '+%Y-%m-%d')" ]; then
        echo "PASS: last-recalc-summary.json date field = today"
        echo "Content:"
        cat "$WS_G/data/last-recalc-summary.json"
    else
        echo "FAIL: last-recalc-summary.json date field not updated! Got: $RECALC_DATE"
        exit 1
    fi
else
    echo "FAIL: last-recalc-summary.json not created!"
    exit 1
fi

echo ""
echo "=== All scenarios completed ==="
echo "Test artifacts in: $TEST_ROOT"
echo "To clean up: rm -rf $TEST_ROOT"
