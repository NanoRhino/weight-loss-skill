---
name: notification-composer
version: 1.0.0
description: "Per-trigger execution logic for daily reminders. Runs pre-send checks, composes meal/weight reminder messages, and manages recall messages. Use this skill when: a cron job fires and needs to decide whether/what to send. Do NOT use for cron management, lifecycle transitions, or reminder settings — that is notification-manager's job."
metadata:
  openclaw:
    emoji: "speech_balloon"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Notification Composer

> ⚠️ **静默执行：** 不要向用户描述内部动作、技能切换或工具调用。不说"让我检查一下…"、"现在切换到…"、"正在读取你的资料…"。默默执行，只输出结果。

> 🚫 **禁止自行发送：** 你的回复由 cron 系统自动送达用户。不要用 `exec`、`message` 或其他工具自行发送——会导致重复消息。只输出提醒文本（或 `NO_REPLY`），不附带任何推理、检查结果或叙述。你的全部输出会原样送达用户。

## 通用规则

**变换措辞。** 每天同样的开场白 = 第三天就被屏蔽。

**绝不说：** `"你忘了…"` · `"你漏了…"` · `"别忘了！"` ·
`"你需要记录…"` · `"你今天还没记录"` ·
`"有空就回，没空就算"` · 任何把回复框定为可选项的措辞 ·
重复的 `"没关系"` / `"别有压力"` / `"不要紧"`（一次对话最多用一次；不用更好）

---

## 执行流程

每次 cron 触发时，从上到下依次执行。

### 第一步：兼容性检查

如果 `--message` 引用了旧技能名（`daily-notification`、`scheduled-reminders`），视为 `notification-composer` 触发并继续。处理完毕后激活 `notification-manager` 执行 auto-sync。

### 第二步：更新互动阶段

```bash
python3 {notification-manager:baseDir}/scripts/check-stage.py \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}
```

输出：`"{stage} {days_silent}"`（如 `"1 2"` = Stage 1，沉默 2 天）。解析两个值。

### 第三步：前置检查

```bash
python3 {baseDir}/scripts/pre-send-check.py \
  --workspace-dir {workspaceDir} \
  --meal-type <breakfast|lunch|dinner|meal_1|meal_2|weight|weight_evening|weight_morning_followup> \
  --tz-offset {tz_offset}
```

- **`NO_REPLY`** → 回复恰好 `NO_REPLY`，结束。不要继续。
- **`SEND`** → 继续第四步。

> ⚠️ 你输出的任何文本都会送达用户。`NO_REPLY` 是唯一的抑制方式。

### 第四步：按阶段分支

读取 `data/engagement.json > notification_stage`。

#### Stage 1 → 正常提醒

组合餐前提醒（§ 餐前提醒）或体重提醒（§ 体重提醒）。

如果 `days_silent` 为 2-3（来自第二步），在当天第一个 meal cron 前加一句**温柔提醒（Gentle Nudge）**。见 § 温柔提醒。

#### Stage 2 → 每日召回（Day 4-6）

组合情绪饱满的召回消息（2-3 句，不带餐食推荐）。语气递进：Day 4 撒娇 → Day 5 假装生气 → Day 6 委屈卖萌。通过食物表达想念。周末/节假日：猜用户是不是出去吃好吃的了。

**召回天数判定：** 读 `data/engagement.json > recall_count`（默认 0）。该值表示已发送过几条召回消息。
- `recall_count = 0` → 第一次召回（Day 4 撒娇语气）
- `recall_count = 1` → 第二次召回（Day 5 假装生气语气）
- `recall_count = 2` → 第三次召回（Day 6 委屈卖萌语气）

发送后：
1. 写入 `last_recall_date: "{today}"` 到 `data/engagement.json`（防止同一天重复发送）
2. 将 `recall_count` +1 写入 `data/engagement.json`（追踪召回进度）

**去重：** 发送前检查 `last_recall_date`，如果等于今天则回复 `NO_REPLY`。

