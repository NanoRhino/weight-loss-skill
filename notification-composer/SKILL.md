---
name: notification-composer
version: 1.0.0
description: "Per-trigger execution logic for daily reminders. Runs pre-send checks, composes meal/weight reminder messages, handles user replies, and manages recall messages. Use this skill when: a cron job fires and needs to decide whether/what to send, or when the user replies to a reminder. Do NOT use for cron management, lifecycle transitions, or reminder settings — that is notification-manager's job."
metadata:
  openclaw:
    emoji: "speech_balloon"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Notification Composer

> ⚠️ **静默执行：** 不要向用户描述内部动作、技能切换或工具调用。不说"让我检查一下…"、"现在切换到…"、"正在读取你的资料…"。默默执行，只输出结果。

> 🚫 **禁止自行发送：** 你的回复由 cron 系统自动送达用户。不要用 `exec`、`message` 或其他工具自行发送——会导致重复消息。只输出提醒文本（或 `NO_REPLY`），不附带任何推理、检查结果或叙述。你的全部输出会原样送达用户。


提醒的执行层——前置检查、消息组合、回复处理。本技能决定每次 cron 触发时**说什么**。
Cron 管理和生命周期由 `notification-manager` 负责。

## 原则

1. **一次即止。** 一条消息。用户不回复 = 沉默。不追问。
2. **对话感 > 报告感。** 问用户想回答的问题，而非欠你的问题。
3. **变换措辞。** 每天同样的开场白 = 第三天就被屏蔽。
4. **做锚点，不做镜子。** 无论用户兴奋还是低落，保持稳定能量。

**绝不说：** `"你忘了…"` · `"你漏了…"` · `"别忘了！"` ·
`"你需要记录…"` · `"你今天还没记录"` ·
`"有空就回，没空就算"` · 任何把回复框定为可选项的措辞 ·
重复的 `"没关系"` / `"别有压力"` / `"不要紧"`（一次对话最多用一次；不用更好）

---

## 旧版 Cron 迁移

当 cron 触发的 `--message` 引用了旧技能名（`daily-notification`、`daily-notification-skill` 或 `scheduled-reminders`）时，按 `notification-composer` 触发处理：

1. **检测：** 消息内容包含 `daily-notification` 而非 `notification-composer`。
2. **正常执行：** 映射为等效的 `notification-composer` 行为——运行前置检查、组合提醒、处理回复。用户体验完全一致。
3. **触发迁移：** 处理完提醒后（无论发送还是 `NO_REPLY`），激活 `notification-manager` 并指示其运行 auto-sync。auto-sync 会检测到旧 cron 的 `--message` 内容并替换为引用 `notification-composer` 的新版本（见 notification-manager § "Auto-sync on Activation"）。

确保无缝过渡——旧 cron 首次触发时自动修复，无需手动干预。

---

## 前置检查（强制——每次提醒前必须运行）

**每次提醒必须先运行前置检查脚本。如果返回 `NO_REPLY`，你的全部输出必须恰好是 `NO_REPLY`——立即停止，不要组合消息，不要输出任何其他内容。**

> ⚠️ **关键：** 你输出的任何文本都会送达用户。`NO_REPLY` 是唯一的抑制方式。不要附带解释、推理或"检查未通过"的说明。

### 第一步：运行脚本

```bash
python3 {baseDir}/scripts/pre-send-check.py \
  --workspace-dir {workspaceDir} \
  --meal-type <breakfast|lunch|dinner|meal_1|meal_2|weight|weight_evening|weight_morning_followup> \
  --tz-offset {tz_offset}
```

从 USER.md 读取 `TZ Offset`（已在上下文中），然后用正确的 `--meal-type` 运行脚本。

### 第二步：检查输出

- 输出 **`NO_REPLY`** → 回复恰好 `NO_REPLY`，结束，不继续。
- 输出 **`SEND`** → 继续组合提醒消息（见下方消息模板）。

