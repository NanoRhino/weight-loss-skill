---
name: branch-deploy-test
description: "Deploy a git branch to the weight-loss-skill repo, apply local fixes, prepare test environment, and generate a test plan. Trigger when user says '获取最新...分支' or '部署...分支' or 'deploy branch' or '重启gateway' combined with a branch name. Also trigger on '清测试用户' or '准备测试'."
metadata:
  openclaw:
    emoji: "rocket"
---

# Branch Deploy & Test

Deploy a skill branch, apply local fixes, prepare test environment, generate test plan.

## Step 1: Deploy Branch

```bash
cd /home/admin/.openclaw/skills \
  && git fetch origin \
  && git checkout <branch> \
  && git pull origin <branch>
```

Extract `<branch>` from user message. If branch doesn't exist, report error and stop.

## Step 2: Diff Analysis

Run:
```bash
cd /home/admin/.openclaw/skills && git diff origin/main..HEAD --stat
```

Then for each changed SKILL.md:
```bash
cd /home/admin/.openclaw/skills && git diff origin/main..HEAD -- <path>
```

Identify:
- **Functional changes**: New features, behavior changes, threshold changes
- **Cosmetic changes**: Wording compression, formatting, renames (no logic change)

## Step 3: Local Fixes

Check if the branch moved Response Schemas / Ambiguous Food sections out of `diet-tracking-analysis/SKILL.md` into a separate file. If so:

1. Get original content from `origin/main`:
   ```bash
   git show origin/main:diet-tracking-analysis/SKILL.md | sed -n '/^## Response Schemas/,$ p'
   ```
2. Replace the compressed version in current SKILL.md with the original
3. Verify with diff that Response Schemas section is identical to main
4. Commit + push:
   ```bash
   git add -A && git commit -m "restore: use original response-schemas wording from main" && git push origin <branch>
   ```

Also check for any other content that was moved out of SKILL.md into references/ that should stay inline. The rule: **Response Schemas, Ambiguous Food Clarification, and Overshoot tone rules must stay in SKILL.md, not in reference files.**

## Step 4: Restart Gateway

```bash
openclaw gateway restart
```

This will kill the current session. After restart, verify:
```bash
curl -s http://localhost:17295/health
```

## Step 5: Prepare Test Environment

Clear test user's session history + meal data in one step:

```bash
# Clear sessions
for f in /home/admin/.openclaw/agents/wechat-dm-acco9kmaupzisoat8hpofek/sessions/*.jsonl; do
  echo "" > "$f"
done

# Clear meal data
rm -f /home/admin/.openclaw/workspace-wechat-dm-acco9kmaupzisoat8hpofek/data/meals/*.json
```

Confirm both are empty before proceeding.

## Step 6: Generate Test Plan

Based on the functional changes identified in Step 2, generate a test plan:

### For each functional change, create a test case:
- **Test name**: What are we testing
- **What changed**: One-line summary of the change
- **Steps**: Numbered steps the user (Boss) should do in WeChat test account
- **Expected result**: What should happen if the change works
- **How to verify**: What to check in agent session logs (thinking/tool_use/reply)

### Always include regression test:
- Send a normal food photo → verify Scene inventory, container templates, food templates, oil templates, progress bar format all still work

### Test order:
1. Regression (basic functionality) first
2. New features second
3. Calibration/memory features last (they need setup steps)

Report the test plan to Boss and wait for them to start testing.

## References

| Item | Path |
|------|------|
| Skills repo | `/home/admin/.openclaw/skills` |
| Test user agent | `wechat-dm-acco9kmaupzisoat8hpofek` |
| Test user sessions | `/home/admin/.openclaw/agents/wechat-dm-acco9kmaupzisoat8hpofek/sessions/` |
| Test user meals | `/home/admin/.openclaw/workspace-wechat-dm-acco9kmaupzisoat8hpofek/data/meals/` |
| Test user workspace | `/home/admin/.openclaw/workspace-wechat-dm-acco9kmaupzisoat8hpofek/` |
| Gateway health | `http://localhost:17295/health` |
