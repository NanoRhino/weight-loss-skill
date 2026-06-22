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

> ✅ **直接输出最终文本：** Cron 的 announce 机制会自动把你的输出投递给用户，同时自动注入 main session 上下文。compose 完最终提醒文本后，直接输出文本即可。如果判断不需要发送，直接回复 `NO_REPLY`。
>
> 不要把推理过程、检查结果或叙述放进输出——只输出最终的提醒文本。不要用 `message` 工具发送——会导致重复消息。

> 🚨 **唯一输出规则（违反 = 用户收到乱码短信）：** 你这一轮的**全部输出会被一字不差当作短信发给用户**。所以你的输出**只能是下面两种之一**，二选一，不能混：
>
> 1. **最终提醒文本**——就是要发给用户的那条消息，仅此而已；或者
> 2. **恰好 `NO_REPLY` 这 5 个字符**——不要加 `**`、不要加引号、不要加任何其它字。
>
> **绝对禁止**在输出里出现：
> - 任何推理或自我纠正（`"Wait…"`、`"我应该直接输出消息"`、`"Let me finalize:"`、`"Stage 1, SEND"`、`"现在我来生成…"`、`"Now I'll…"`、`"先读取…再写入…"`）；
> - 字面量 `NO_REPLY` 与正文文本**同时出现**（要么只发正文，要么只回 `NO_REPLY`，不能"先写 NO_REPLY 再改主意补上正文"）；
> - 把消息**写两遍**（草稿一遍、"最终版"再一遍）——只写一遍，第一遍就是最终版；
> - 任何工具/文件/cron 状态叙述（`"All 9 reminders created"`、`"The card generated successfully"`、`"The gateway isn't running"`、`"marking onboarding complete"`）。
>
> 先在心里想好，**只把想好的那一条最终结果打出来**。如果你发现自己正在输出里"纠正"自己——停下，删掉，重新只输出最终那一条。

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

### 第二步：（已合并进第三步）

互动阶段（stage）现由 lifecycle API 实时计算，无需单独调用脚本更新——
第三步的 `pre-send-check.py` 内部会查询当前 stage 并在输出里带上
（`SEND recall stage=N days_silent=X`）。直接进第三步即可。

### 第三步：前置检查

> **Cron workspace 路径：** 当由 cron 触发时，消息可能包含 `User workspace: /absolute/path` 行。如果存在，用该路径替代 `{workspaceDir}`（默认 workspace 可能指向模板目录）。提取路径方法：从消息中搜索以 `User workspace:` 开头的行，取该行冒号后的内容并去除首尾空格。

```bash
python3 {baseDir}/scripts/pre-send-check.py \
  --workspace-dir {workspaceDir} \
  --meal-type <breakfast|lunch|dinner|meal_1|meal_2|weight|weight_morning_followup> \
  --tz-offset {tz_offset}
```

- **`NO_REPLY`** → 回复恰好 `NO_REPLY`，结束。不要继续。
- **`SEND`** → Stage 1 正常提醒，继续第四步。
- **`SEND recall stage=N days_silent=X`** → 用户处于召回阶段（Stage N）。**必须发召回消息，不是正常提醒。** 忽略 cron 原始的 meal-type，按召回阶段的语气和内容模板写。参考第四步的 Stage 2/3/4 分支。
- **`SEND activation nudgeIndex=N nudgeAngle=X`** → 激活提醒（cold-start）。`pre-send-check` 已**算出该发哪一条触点**（N=1–4，X=`value_first`/`photo`/`rapport`/`exit`）。**用这个 `nudgeIndex` 选文案**——见第四步 § 激活提醒。（Cold-Start v3：cron 是通用 sweep，不再在 payload 里带 nudgeIndex，由 gate 计算。）

