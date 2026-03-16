# 拆分方案：daily-notification → notification-manager + notification-composer

## 概述

将当前 `daily-notification-skill` 拆分为两个 skill：

| Skill | 职责 | 关注点 |
|-------|------|--------|
| **notification-manager** | 定时任务的生命周期管理 | "什么时候发、要不要继续发" |
| **notification-composer** | 每次触发时的执行逻辑 | "该不该发、发什么内容" |

底层 `scheduled-reminders` 不变，继续作为 cron 基础设施。

```
scheduled-reminders     纯 cron 工具层（不变）
        ↑
notification-manager    编排层：创建/删除/同步 cron job，管理提醒生命周期
        ↓
notification-composer   执行层：每次触发时的检查 + 话术生成 + 回复处理
```

---

## notification-manager 职责

管理提醒的"存在"，不关心每次发什么。

### 包含内容（从 daily-notification 迁出）

1. **Auto-sync 逻辑**（当前 SKILL.md "Auto-sync on activation" 段落）
   - 读 `health-profile.md > Meal Schedule`，对比现有 cron job
   - 缺的创建、过期的删除、匹配的不动
   - 体重提醒 cron（Mon & Thu）的同步

2. **Cron job 定义**（当前 "Cron job definitions" 段落）
   - 调用 `scheduled-reminders/scripts/create-reminder.sh`
   - 但 `--message` 改为指向 `notification-composer`：
     ```
     "Run notification-composer pre-send checks for breakfast.
      If passed, compose and send a breakfast reminder."
     ```

3. **阶段管理**（当前 "Lifecycle: Active → Recall → Silent" 段落）
   - Stage 1-4 的状态机逻辑
   - Stage 转换条件判断（2 天无回复 → Stage 2，等等）
   - 写 `engagement.notification_stage`

4. **自适应调时**（当前 "Adaptive Timing" 段落）
   - 检测用户回复延迟模式
   - 更新 `health-profile.md > Meal Schedule`
   - 停止长期无回复的餐次提醒

5. **用户提醒设置变更**（当前 "Reminder settings changes" 段落）
   - "停止早餐提醒"、"改晚餐到 8 点"、"恢复提醒"
   - 写 `engagement.reminder_config`

### 触发条件

- `meal-planner` 完成 onboarding 后激活
- 用户请求修改提醒设置时
- 其他 skill 需要验证/修复 cron 状态时

### 数据读写

| 操作 | 路径 | 方式 |
|------|------|------|
| 读 | `health-profile.md > Meal Schedule` | 直接读 |
| 读写 | `engagement.notification_stage` | 直接读写 |
| 读写 | `engagement.reminder_config` | 直接读写 |
| 读 | `engagement.last_interaction` | 直接读 |
| 调用 | `scheduled-reminders` create/list/remove | 脚本 |

---

## notification-composer 职责

每次 cron 触发时被唤起，决定"该不该发"和"发什么"。

### 包含内容（从 daily-notification 迁出）

1. **Pre-send 检查**（当前 "Pre-send Checks" 段落）
   - health-profile 存在？
   - 安静时段？
   - Stage 4（静默）？
   - 该餐已记录？
   - 用户调度约束？
   - 任何一项不通过 → `NO_REPLY`

2. **消息模板 / 话术生成**（当前 "Message Templates" 整个段落）
   - 餐食提醒：4 种技巧轮换、时段能量、新鲜度检查
   - 体重提醒：随意风格、必提空腹、不显示目标体重
   - 召回消息：Stage 2/3 的温暖召回话术

3. **回复处理**（当前 "Handling Replies" 段落）
   - 餐食回复 → 交给 `diet-tracking-analysis`
   - 体重回复 → 调用 `weight-tracker.py save`
   - 情绪信号 → 交给 `emotional-support`
   - 跳过/拒绝 → 简短确认

4. **Habit 整合**（当前 "Habit Check-ins" 段落）
   - 提供餐食对话作为载体，`habit-builder` 决定插入什么

5. **Weekly Low-Calorie Check**（当前该段落）
   - 每周一在第一餐提醒时执行

### 触发条件

- Cron job 触发时（通过 `--message` 中的指令）
- 用户回复提醒消息时

### 数据读写

| 操作 | 路径 | 方式 |
|------|------|------|
| 读 | `health-profile.md` | 直接读（meal schedule、unit、exercise habits） |
| 读 | `health-preferences.md > Scheduling & Lifestyle` | 直接读 |
| 读 | `USER.md > Name, Health Flags` | 直接读 |
| 读 | `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load` |
| 读 | `data/weight.json` | `weight-tracker.py load --last 1` |
| 读 | `engagement.notification_stage` | 直接读（判断是否 Stage 4） |
| 写 | `data/weight.json` | `weight-tracker.py save`（体重回复时） |