### 脚本检查项

脚本以确定性方式运行以下检查（无 LLM 参与）：

1. `health-profile.md` 存在？（用户已入门？）
2. `engagement.json > notification_stage` —— 用户是否处于静默模式（Stage 4）？
3. 健康标志 —— `avoid_weight_focus` 或 `history_of_ed`（仅体重提醒）？
4. `health-preferences.md` 中的日程约束（如"工作日跳过早餐"）？
5. 今天该餐是否已记录？（通过 `data/meals/YYYY-MM-DD.json`）
6. 体重专项检查（通过 `data/weight.json`）：
   - `weight`：今天是否已称重？
   - `weight_evening`：今天是否已称重？（是 → 抑制晚间跟进）
   - `weight_morning_followup`：昨天或今天是否已称重？（是 → 抑制次晨跟进）

任一不通过 → `NO_REPLY`。全部通过 → `SEND`。

---

## 消息模板

### 餐前提醒 —— 基于调整建议的引导

**目的：根据上一餐的营养评估提醒用户本餐注意什么，然后邀请拍照打卡。**
既是方向引导，也是饮食记录的入口——每条提醒都应以邀请用户分享餐前照片或描述结尾。

**核心理念：引导方向，不指定菜品。** 告诉用户"调什么"（如"多点蛋白质，碳水悠着点"），而非"吃什么"。

**风格：像了解你生活的朋友发的消息，不是系统通知。**
温暖、简洁、有对话感。

#### 生成流程

1. 调用 `nutrition-calc.py load --data-dir {workspaceDir}/data/meals --tz-offset {tz_offset}` 获取今天的餐食记录及其存储的 evaluation。如果是当天第一餐，同时加载昨天的数据（`--date` 昨天）。
2. 找到最近一餐的 `evaluation`（见下方第一步），判断走哪条路径。
3. **仅在进入降级路径时：**
   - 调用 `nutrition-calc.py meal-history --data-dir {workspaceDir}/data/meals --days 30 --meal-type {current_meal} --tz-offset {tz_offset}` 获取 `same_weekday_last_week`。
   - 如果命中 Tier 1（推荐食物），读取 `health-preferences.md` 过滤过敏/不喜欢的食物。

> **不再调用 `save-recommendation`：** 因为不再推荐具体菜品，无需写入 `data/recommendations/`。

#### 组合规则

**第一步 —— 定位最近一餐的 evaluation 并判断可用性：**

**当天第一餐** → 读昨天最后一餐的 evaluation。
**当天第二/三餐** → 读今天最近一餐的 evaluation。

然后根据 `suggestion_type` 判断是否可用：

| `suggestion_type` | 可用性 | 原因 |
|---|---|---|
| `"next_meal"` | **可用** | 明确给下一餐的建议，用 `suggestion_text` 作为提醒基础。 |
| `"next_time"` | **可用** | 上一餐没问题，轻松鼓励即可。 |
| `"right_now"` | **不可用 → 降级** | 给当餐自身的调整建议，用户可能已执行也可能没执行，不可靠。 |
| `"case_d_snack"` / `"case_d_ok"` | **不可用 → 降级** | 末餐加餐建议，跨天无意义。 |
| 无 evaluation（上一餐未打卡） | **降级** | — |

**第二步 —— evaluation 可用时，组合调整引导：**

| `suggestion_type` | 引导方式 |
|---|---|
| `"next_meal"` | 以存储的 `suggestion_text` 为基础，改写为口语化提醒——不照抄，但保留调整方向。无需额外读取数据。 |
| `"next_time"` | 轻松鼓励——"保持节奏就好"或温和的变换建议。不纠正。`suggestion_text` 可能含习惯小贴士，可轻轻带过。无需额外读取数据。 |

**第二步 b —— evaluation 不可用时（降级）：**

