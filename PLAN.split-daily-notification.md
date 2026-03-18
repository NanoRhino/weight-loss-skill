# 拆分方案：daily-notification + scheduled-reminders → notification-manager + notification-composer

## 概述

将 `daily-notification-skill` 和 `scheduled-reminders` 合并拆分为两个 skill：

| Skill | 职责 | 关注点 |
|-------|------|--------|
| **notification-manager** | cron 基础设施 + 提醒生命周期管理 | "怎么发、什么时候发、要不要继续发" |
| **notification-composer** | 每次触发时的执行逻辑 | "该不该发、发什么内容、怎么处理回复" |

```
notification-manager     编排层：cron CRUD + 生命周期 + 自适应调时 + 设置变更
        ↓
notification-composer    执行层：pre-send 检查 + 话术生成 + 回复处理
```

两层而非三层。`scheduled-reminders` 的 cron 脚本直接收入 `notification-manager`。

### 为什么合并 scheduled-reminders

- 当前只有 `daily-notification` 调用它，没有其他 skill 使用
- `meal-planner` 明确写了 "Do NOT create cron jobs directly via scheduled-reminders"
- 合并后消除跨 skill 路径引用（`{scheduled-reminders:baseDir}`），降低复杂度
- 如果未来需要通用定时能力，可以再从 manager 中抽出

---

## notification-manager 职责

管理提醒的"存在"和 cron 基础设施。

### 来自 scheduled-reminders（整体吸收）

1. **`scripts/create-reminder.sh`**（原封迁入 `notification-manager/scripts/`）
   - 渠道自动检测（Slack / WeChat / WeCom）
   - 时区自动检测（`timezone.json`）
   - `openclaw cron add` 封装
   - 参数不变：`--agent`、`--channel`、`--name`、`--message`、`--cron`/`--at`、`--tz`、`--keep`、`--to`

2. **Cron 管理接口**
   - 创建：`bash {baseDir}/scripts/create-reminder.sh ...`
   - 查看：cron tool `action: "list"`
   - 删除：cron tool `action: "remove"` + `jobId`
   - 调整时间：删旧建新

### 来自 daily-notification（编排逻辑）

3. **Auto-sync 逻辑**（原 "Auto-sync on activation" 段落）
   - 读 `health-profile.md > Meal Schedule`，对比现有 cron job
   - 缺的创建、过期的删除、匹配的不动
   - 体重提醒 cron（Mon & Thu）的同步

4. **Cron job 定义**（原 "Cron job definitions" 段落）
   - 路径改为 `{baseDir}/scripts/create-reminder.sh`（本 skill 自有）
   - `--message` 指向 `notification-composer`：
     ```
     "Run notification-composer pre-send checks for breakfast.
      If passed, compose and send a breakfast reminder."
     ```

5. **阶段管理**（原 "Lifecycle: Active → Recall → Silent" 段落）
   - Stage 1-4 的状态机逻辑
   - Stage 转换条件判断（2 天无回复 → Stage 2，等等）
   - 写 `engagement.notification_stage`

6. **自适应调时**（原 "Adaptive Timing" 段落）
   - 检测用户回复延迟模式
   - 更新 `health-profile.md > Meal Schedule`
   - 停止长期无回复的餐次提醒

7. **用户提醒设置变更**（原 "Reminder settings changes" 段落）
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
| 读 | `timezone.json` | 直接读（cron 脚本自动检测） |

---

## notification-composer 职责

每次 cron 触发时被唤起，决定"该不该发"和"发什么"。

### 包含内容（从 daily-notification 迁出）

1. **Pre-send 检查**（原 "Pre-send Checks" 段落）
   - health-profile 存在？
   - 安静时段？
   - Stage 4（静默）？
   - 该餐已记录？
   - 用户调度约束？
   - 任何一项不通过 → `NO_REPLY`

2. **消息模板 / 话术生成**（原 "Message Templates" 整个段落）
   - 餐食提醒：4 种技巧轮换、时段能量、新鲜度检查
   - 体重提醒：随意风格、必提空腹、不显示目标体重
   - 召回消息：Stage 2/3 的温暖召回话术
   - Principles（One and done、Conversation > report、Variety、Anchor don't mirror）
   - Never-say 列表

3. **回复处理**（原 "Handling Replies" 段落）
   - 餐食回复 → 交给 `diet-tracking-analysis`
   - 体重回复 → 调用 `weight-tracker.py save`
   - 情绪信号 → 交给 `emotional-support`
   - 跳过/拒绝 → 简短确认

4. **Habit 整合**（原 "Habit Check-ins" 段落）
   - 提供餐食对话作为载体，`habit-builder` 决定插入什么

5. **Weekly Low-Calorie Check**（原该段落）
   - 每周一在第一餐提醒时执行

6. **Safety 检测与交接**（原 "Safety" 段落）
   - 检测危机信号，交给 `emotional-support`

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
| 读 | `engagement.notification_stage` | 直接读（判断 Stage 4、选召回话术） |
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

```diff
- ### Pattern 5: Daily Notification + Other Active Skill (P4 vs Any)
+ ### Pattern 5: Notification Composer + Other Active Skill (P4 vs Any)
```

逻辑不变（defer the notification）。实际被 defer 的是 composer 的执行，不是 manager。