注意：`notification-composer` **只读** `engagement.notification_stage`，不写。写的权力在 `notification-manager`。

---

## SKILL-ROUTING.md 变更

### Priority Tiers 表

```diff
- | **P4 — Reporting** | `weekly-report`, `daily-notification` | Summaries and proactive outreach. |
+ | **P4 — Reporting** | `weekly-report`, `notification-manager`, `notification-composer` | Summaries and proactive outreach. |
```

### Pattern 5 更新

标题改为 "Notification Composer + Other Active Skill (P4 vs Any)"，逻辑不变（defer the notification）。因为实际被 defer 的是 composer 的执行，不是 manager。

### Single-Ask Rule 豁免

```diff
- **Scheduled reminders** (`daily-notification` cron-based meal/weight reminders)
+ **Scheduled reminders** (`notification-composer` cron-based meal/weight reminders)
```

---

## 其他 skill 引用更新

| 文件 | 当前引用 | 改为 |
|------|---------|------|
| `meal-planner/SKILL.md` | "activate `daily-notification-skill`" | "activate `notification-manager`" |
| `weight-loss-planner/SKILL.md` | "handled by `daily-notification-skill`" | "handled by `notification-manager`" |
| `diet-tracking-analysis/SKILL.md` | "daily-notification system" | "notification-manager system"（或保持泛称） |
| `exercise-tracking-planning/SKILL.md` | "`daily-notification` reads..." | "`notification-composer` reads..." |
| `emotional-support/SKILL.md` | "daily-notification" 相关条目 | 区分：提醒暂停→manager，回复处理→composer |
| `weight-tracking/SKILL.md` | "`daily-notification`" | "`notification-composer`" |
| `memory-consolidation/SKILL.md` | "daily-notification" | 视具体逻辑指向 manager 或 composer |
| `habit-builder/SKILL.md` | "Daily Notification" | "`notification-composer`"（提供对话载体的是 composer） |
| `scheduled-reminders/SKILL.md` | description 中提到 daily-notification | 更新为 notification-manager |

---

## plugin.json 变更

```diff
  "skills": [
    ...
-   "./daily-notification-skill",
+   "./notification-manager",
+   "./notification-composer",
    ...
  ]
```

---

## 文件系统变更

### 新建

```
notification-manager/
├── SKILL.md
notification-composer/
├── SKILL.md
├── references/
│   └── data-schemas.md    （从 daily-notification-skill 迁移）
```

### 删除

```
daily-notification-skill/     （整个目录，内容已拆入两个新 skill）
```

### evals

`daily-notification-skill/evals/evals.json` 需要审查，按职责拆分到两个新 skill 的 evals 目录。

### 打包脚本

- `.github/workflows/package-release.yml` — 替换 daily-notification-skill 为两个新 skill
- `scripts/package.sh` — 同上

---

## 交互边界示例

### 场景 1：Onboarding 后首次创建提醒

```
meal-planner 完成 → 激活 notification-manager
  → manager 读 health-profile.md，创建 3 个餐食 cron + 1 个体重 cron
  → cron 的 --message 指向 notification-composer
```

### 场景 2：午餐 cron 触发

```
cron 触发 → 启动 isolated session → agent 读到 --message 指令
  → 激活 notification-composer
  → composer 执行 pre-send 检查
  → 通过 → 读用户数据，生成话术，发送
  → 用户回复 → composer 处理回复（记录饮食/交给 diet-tracking）
```

### 场景 3：用户 2 天未回复

```
某次 cron 触发 → composer 正常执行
  → 但 notification-manager 定期检查 engagement.last_interaction
  → 发现 2 天无回复 → 切到 Stage 2
  → 写 engagement.notification_stage = 2
  → 下次 cron 触发时，composer 读到 Stage 2
  → composer 发送召回消息而非普通提醒
```

### 场景 4：用户说"把晚餐提醒改到 8 点"

```
消息路由 → notification-manager
  → 更新 health-profile.md Meal Schedule
  → auto-sync 删旧 cron、建新 cron
  → 回复用户确认
```

---

## 不变的部分

- `scheduled-reminders` — 纯工具层，不改
- 数据文件格式 — `engagement.*`、`data/weight.json`、`data/meals/` 结构不变
- 用户体验 — 用户感知不到拆分，提醒行为完全一致