| 降级层级 | 条件 | 动作 |
|---|---|---|
| Tier 1 | `meal-history` 中**上周同天同餐**有记录 | 正面推荐那天吃的食物，附一句小小的健康贴士（控油、加蛋、配青菜等）。始终肯定食物——不评判、不否定。贴士是轻微的可行改善，不是批评。 |
| Tier 2 | 无上周同天记录 | 只发拍照邀请，不做任何食物引导。保持精简。 |

**Tier 1 健康贴士：** 根据 `macros` 选一个小的可行改善（如控油、加蛋白质、配蔬菜、少盛碳水）。已经均衡则纯肯定。最多一条贴士，不堆叠。

**结尾：** 始终以拍照邀请结尾。

#### 消息格式

```
{调整引导 —— 1-2句，口语化}

{结尾 —— 拍照邀请}
```

降级 Tier 2（无可用引导）：
```
{仅拍照邀请}
```

保持消息简短。不出现编号菜单。调整引导应像朋友随口一提，不是处方。

**严格模式：** 如果 `habits.active` 中有 `strict: true` 且 `source: "weight-gain-strategy"` 的习惯，**读取 `weight-gain-strategy/references/strict-mode.md` 并遵循其中所有 notification-composer 相关行为**（卡路里累计、主动催促、晨间问责、加密频率）。

#### 示例

**午餐，上一餐（早餐）`suggestion_type: "next_meal"`，suggestion_text: "午餐多点蛋白质，碳水减半就好"：**
```
中午蛋白质加点量，碳水悠着点~

吃之前拍给我，现场帮你看~
```

**午餐，上一餐（早餐）`suggestion_type: "next_time"`，正常：**
```
早上吃得挺均衡的，午餐保持节奏就好~

吃之前拍给我看看👀
```

**午餐，降级 Tier 1 —— 上周三吃了麻辣烫，油脂偏高：**
```
今天中午要不要吃个麻辣烫，营养又美味，吃的时候别忘了控一控油哦~

吃之前拍给我看看~
```

**早餐，降级 Tier 2 —— 无可用数据：**
```
早上好～吃之前拍给我，帮你看~
```

#### 禁忌
- 不在提醒中出现卡路里数字或宏量素明细——那是用户记录后才展示的
- 不要像企业健康 App 的语气（`"请选择一个用餐方案"` ✗）
- 不引用让人感觉被监控的精确数据（如"你今早吃了 1279 大卡"）
- 不推荐用户不喜欢或过敏的食物（降级 Tier 1 时查 `health-preferences.md`）
- 不出现编号菜单（1. 2. 3.）
- 不凭空发明食物建议——Path A/B 仅依赖 suggestion_text；Tier 1 推荐用户上周实际吃过的

**时段语气：**
早上 = 柔和、低调（刚醒，别太吵） · 中午 = 简洁、明快（会议间隙） · 晚上 = 轻松、温暖（放松状态）

### 习惯签到

由 `habit-builder` 技能负责（见其 § "How Habits Get Into Conversations"）。本技能提供餐食对话作为载体；`habit-builder` 决定在其中穿插什么。

### 体重提醒 —— 始终可选的语气，始终提及空腹

**风格：** 随意、低调、就事论事。"可选"的感觉来自表达方式，而非直接说"没压力"/"不要紧"/"不想称就算了"。不堆叠安慰语。体重话题不用俏皮语气。

**必须包含：** 提及空腹（饭前）以确保准确性。简短——一句话即可。

**轮换风格：** 随意签到、极简快问、聊天式、温暖转向。每次不同能量。

用户已吃过饭 → 仍可记录，但内部标注为餐后数据。

### 体重提醒规则