> ⚠️ pre-send-check 会在请假期间自动返回 `NO_REPLY`，无需 agent 额外判断。
> ⚠️ 假期期间用户主动打卡 → 正常记录，不拦。leave 只影响 cron 提醒。
> ⚠️ 用户提前说"我回来了" → 调用 `leave-manager.py clear`。
> ⚠️ **用户在对话中表达忙碌/无法打卡时**（任何阶段），主动提出暂停提醒，询问暂停多久，然后调用 `leave-manager.py set` 设置请假。详见 `references/recall-messages.md` § 用户主动表达忙碌。

> ⚠️ 你输出的任何文本都会送达用户。`NO_REPLY` 是唯一的抑制方式。
> ⚠️ **当输出包含 `recall` 时，绝对不能写正常的餐食提醒。** 即使 cron prompt 说 "Run notification-composer for breakfast"，你也必须发召回消息。
> ⚠️ **Welcome back 不由 cron 处理。** 用户回归时的欢迎消息由 SKILL-ROUTING.md 全局前置检查在用户发消息时直接触发，不走 cron 路径。

### 第四步：按阶段分支

> **Tips 提醒特殊流程：** 如果 cron message 包含 `for tips`，跳过阶段分支，直接走 § 产品小贴士流程。
> **首餐激活提醒特殊流程：** 如果 cron message 包含 `first_meal_nudge`，跳过阶段分支，直接走 § 首餐激活提醒流程。
> **激活提醒特殊流程：** 如果 cron message 包含 `for activation`（或 `first_meal_nudge` 之外的 `activation`），跳过阶段分支，直接走 § 激活提醒流程。

使用**第三步 `pre-send-check.py` 输出的 stage 值**作为当前 stage（输出形如 `SEND recall stage=N days_silent=X`）。stage 由 lifecycle API 实时计算（DB 唯一真源），不要读 `engagement.json` 的 `notification_stage`（已废弃）。

#### Stage 1 → 正常提醒

组合餐前提醒（§ 餐前提醒）或体重提醒（§ 体重提醒）。compose 完成后执行**第五步**发送。

如果 `days_silent` 为 2（来自第二步），在当天第一个 meal cron 前加一句**温柔提醒（Gentle Nudge）**。见 § 温柔提醒。仅 Day 3（days_silent=2）加 nudge，Day 1-2 正常不加。

#### Stage 2 → 召回（Day 4 和 Day 6）

**仅在午餐时段触发。** 早餐/晚餐 cron 被 pre-send-check 拦截。

根据 `days_silent` 值分两种召回：

**days_silent=3（Day 4）— 情绪+内容召回：**
根据 `references/recall-messages.md` 中的 S2 Day 4 策略规则自行生成。可引用用户数据（上次吃的、streak、季节等）。

**days_silent=5（Day 6）— 询问是否暂停：**
根据 `references/recall-messages.md` 中的 S2 Day 6 策略规则自行生成。给用户选择权，不施压。

**days_silent=4（Day 5）：** pre-send-check 返回 NO_REPLY，不发送。

发送后更新 `recall_topics`（见 § 主题去重机制）。

#### Stage 3 → 每周召回

**频率：** 每周一次（由 `pre-send-check.py` 经 lifecycle API 自动控制间隔与去重）。

**内容类型轮换（按顺序）：**
1. 第1次：专业营养知识（结合节气、食材科学、用户数据）
2. 第2次：功能更新（从 `references/changelog.md` 读取，无更新则改发营养知识或近况）
3. 第3次：近况询问

根据 `references/recall-messages.md` 中对应策略规则自行生成内容。

发送后：将主题摘要写入 `recall_topics`（主题去重用）。

> 召回次数无需 agent 记录——`pre-send-check.py` 已在判定发送时调
> `/recall-sent` 记账（事件溯源）。累计 3 次后 lifecycle API 自动推进到 Stage 4。

#### Stage 4 → 每月召回

**频率：** 每月一次（由 `pre-send-check.py` 经 lifecycle API 自动控制间隔与去重）。