### Single-Ask Rule 豁免

```diff
- **Scheduled reminders** (`daily-notification` cron-based meal/weight reminders)
+ **Scheduled reminders** (`notification-composer` cron-based meal/weight reminders)
```

---

## 其他 skill 引用更新

| 文件 | 当前引用 | 改为 |
|------|---------|------|
| `meal-planner/SKILL.md` | "activate `daily-notification-skill`" + "Do NOT create cron jobs directly via `scheduled-reminders`" | "activate `notification-manager`"（删除 scheduled-reminders 提示，因为已合并） |
| `weight-loss-planner/SKILL.md` | "handled by `daily-notification-skill`" | "handled by `notification-manager`" |
| `diet-tracking-analysis/SKILL.md` | "daily-notification system" | "notification-composer"（weekly-low-cal-check 由 composer 调用） |
| `exercise-tracking-planning/SKILL.md` | "`daily-notification` reads..." | "`notification-composer` reads..."（读训练计划的是 composer） |
| `emotional-support/SKILL.md` | "daily-notification" 相关条目 | 区分：提醒暂停→manager，回复处理→composer |
| `weight-tracking/SKILL.md` | "`daily-notification`" | "`notification-composer`"（调用 weight-tracker.py 的是 composer） |
| `memory-consolidation/SKILL.md` | "daily-notification" | 视具体逻辑指向 manager 或 composer |
| `habit-builder/SKILL.md` | "Daily Notification" | "`notification-composer`"（提供对话载体的是 composer） |

---

## plugin.json 变更

```diff
  "skills": [
    ...
-   "./daily-notification-skill",
+   "./notification-manager",
+   "./notification-composer",
    ...
-   "./scheduled-reminders",
    ...
  ]
```

---

## 文件系统变更

### 新建

```
notification-manager/
├── SKILL.md
├── scripts/
│   └── create-reminder.sh    （从 scheduled-reminders/scripts/ 迁入）
notification-composer/
├── SKILL.md
├── references/
│   └── data-schemas.md       （从 daily-notification-skill/references/ 迁入）
```

### 删除

```
daily-notification-skill/     （整个目录，内容已拆入两个新 skill）
scheduled-reminders/          （整个目录，脚本和文档已并入 notification-manager）
```

### evals

`daily-notification-skill/evals/evals.json` 需要审查，按职责拆分到两个新 skill 的 evals 目录。

### 打包脚本

- `.github/workflows/package-release.yml` — 删除 `daily-notification-skill` 和 `scheduled-reminders`，新增 `notification-manager` 和 `notification-composer`
- `scripts/package.sh` — 同上

---

## 交互边界示例

### 场景 1：Onboarding 后首次创建提醒

```
meal-planner 完成 → 激活 notification-manager
  → manager 读 health-profile.md
  → manager 调用自有 create-reminder.sh，创建 3 个餐食 cron + 1 个体重 cron
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
  → auto-sync：调用自有 create-reminder.sh 删旧 cron、建新 cron
  → 回复用户确认
```

### 场景 5：未来某 skill 需要创建一次性提醒（扩展性）

```
新 skill 需要定时 → 直接调用 notification-manager 的 create-reminder.sh
  → 传 --at "30m" --message "..."
  → 无需新建 skill，manager 已包含通用 cron 能力
```

---

## 不变的部分

- 数据文件格式 — `engagement.*`、`data/weight.json`、`data/meals/` 结构不变
- Cron 脚本行为 — `create-reminder.sh` 逻辑和参数不变，只是换了目录
- 用户体验 — 用户感知不到拆分，提醒行为完全一致

---

## 迁移检查清单

- [ ] 创建 `notification-manager/` 目录和 SKILL.md
- [ ] 迁移 `scheduled-reminders/scripts/create-reminder.sh` → `notification-manager/scripts/`
- [ ] 创建 `notification-composer/` 目录和 SKILL.md
- [ ] 迁移 `daily-notification-skill/references/data-schemas.md` → `notification-composer/references/`
- [ ] 拆分 `daily-notification-skill/evals/evals.json` 到两个新 skill
- [ ] 更新 `plugin.json`：删 2 旧 skill，加 2 新 skill
- [ ] 更新 `SKILL-ROUTING.md`：Priority Tiers、Pattern 5、Single-Ask Rule
- [ ] 更新 `meal-planner/SKILL.md` 引用
- [ ] 更新 `weight-loss-planner/SKILL.md` 引用
- [ ] 更新 `diet-tracking-analysis/SKILL.md` 引用
- [ ] 更新 `exercise-tracking-planning/SKILL.md` 引用
- [ ] 更新 `emotional-support/SKILL.md` 引用
- [ ] 更新 `weight-tracking/SKILL.md` 引用
- [ ] 更新 `memory-consolidation/SKILL.md` 引用
- [ ] 更新 `habit-builder/SKILL.md` 引用（如有）
- [ ] 更新 `README.md`
- [ ] 更新 `.github/workflows/package-release.yml`
- [ ] 更新 `scripts/package.sh`
- [ ] 删除 `daily-notification-skill/` 目录
- [ ] 删除 `scheduled-reminders/` 目录
- [ ] 全局搜索残留引用：`daily-notification`、`scheduled-reminders`