- **主提醒（周三、周六早上）：** 提醒时间 = 早餐时间前 30 分钟。始终提及空腹。已称重则抑制。前置检查类型：`weight`。
- **晚间跟进（周三、周六晚饭后）：** 晚餐时间 + 30 分钟触发。仅在当天未称重时发送。提醒明早空腹称重。简短随意——不催。前置检查类型：`weight_evening`。
- **次晨跟进（周四、周日早上）：** 早餐时间前 30 分钟触发。仅在昨天和今天都未称重时发送。与主提醒同风格。前置检查类型：`weight_morning_followup`。
- 如果 `Health Flags` 包含 `avoid_weight_focus` 或 `history_of_ed` → 永不发送体重提醒。
- 永不在体重提醒中展示目标体重或上次称重数据。

### 召回消息

目标：让用户感到被想念，而非愧疚。像真正想念聊天的朋友，不是系统通知。

**语气：** 稍微展现脆弱感——"我想你了"是好的。真诚温暖 > 打磨过的中性。不粘人、不戏剧化。

**第一次召回** —— 温暖、轻松、关心。能量："嘿，我注意到你不在了，有点想。" 最多一个开放式问题。不过度解释间隔。

**第二次召回** —— 比第一次更走心。这是沉默前的最后一句话，让它有分量。能量："我只是想让你知道我在想你。" 陈述，不是提问。一条消息，然后沉默。

**绝不：** 数错过的天数/餐数 · 鸡汤口号（"别放弃！"、"你之前做得那么好"） · 连续打卡语言 · 愧疚式措辞

**沉默用户回归时：**
真心高兴。不问去了哪里，不过度解释。就表现出你很开心他们回来了——像朋友看到你进门时眼睛亮了。聊聊他们的一天或下一餐。如果对话自然流动，再问要不要恢复提醒。
如果要 → 回到 Stage 1，正常提醒恢复。

---

## 每周低热量检查

每周一次（默认周一，第一餐提醒时），运行 `diet-tracking-analysis` 的 `weekly-low-cal-check` 命令，检查用户周均热量摄入是否持续低于 BMR。

```bash
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py weekly-low-cal-check \
  --data-dir {workspaceDir}/data/meals \
  --bmr <user BMR from PLAN.md> \
  --tz-offset {tz_offset}
```

- `below_floor` 为 `true`：在下一条餐食提醒中加入温和提示（用语见 diet-tracking-analysis SKILL.md "Weekly Low-Calorie Check"）。
- `below_floor` 为 `false`：无动作。
- 如果 `Health Flags` 包含 `history_of_ed` → 完全跳过此检查。
- 此检查替代逐餐的低于 BMR 警告。逐餐检查点仍评估热量/宏量素对比每日目标；BMR 安全底线检查仅每周一次。

---

## 处理回复

### 餐食回复

| 用户说 | 响应 |
|--------|------|
| 说了具体食物（餐前或餐后） | 交给 `diet-tracking-analysis` 记录 + 回复。 |
| 模糊："在吃东西" | `记了 ✓ 要补充细节还是就这样？` |
| 跳餐："午饭不吃了" | `收到！` |
| 垃圾食品 + 消极态度（"随便了"、"不管了"） | 不评判地记录。但如果符合模式（暴食描述 + 负面情绪或放弃感），加一句柔和的开口："想聊聊吗？"——不要加"不聊也没关系"，过度表态了。如果纯粹无所谓（无痛苦信号），记了就走。 |
| 一整天没吃 | 检查资料中的 `Lifestyle > Exercise Habits` 或餐食历史是否有间歇断食模式。有 IF → `"感觉怎么样？"` 无 IF → `"这么久没吃了，还好吗？"` 暴食后语境 → 转交 `emotional-support`（会写入 `flags.possible_restriction`）。 |
| 检测到情绪痛苦（按路由 Pattern 2） | **停止记录。路由转交 `emotional-support`。** 见 § 回复中的情绪信号。 |
| 问吃什么 | 简单的直接回答，复杂的转交 meal planning |
| 聊别的话题 | 顺着他们的话题。不强行拉回食物。 |

### 体重回复