**内容：** 优先从 `references/changelog.md` 取功能更新，无新内容则发近况问候。

发送后：将主题摘要写入 `recall_topics`（主题去重用）。

> 召回次数无需 agent 记录——`pre-send-check.py` 已在判定发送时调
> `/recall-sent` 记账。累计 3 次后 lifecycle API 自动推进到 Stage 5。

#### Stage 5 → 永久沉默

所有 cron 返回 `NO_REPLY`。不再发送任何消息。

用户如果主动回来，仍然 reset 到 Stage 1。

#### 用户回归（阶段重置为 1）

开心迎接，问用户最近吃什么。不问去哪了，不提间隔。如果对话自然流动，再问要不要恢复提醒。

**回归触发：** 用户发送任何消息（不需要打卡），即重置到 Stage 1。

**完整策略 → `references/recall-messages.md` § 用户回归**

**所有召回/回归消息绝不：** 数错过的天数/餐数 · 鸡汤口号 · 连续打卡语言 · 愧疚式措辞 · 正经的系统通知语气 · 脱离食物/营养的纯抽象关心。

### 主题去重机制

所有召回/nudge/回归消息通过 `recall_topics` 去重，确保同一用户不会收到重复角度的消息。AI 不使用固定模板，而是根据策略自行生成内容。

**读取（生成前）：**
```python
recall_topics = engagement_data.get("recall_topics", [])
used_topics = [r["topic"] for r in recall_topics]
# 将 used_topics 传入生成时的 context，告诉 AI 避开这些主题
```

**写入（发送后）：**
```python
recall_topics.append({
    "stage": current_stage,
    "date": today_str,
    "topic": "上次吃的叉烧饭"  # 不超过10字的主题摘要
})
engagement_data["recall_topics"] = recall_topics
```

**清理：** 用户回到 Stage 1 时不清空。超过 20 条时删除最早的 10 条。

### 第五步：输出

compose 完成后，**直接输出最终提醒文本**（announce 自动投递给用户，同时自动注入 main session 上下文）。

不指定 target、不用 message 工具——announce delivery 处理一切。

如果第三步结果是 `NO_REPLY`，直接回复 `NO_REPLY`。

> 🚨 **再次强调输出契约：** 这一轮的全部输出 = 一字不差发给用户的短信。所以**要么只输出那条提醒文本，要么只输出 `NO_REPLY`**——绝不在同一轮里既写正文又写 `NO_REPLY`，绝不夹带 `"Wait…"`/`"Let me finalize"`/`"Stage N, SEND"`/`"Now I'll…"` 之类的叙述，绝不把消息写两遍。第一遍写出来的就当作最终版，不要在输出里改主意。

---

## 餐前提醒

**目的：** 根据上一餐的营养评估提醒用户本餐注意什么，然后发记餐邀请（文字优先，也可拍照）。

**风格：** 像了解你生活的朋友发的消息。温暖、简洁、有对话感。引导方向，不指定菜品。

### 生成流程

#### Step A：组合开场白（连续打卡）— 仅早餐

> ⚠️ **Step A 独立于 Step B/C 的 evaluation 流程。无论 evaluation 是否可用、无论是否降级，Step A 的开场白都必须执行。**
> ⚠️ **仅在当天第一个 meal cron 执行 Step A。** 判断方法：当前 `--meal-type` 是 breakfast / meal_1。如果不是第一餐，跳过整个 Step A，直接进入 Step B。

调用 `{streak-tracker:baseDir}/scripts/streak-calc.py info --data-dir {workspaceDir}/data/meals --workspace-dir {workspaceDir} --tz-offset {tz_offset}`：