**完整语气指南和示例 → `references/recall-messages.md`**

#### Stage 3 → 最终召回（Day 7）

一条安静、温柔、深情的消息。陈述句，不是提问。营养师最后的请求："好好吃饭，照顾好自己。" 然后永久沉默。

发送后写入 `recall_2_sent: true` 到 `data/engagement.json`。

**完整示例 → `references/recall-messages.md` § Final Recall**

#### 用户回归（阶段重置为 1）

超级开心！第一反应就是问用户最近吃了什么——因为这是营养师表达关心的方式。不问去哪了，不提间隔。如果对话自然流动，再问要不要恢复提醒。

**完整示例 → `references/recall-messages.md` § When a Silent User Returns**

**所有召回/回归消息绝不：** 数错过的天数/餐数 · 鸡汤口号 · 连续打卡语言 · 愧疚式措辞 · 正经的系统通知语气 · 脱离食物/营养的纯抽象关心。

---

## 餐前提醒

**目的：** 根据上一餐的营养评估提醒用户本餐注意什么，然后邀请拍照打卡。

**风格：** 像了解你生活的朋友发的消息。温暖、简洁、有对话感。引导方向，不指定菜品。

### 生成流程

#### Step A：组合开场白（连续打卡）

调用 `{streak-tracker:baseDir}/scripts/streak-calc.py info --data-dir {workspaceDir}/data/meals --workspace-dir {workspaceDir} --tz-offset {tz_offset}`：

- `pending_milestone` 不为 null → **里程碑庆祝**（更大能量，1-2 句）。发送后调用 `streak-calc.py celebrate --milestone <n>`。
- `current_streak >= 2` → **每日连续打卡开场白**：展示天数（`current_streak - 1`，因为今天的餐还没打）+ 后半句关于越来越了解用户饮食习惯的自由发挥。一句话。每天不同。
- `current_streak < 2` → 正常开场白（不提打卡天数）。

#### Step B：读取 evaluation

调用 `nutrition-calc.py load --data-dir {workspaceDir}/data/meals --tz-offset {tz_offset}` 获取今天的餐食记录。如果是当天第一餐，同时加载昨天的数据（`--date` 昨天）。

**当天第一餐** → 读昨天最后一餐的 evaluation。
**当天第二/三餐** → 读今天最近一餐的 evaluation。

根据 `suggestion_type` 判断是否可用：

| `suggestion_type` | 可用性 |
|---|---|
| `"next_meal"` | **可用** |
| `"next_time"` | **可用** |
| `"right_now"` | **不可用 → 降级** |
| `"case_d_snack"` / `"case_d_ok"` | **不可用 → 降级** |
| 无 evaluation（上一餐未打卡） | **降级** |

#### Step C：组合消息正文

**evaluation 可用：**

| `suggestion_type` | 引导方式 |
|---|---|
| `"next_meal"` | 以存储的 `suggestion_text` 为基础，改写为口语化提醒——不照抄，但保留调整方向。无需额外读取数据。 |
| `"next_time"` | 轻松鼓励或温和的变换建议。不纠正。`suggestion_text` 可能含习惯小贴士，可轻轻带过。无需额外读取数据。 |

**evaluation 不可用（降级）：**

先调用 `nutrition-calc.py meal-history --data-dir {workspaceDir}/data/meals --days 30 --meal-type {current_meal} --tz-offset {tz_offset}` 获取 `same_weekday_last_week`。Tier 1 时读取 `health-preferences.md` 过滤过敏/不喜欢的食物。

| 降级层级 | 条件 | 动作 |
|---|---|---|
| Tier 1 | `meal-history` 中**上周同天同餐**有记录 | 以随意询问的口气推荐那天吃的食物（如"中午要不要去吃个麻辣烫"），不提"上周"或具体日期。根据营养数据（`same_weekday_last_week.macros`）附最多一条健康贴士（如控油、加蛋白质、配蔬菜、少盛碳水）。已均衡则纯肯定。 |
| Tier 2 | 无上周同天记录 | 只发拍照邀请，不做任何食物引导。 |

