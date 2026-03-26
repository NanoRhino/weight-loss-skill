# 工作日用餐场所收集 — 改动详情

## 概述

在 diet-tracking-analysis 技能中新增「工作日用餐场所收集」功能，通过打卡后自然追问的方式，收集用户三餐（早/午/晚）的固定用餐场所（在家、食堂、外面吃等），存储为 profile 供后续推荐和建议使用。

---

## 改动文件清单

| 文件 | 类型 | 行数 | 说明 |
|------|------|------|------|
| `meal-place-rules.md` | 新增 | 203 行 | 收集规则文档：when/how/where + 数据 schema + 漂移检测 |
| `scripts/meal-place.py` | 新增 | 313 行 | 状态管理脚本，6 个命令 |
| `scripts/test-meal-place.py` | 新增 | 562 行 | 测试套件，28 个测试，81 个断言 |
| `SKILL.md` | 修改 | +30 行 | 工作流第 11 步 + 脚本文档（§9） + Reference Files 条目 |
| `response-schemas.md` | 修改 | +46 行 | 回复模板：confirm / pick_two / drift confirmation |

---

## 数据存储

**文件路径：** `{workspaceDir}/data/meal-place-profile.json`
**归属技能：** diet-tracking-analysis

```json
{
  "workday_meal_place_profile": {
    "breakfast": { "place": "home", "updated_at": "2026-03-23T07:30:00+08:00" },
    "lunch":     { "place": "cafeteria", "updated_at": "2026-03-23T12:10:00+08:00" },
    "dinner":    { "place": "home", "updated_at": "2026-03-23T18:20:00+08:00" }
  },
  "_collection_state": {
    "breakfast": { "ask_count": 0, "collected": false },
    "lunch":     { "ask_count": 0, "collected": false },
    "dinner":    { "ask_count": 0, "collected": false }
  },
  "_drift_detection": {
    "breakfast": { "consecutive_mismatches": 0, "last_inferred": null },
    "lunch":     { "consecutive_mismatches": 0, "last_inferred": null },
    "dinner":    { "consecutive_mismatches": 0, "last_inferred": null }
  }
}
```

**候选场所值：** `home` | `cafeteria` | `takeout` | `restaurant` | `bring_meal` | `other`

---

## 收集策略

### 触发条件
- **仅工作日**（周一至周五），周末完全跳过
- 该餐次 `place` 为 null → 打卡后追问
- 已有值 → 不问，走漂移检测

### 放弃机制
- 同一餐次累计问 3 次未回答 → 永久放弃，不再问

### 漂移检测
- 每次打卡推断场所，与 profile 对比
- 一致 → 计数归零
- 不一致 → 累加，连续 ≥3 次 → 询问是否换了
- 用户确认/否认/不回 → 计数归零

---

## 两种问法模式

### Mode A: confirm（高置信度推断）

直接确认推断结果：
```
对了顺便问下，午餐一般都是在外面吃呀？
```

**触发条件：** 图片/文字中有明确场所信号（餐厅桌椅+菜单 → restaurant，外卖盒+办公桌 → takeout）

### Mode B: pick_two（低置信度或无推断）

二选一，推断结果排第一位：
```
对了顺便问下，晚餐一般是吃食堂呢，还是在家吃呢？
```

**选项逻辑：**
1. 有低置信度推断 → 推断排第一，配一个默认选项
2. 推断已在默认列表中 → 重排，推断优先
3. 无推断 → 使用默认

### 三餐默认选项（无推断时 fallback）

| 餐次 | Option 1 | Option 2 |
|------|----------|----------|
| 早餐 | 在家吃 | 吃食堂 |
| 午餐 | 吃食堂 | 在外面吃 |
| 晚餐 | 在家吃 | 在外面吃 |

---

## 脚本命令（meal-place.py）

| 命令 | 用途 | 关键参数 |
|------|------|----------|
| `check` | 判断是否该问 / 是否触发漂移确认 | `--meal`, `--weekday`, `--inferred`, `--confidence` |
| `save-place` | 存储场所 | `--meal`, `--place` |
| `no-reply` | 记录用户未回复 | `--meal` |
| `record-drift` | 记录推断场所，更新漂移计数 | `--meal`, `--inferred` |
| `reset-drift` | 重置漂移计数 | `--meal` |
| `load` | 读取完整 profile | — |

所有命令需要 `--data-dir`。

---

## 工作流集成

在 SKILL.md Logging Food 流程中新增第 11 步：

> **11. Meal place collection (workdays only)** — after the reply, run the venue collection or drift detection logic per `meal-place-rules.md`. If today is a weekend, skip entirely. If the current meal's place is not yet recorded and ask attempts remain, append a one-line venue question to the reply. If place is already recorded, silently run drift detection based on photo/text context clues.

---

## 测试覆盖

28 个测试，81 个断言，全部通过。

| 测试类别 | 测试数 | 覆盖场景 |
|----------|--------|----------|
| load | 2 | 空目录默认值、已有数据读回 |
| check 基础 | 7 | 周末跳过、工作日询问、各餐默认选项、已收集跳过 |
| check 推断模式 | 4 | 高置信confirm、低置信pick_two、推断排序、无效推断回退 |
| no-reply | 2 | 计数递增、3次放弃 |
| save-place | 3 | 存储、非法值拒绝、覆盖更新 |
| drift | 5 | 匹配归零、不匹配累加、混合归零、无基线跳过、触发确认 |
| reset-drift | 1 | 重置后不再触发确认 |
| E2E 流程 | 4 | 完整收集流、放弃流、漂移确认流、漂移拒绝流 |
| 独立性 | 1 | 三餐状态互不影响 |

---

## Commit 历史

| Commit | 说明 |
|--------|------|
| `842b59a` | 新增 meal-place-rules.md + SKILL.md 引用 |
| `b1c2547` | 新增 meal-place.py 脚本 + 测试 |
| `f882af0` | 两种问法模式（confirm vs pick_two） |
| `17dcc2a` | 追加"对了顺便问下"引导语 |
| `9af3481` | pick_two 模式使用推断结果排第一 |
| `200486b` | 早餐默认从外卖改为食堂 |
| `4e210a1` | 午餐/晚餐默认从外卖改为外面吃 |