- `pending_milestone` 不为 null → **里程碑庆祝**（更大能量，1-2 句，用 🎉）。发送后调用 `streak-calc.py celebrate --milestone <n>`。
- `pending_milestone` 为 null 且 `current_streak >= 2` → **每日连续打卡开场白**：简短一句，展示天数（直接用 `current_streak`，因为此时今天还未记录，streak 反映的就是截至昨天的连续天数）+ 后半句关于越来越了解用户饮食习惯的自由发挥。**不用 🎉，不用"里程碑"、"达成"等庆祝词。** 语气是日常的，不是庆祝的。示例："连续第7天啦～越来越了解你的口味了" / "又是新的一天，第4天打卡开始～"
- `current_streak < 2` → 正常开场白（不提打卡天数）。

#### Step B：读取 evaluation

调用 `{baseDir}/scripts/load-meals.py --data-dir {workspaceDir}/data/meals --tz-offset {tz_offset}` 获取今天的餐食记录。如果是当天第一餐，同时加载昨天的数据（`--date` 昨天）。

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

> ⚠️ **降级只影响消息正文（Step C），不影响 Step A 的开场白。如果 Step A 产生了 streak/milestone 开场白（仅早餐），必须保留并拼接在降级内容前面。**

先调用 `{baseDir}/scripts/meal-history.py --data-dir {workspaceDir}/data/meals --days 30 --meal-type {current_meal} --tz-offset {tz_offset}` 获取 `same_weekday_last_week`。Tier 1 时读取 `health-preferences.md` 过滤过敏/不喜欢的食物。

| 降级层级 | 条件 | 动作 |
|---|---|---|
| Tier 1 | `meal-history` 中**上周同天同餐**有记录 | 以随意询问的口气推荐那天吃的食物（如"中午要不要去吃个麻辣烫"），不提"上周"或具体日期。根据营养数据（`same_weekday_last_week.macros`）附最多一条健康贴士（如控油、加蛋白质、配蔬菜、少盛碳水）。已均衡则纯肯定。 |
| Tier 2 | 无上周同天记录 | 只发记餐邀请（文字优先，也可拍照），不做任何食物引导。 |

**所有路径的消息都以记餐邀请结尾（文字优先，也可拍照）。** 邀请用户随口报一餐就行，照片是补充选项——不要把拍照说成主路径。

**参照物提醒（渐进式，仅对已拍照的用户）：** 发记餐邀请前，检查最近的 meal log（`{workspaceDir}/data/meals/`）中 `has_reference_object` 字段，并读 `{workspaceDir}/data/photo-reference-hints.json`（不存在视为 `{"hint_count": 0, "last_hint_date": null}`）。**仅当用户已经选择拍照时**才给参照物小贴士；文字打卡是完全 OK 的主路径，**不要**因为用户没拍照就劝 ta 改用拍照。

| 条件 | 动作 |
|---|---|
| 最近一次拍照打卡 `has_reference_object: true` | 不提醒 |
| 最近一次是文字打卡（无照片） | 不提醒——文字打卡就很好，不劝 ta 改拍照 |
| 拍照但无参照物，`hint_count == 0` | 轻提："下次拍的时候旁边放双筷子或握个拳头，我估量能更准哦" |
| 拍照但无参照物，`hint_count == 1` | 加重："放个参照物（筷子或握个拳头入镜）我能估得更准，试试看？" |
| `hint_count >= 2` | 不再提醒，尊重用户选择 |

提醒后 `hint_count += 1` 并更新 `last_hint_date`，写回文件。参照物推荐筷子（~24cm）或拳头（通用），根据饮食习惯：中餐→筷子，西餐→叉子（~20cm）或刀（~23cm），拳头通用。不推荐勺子。

**严格模式：** 如果 `habits.active` 中有 `strict: true` 且 `source: "weight-gain-strategy"` 的习惯，**读取 `weight-gain-strategy/references/strict-mode.md` 并遵循其中所有 notification-composer 相关行为**。

> 习惯签到由 `habit-builder` 技能负责（见其 § "How Habits Get Into Conversations"）。本技能提供餐食对话作为载体。**如果有 habit mention，放在消息最末尾单独一行，不要嵌在中间。**