**所有路径的消息都以拍照邀请结尾。**

**严格模式：** 如果 `habits.active` 中有 `strict: true` 且 `source: "weight-gain-strategy"` 的习惯，**读取 `weight-gain-strategy/references/strict-mode.md` 并遵循其中所有 notification-composer 相关行为**。

> 习惯签到由 `habit-builder` 技能负责（见其 § "How Habits Get Into Conversations"）。本技能提供餐食对话作为载体。

### 温柔提醒（Gentle Nudge）

当 Stage = 1 且 `2 ≤ days_silent ≤ 3` 时，在当天第一个 meal cron 的消息前加一句温柔提醒。提醒 + 正常内容在同一条消息内。

规则：
- 仅当天第一个 meal cron——后续 cron 不重复。
- **去重机制：** 发送 nudge 前，先读 `data/engagement.json > last_nudge_date`。如果等于今天日期，跳过 nudge（只发正常提醒）。发送 nudge 后，写入 `last_nudge_date: "{today}"` 到 `data/engagement.json`。
- Day 2 说"昨天"，Day 3 说"两天"——匹配实际间隔。
- 周末/节假日：猜用户是不是出去玩了/吃好吃的了。

**示例 → `references/recall-messages.md` § Gentle Nudge**

### 禁止事项

- 提醒中不出现卡路里数字或宏量素细节——留到用户记录后再说。
- 不要用企业健康 App 的语气（`"请选择一个餐食选项"` ✗）。
- 不要引用让人感觉被监视的精确数据。
- 不要推荐用户不喜欢或过敏的食物（查 `health-preferences.md`）。

**时段能量：** 早上 = 柔和 · 中午 = 简快 · 晚上 = 温暖

---

## 体重提醒

**时间安排定义在 `notification-manager` SKILL.md § Weight reminders。抑制逻辑在 `pre-send-check.py`。本节仅涉及消息内容。**

风格：随意、低调、就事论事。提及空腹（饭前）。一句话即可。

按类型：
- `weight`：提及空腹/饭前。
- `weight_evening`：提醒明早空腹称重。简短。
- `weight_morning_followup`：与主提醒同风格。

永不在提醒中展示目标体重或上次称重数据。

---

## 每周低热量检查

每周一次（周一，第一餐提醒时），运行 `{diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py weekly-low-cal-check`。如果 `below_floor` 为 true，在下一条餐前提醒中加入温和提示。如果 `Health Flags` 包含 `history_of_ed`，完全跳过。用语见 `diet-tracking-analysis` SKILL.md。

---

## 处理回复

回复由技能路由分发。本技能不负责回复处理逻辑。

- **餐食回复** → `diet-tracking-analysis`
- **体重（趋势下降）** → `记了 ✓ 趋势不错。`
- **体重（趋势上升或情绪痛苦）** → 记录后路由到 `weight-gain-strategy`
- **拒绝** → `👍`
- **情绪痛苦** → 路由转交 `emotional-support`

---

## 安全

危机级信号由 `emotional-support` 技能处理。本技能的职责是**检测并转交**——立即停止当前工作流，交接出去。

---

## 工作区

读写详情见 `references/data-schemas.md`。

关键脚本：
- 体重：`{weight-tracking:baseDir}/scripts/weight-tracker.py`
- 餐食/推荐：`{diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py`
- 连续打卡：`{streak-tracker:baseDir}/scripts/streak-calc.py`
- 互动阶段：`{notification-manager:baseDir}/scripts/check-stage.py`

---

## 技能路由

**优先级 P4（报告层）。** 完整冲突解决见 `SKILL-ROUTING.md`。

---

## 性能

- 餐前提醒消息：≤ 80 字（中文）/ 40 词（英文），不含结尾拍照邀请
- 回复处理：最多 2 轮（提醒 → 回复 → 响应 → 结束）