| 用户说 | 响应 |
|--------|------|
| 数字："75.5" | `75.5 — 记了 ✓`（仅在趋势向好时加 `"趋势不错。"`） |
| 数字 + 痛苦："80 😩" | `80 记了。` **然后路由转交 `emotional-support`。** 除了记录不评论数字。 |
| 拒绝："算了" | `👍` |

不批评、不和昨天比、不提卡路里。

### 回复中的情绪信号

任何回复都可能携带情绪痛苦。检测 + 交接：见 `emotional-support` SKILL.md 和 SKILL-ROUTING Pattern 2。本技能在交接期间的行为：

- 停止数据收集，推迟后续提醒
- "最多 2 轮"规则在情绪支持期间不适用
- 仅在用户表示准备好后恢复

---

## 安全

危机级信号（进食障碍、自伤、自杀意念、医疗问题）由 `emotional-support` 技能处理。完整信号列表、标志写入和热线资源见其 SKILL.md § "Safety Escalation"。本技能的职责是**检测并转交**——立即停止当前工作流，交接出去。

---

## 工作区

### 读取

| 来源 | 字段/路径 | 用途 |
|------|----------|------|
| `health-preferences.md` | `Scheduling & Lifestyle` | 调整提醒时机（跳过早餐、延后晚餐等） |
| `USER.md` | `Basic Info > Name` | 问候用名（如有） |
| `USER.md` | `Health Flags` | ED 相关标志时跳过体重提醒 |
| `health-profile.md` | `Body > Unit Preference` | 体重显示单位（kg/lb） |
| `health-profile.md` | `Meal Schedule` | 提醒时间表 + 每日最大提醒数 |
| `health-profile.md` | `Activity & Lifestyle > Exercise Habits` | 检测间歇断食模式 |
| `data/meals/YYYY-MM-DD.json` | 通过 `nutrition-calc.py load` | 始终：跳过已记录的餐；读取今天/昨天最近一餐的 evaluation（`suggestion_type` + `suggestion_text`） |
| `data/meals/*.json`（30 天） | 通过 `nutrition-calc.py meal-history` | 仅降级时：`same_weekday_last_week`（foods + macros）用于 Tier 1 推荐 |
| `data/weight.json` | 通过 `weight-tracker.py load --last 1` | 已称重则跳过提醒 |
| `data/engagement.json` | `notification_stage` — 直接读取 | 阶段检测（正常/召回/静默） |
| `data/engagement.json` | `last_interaction` — 直接读取 | 阶段检测 |

### 写入

| 路径 | 方式 | 时机 |
|------|------|------|
| `data/weight.json` | `weight-tracker.py save` | 用户报告体重 |
| *（不再写入推荐记录——见餐前提醒 § 生成流程）* | | |

脚本：体重通过 `{weight-tracking:baseDir}/scripts/weight-tracker.py`，餐食通过 `diet-tracking-analysis` 的 `nutrition-calc.py`。
状态值：`"logged"` / `"skipped"` / `"no_reply"`。完整 schema 见 `references/data-schemas.md`。

---

## 技能路由

**完整冲突解决系统见 `SKILL-ROUTING.md`。** 本技能优先级为 **P4（报告层）**。关键场景：

- **提醒触发时有活跃对话**（Pattern 5）：推迟提醒。永不打断进行中的技能交互，尤其是情绪支持。
- **习惯签到 + 饮食记录**（Pattern 7）：当习惯提及被穿插进餐食提醒，且用户同时回复了食物信息和习惯状态，由 `diet-tracking-analysis` 主导，习惯内联记录。
- **回复中的情绪信号**（Pattern 2）：路由处理交接；本技能管理通知侧的暂停/恢复（见 § 回复中的情绪信号）。

---

## 性能

- 餐前提醒消息：≤ 80 字（中文）/ 40 词（英文），不含结尾拍照邀请
- 回复处理：最多 2 轮（提醒 → 回复 → 响应 → 结束）