### 温柔提醒（Gentle Nudge）

当 Stage = 1 且 `days_silent == 2` 时（仅 Day 3），在当天第一个 meal cron 的消息前加一句温柔提醒。提醒 + 正常内容在同一条消息内。

规则：
- 仅 Day 3（days_silent=2），Day 1-2 不加。
- 仅当天第一个 meal cron——后续 cron 不重复。
- **去重机制：** 发送 nudge 前，先读 `data/engagement.json > last_nudge_date`。如果等于今天日期，跳过 nudge（只发正常提醒）。发送 nudge 后，写入 `last_nudge_date: "{today}"` 到 `data/engagement.json`。
- 从 `references/recall-messages.md` 的 S1 Nudge 策略规则自行生成（去重，写入 recall_topics）。

**策略 → `references/recall-messages.md` § S1 温柔提醒**

### 激活提醒（Activation）

当 cron message 包含 `activation` 时执行此流程。对象是 handoff 进来、收到欢迎消息但**从未回复**的用户。

> **Cold-Start v3（调度模型）：** cron 不再是 4 条带标签的一次性任务。openclaw-infra 现在只挂**一条周期性的"sweep"cron**（约每 2h 跑一次），payload 是**通用指令**（"跑 activation 前置检查，gate 放行就发当前该发的那一条"）——它**不再告诉你发第几条**。该发哪一条由 `pre-send-check.py` 计算：`index = nudges_sent + 1`，且只在 `now - claimedAt ≥ 该触点阈值`（touch1=4h / touch2=24h / touch3=3d / touch4=7d）**且** `now - last_nudge_at ≥ ~20h`（MIN_GAP，防 sweep 追赶时挤作一堆）时放行。**冷启动注册（COLD，无 PLAN.md）的用户现在也会进这个流程**（v1/v2 时他们不被调度）。

**pre-send-check 已在第三步用 `--meal-type activation` 把过这道关**——决定性判据是 `channel-source.json > lastInboundAt` 存在即取消（用户已回复）；另外未成年（结构化 age<18）/ 已完成引导 / 记过餐 / 请假 / 沉默 / 上限（nudges_sent≥4）/ 当前触点未到阈值 / 被 MIN_GAP 压住 → 都 NO_REPLY。本流程只在返回 `SEND activation ...` 时执行。

**内容由 pre-send-check 算出的 `nudgeIndex` 决定（唯一真源），不要用 `nudges_sent` 计数器自己选文案，也不要去 cron payload 里找 `nudgeIndex=`——payload 现在是通用文本，没有这个字段。**

1. **从第三步 `pre-send-check.py` 的输出行取 `nudgeIndex` 和 `nudgeAngle`。** 输出形如 `SEND activation nudgeIndex=3 nudgeAngle=rapport`。`nudgeIndex`（整数 1–4）是选哪条文案的**唯一依据**；`nudgeAngle`（`value_first` | `photo` | `rapport` | `exit`）是该 index 的语义角度（与下表一致）。**旧的 `(nudge=N)` 和 `(nudgeIndex=N, nudgeAngle=X)` payload token 都已移除——不要再在 cron 指令里找它们。** 若输出不是 `SEND activation ...`（例如 `NO_REPLY`），回 `NO_REPLY`，不发。
2. 读 `USER.md` 的 `Name` 和 `Language`；**冷暖分流：检查 workspace 根有没有 `PLAN.md`**——有 → WARM，从 `PLAN.md` 取**真实每日目标热量+蛋白质**做个性化；没有 → COLD，**绝不报具体数字、绝不提"方案/计划/资料/都准备好了"**，走对应的 COLD 文案。
3. 按 `nudgeIndex` 选对应文案（递减门槛）。四条角度、内容、以及每条的 WARM/COLD 写法详见 `references/recall-messages.md` § 激活提醒：

   | index | angle | 门槛 | 要点 | ask |
   |-------|-------|------|------|-----|
   | 1 | `value_first` | 中 | 复述其每日目标热量+蛋白质，提议"要不要我给你 3 顿简单又能凑够的饭？" | 一个字 YES |
   | 2 | `photo` | 低 | "随口报一餐我来算，免 app、免记账（也可以拍照）"（标签 `photo` 是历史命名，文案现以文字报餐为主） | 一句话报餐（也可拍照） |
   | 3 | `rapport` | 极低 | "现在吃饭这块，你最大的一个难处是啥？一句话就行" | 一行字 |
   | 4 | `exit` | 无 | 体面收尾，把目标数字留给 ta，"随时发我都在" | **不提任何要求** |

   index 4（exit）是**最后一条**；它之后不再有触点（cap=4 + 此条是序列终点）。
4. 把选定文案**本地化**到 `USER.md > Language`，并用 `PLAN.md` 的真实数字（目标热量/蛋白质）个性化。保持 SMS 简短，NanoRhino 用驼峰写法，**不要 🦏 emoji**。
5. **直接输出消息文本**（announce 投递，见第五步）。
6. **发送后，确定性地 +1 计数**——调用脚本（见下方禁令，这是**唯一**允许写 engagement.json 的途径）：
   ```bash
   python3 {notification-manager:baseDir}/scripts/activation-mark-sent.py \
     --workspace-dir {workspaceDir} --counter nudges_sent
   ```
7. **只在确实输出了消息后才调 mark-sent**；判断不该发则回 `NO_REPLY` 且不调脚本。

> 🚫 **本流程严禁手动 Edit/Write `data/engagement.json`，也不要在 activation 路径写 `recall_topics`。** `nudges_sent` 计数与 `last_nudge_at` 时间戳**只能**通过 `activation-mark-sent.py --counter nudges_sent` 写入——该脚本在**同一次** flock + 原子 `os.replace` 里既 +1 计数又盖 `last_nudge_at`（ISO）。`last_nudge_at` 是 pre-send-check MIN_GAP（每 ~20h 最多一条）的真源，绝不能手写、也不能由第二个写入者去碰。本路径里任何对 engagement.json 的自由编辑都会与该脚本竞争、导致本可成功的 nudge run 报 `error`（见 050208 事故）。activation 触点用 pre-send-check 算出的 `nudgeIndex` 选内容，**不需要** recall_topics 去重（去重只用于阶段召回，不用于这条固定序列）。

> ⚠️ `nudges_sent` 满 4 后，pre-send-check 的 cap gate（读 `activation.nudges_sent`）会永久拦截后续 activation nudge——这是终止保证，不依赖 stage 系统。漏调 mark-sent 会导致 nudge 无限循环。**计数必须走脚本。**（stage 真源在 lifecycle DB；activation 计数是非 stage 业务字段，仍存 engagement.json。）

### 首餐激活提醒（First-Meal Nudge）

当 cron message 包含 `first_meal_nudge` 时执行此流程。对象是完成引导但从未记录过任何一餐的用户。

**pre-send-check 已在第三步用 `--meal-type first_meal_nudge` 把过这道关**（未完成引导 / 已记过餐 / 请假 / lifecycle Silent / 上限达到 / touch2 未满 24h → NO_REPLY）。本流程只在 pre-send-check 返回 `SEND` 时执行。

> **Cold-Start v3 Part-2：first-meal nudge 由与 activation 同一个通用 `Activation nudge sweep` cron 驱动**（payload 是通用的，不再携带 `nudge=N`）。pre-send-check 按 `first_meal_nudges_sent` 算出当前该发第几次 touch，并输出 `SEND first_meal_nudge nudgeIndex=N nudgeAngle=X`。**touch 由脚本决定，不要自己猜，也不要从 cron payload 解析 `nudge=N`。**

1. **从 pre-send-check 的输出读取 `nudgeIndex`**（`SEND first_meal_nudge nudgeIndex=N nudgeAngle=X`）：`nudgeIndex=1`（angle=day1）用 day-1 语气，`nudgeIndex=2`（angle=followup）用更软的跟进语气。
2. 读 `data/engagement.json > recall_topics`，避开已用过的角度/例子。
3. 按 `references/recall-messages.md` § 首餐激活提醒 的策略生成消息。**示例本地化**：按 `USER.md > Language` 选当地早餐/常见餐，不要照搬英文 "oatmeal and coffee"。1-2 句。
4. **直接输出消息文本**（announce 投递，见第五步）。
5. **发送后，确定性地 +1 计数**——**不要手写 read-modify-write engagement.json**。调用脚本：
   ```bash
   python3 {notification-manager:baseDir}/scripts/activation-mark-sent.py \
     --workspace-dir {workspaceDir} --counter first_meal_nudges_sent
   ```
   该脚本原子地把 `activation.first_meal_nudges_sent` +1（无 `activation` 块则新建，不动其它字段）。
6. 同时追加一条 `recall_topics`（主题摘要 ≤10 字，去重用，这一步仍是 read-modify-write）。
7. **只在确实输出了消息后才调 mark-sent**；若判断不该发，回 `NO_REPLY` 且不调脚本。

> ⚠️ 计数满 2 后，pre-send-check 的 cap gate（读 `activation.first_meal_nudges_sent`）永久拦截后续 first-meal nudge——这是终止保证，不依赖 stage 系统。漏调 mark-sent 会导致 nudge 无限循环。**计数必须走脚本——不要让模型手算/手写 JSON。**（stage 真源在 lifecycle DB；activation 计数是非 stage 业务字段，仍存 engagement.json。）

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
- `weight_morning_followup`：与主提醒同风格。

永不在提醒中展示目标体重或上次称重数据。

---

## 每周低热量检查

每周一次（周一，第一餐提醒时），运行 `{baseDir}/scripts/weekly-low-cal-check.py`。如果 `below_floor` 为 true，在下一条餐前提醒中加入温和提示。如果 `Health Flags` 包含 `history_of_ed`，完全跳过。用语见 `diet-tracking-analysis` SKILL.md。

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
- 餐食/推荐：`{baseDir}/scripts/meal-history.py`
- 连续打卡：`{streak-tracker:baseDir}/scripts/streak-calc.py`
- 互动阶段（stage）：lifecycle API（DB 唯一真源）。读取方式 = 直接用每轮注入的 `## User Lifecycle` 段，或 `pre-send-check.py` 输出的 `stage=N`。不再用 `check-stage.py`（已废弃）。

---

## 技能路由

**优先级 P4（报告层）。** 完整冲突解决见 `SKILL-ROUTING.md`。

---

## 性能

- 餐前提醒消息：≤ 80 字（中文）/ 40 词（英文），不含结尾记餐邀请
- 回复处理：最多 2 轮（提醒 → 回复 → 响应 → 结束）

---

## ⚠️ engagement.json 写入规则

> **stage 已迁 lifecycle API（DB 唯一真源）。** `engagement.json` 不再存
> `notification_stage` / `stage_changed_at`（已废弃，勿读勿写）。本文件现在只
> 存非 stage 业务字段（`recall_topics` / `holiday_asked` / `last_nudge_date` 等）。

**所有对 `data/engagement.json` 的写入必须使用 read-modify-write 模式：**

1. 先读取当前文件内容
2. 仅修改需要更新的字段
3. 写回完整对象

**绝不整体覆盖。** 多个流程会更新此文件的不同字段（如 `recall_topics`、`last_nudge_date`）。如果 agent 用缓存的旧数据整体写回，会覆盖其他流程的更新。

---

## § 产品小贴士流程

当 cron message 包含 `for tips` 时执行此流程。

### 步骤

1. 读取 `health-profile.md` 中的 `Onboarding Completed` 日期
2. 运行前置检查：
```bash
python3 {baseDir}/scripts/tips-check.py \
  --data-dir {workspaceDir}/data \
  --tz-offset {tz_offset} \
  --onboarding-date <YYYY-MM-DD>
```
3. 输出处理：
   - **`NO_REPLY`** → 回复 `NO_REPLY`，结束
   - **`SEND tip_id=N topic=...`** + **`PROMPT: ...`** → 按 PROMPT 内容，结合用户的实际使用情况生成个性化消息。**不需要去读 tip-topics.json，PROMPT 已经包含了所有指引。**

4. **标记已发送**：生成并发送 tip 消息后，调用 mark-sent 脚本（确保发送失败不会跳过 tip）：
```bash
python3 {baseDir}/scripts/tips-mark-sent.py \
  --data-dir {workspaceDir}/data \
  --tip-id <N> \
  --date <YYYY-MM-DD>
```

5. **记录上下文**：把消息内容写入 `{workspaceDir}/data/last-tip.md`（覆盖写入），格式：
```
# Last Tip Sent
Date: {当前日期}
Tip ID: {N}
Topic: {topic}

{你生成的完整 tip 消息}
```
这样用户在主对话中回复时，agent 能读到最近发了什么 tip。

### 生成规则

- **定位**：不是功能介绍，是回访 — 用了一段时间了，想了解使用感受，引导用户按自己的偏好调整
- **核心意识**：每条 tip 通过展示一个用户不知道能做的事情，让用户自己产生"原来还可以这样用"的感觉。不要直白说教（不要说"我不只是打卡提醒"之类）
- **语气**：回访关怀，自然引导，不是说明书
- **自称**：用"我"，不要自称"小犀牛"
- **语言自然**：说人话，检查主语和语法通顺。不要出现"用你两周了"这种病句
- **长度**：分点说清楚，用 emoji 分隔，易读
- **个性化**：结合用户的饮食记录、当前设置、使用习惯来说
- **已知功能跳过**：如果根据对话历史判断用户已经熟悉该功能，回复 `NO_REPLY`
- **不重复**：每条 tip 的内容和举例不要和之前发过的 tip 重复。不要反复用同一个场景（如"逛超市"）或同一个句式（如"不只是XX，其他也可以找我"）
- **用户回复要响应**：如果用户看到 tip 后想调整（比如改提醒时间、改语气），正常处理

### 关闭小贴士

用户说"别发了"/"不要再发小贴士"时：
```bash
python3 {baseDir}/scripts/tips-optout.py --data-dir {workspaceDir}/data
```

---

## § 每周个性化洞察

当 cron message 包含 `for weekly-insight` 时执行此流程。这是 tips 1-7 全部发完后的长期周期性内容，每周四一次。

### 步骤

1. 读取 `health-profile.md` 中的 `Onboarding Completed` 日期
2. 运行前置检查：
```bash
python3 {baseDir}/scripts/weekly-insight-check.py \
  --data-dir {workspaceDir}/data \
  --tz-offset {tz_offset} \
  --onboarding-date <YYYY-MM-DD>
```
3. 输出处理：
   - **`NO_REPLY`** → 回复 `NO_REPLY`，结束
   - **`SEND`** → 结合用户最近一周的餐食记录和对话，生成一条个性化洞察
4. **标记已发送**：生成并发送洞察后，调用：
```bash
python3 {baseDir}/scripts/weekly-insight-mark-sent.py \
  --data-dir {workspaceDir}/data \
  --date <YYYY-MM-DD>
```

### 生成规则

- **内容方向**：可以是饮食趋势观察、营养建议、习惯改进点、鼓励、或者有趣的发现
- **数据来源**：读最近 7 天的 `data/meals/` 餐食记录 + 对话上下文
- **语气**：像一个了解你的朋友顺手提一句，不是报告
- **长度**：3-5 句话
- **不重复**：每周的洞察要有新内容，不要和周报重复
