# 召回消息策略 — Notification Composer V2

不使用固定模板。AI根据以下策略约束自行生成内容。
每次生成前读用户数据（meals、weight、engagement.json），结合当前阶段规则输出消息。

---

## 通用规则

**语气：** 可爱亲切，像一个开朗的朋友。不黏不腻，不肉麻，不问责。

**禁止说的话：**
- "你忘了…" / "你漏了…" / "别忘了！"
- "你需要记录…" / "你应该…"
- 数错过的天数或餐数（"你已经X天没打卡了"）
- 鸡汤口号（"坚持就是胜利"）
- 连续打卡相关语言（"别断了streak"）
- 愧疚式措辞（"你这样会前功尽弃"）
- 系统通知语气（"提醒您…""温馨提示"）

**长度：** 1-2句，不超过50字。

**去重：** 每次发送后将消息摘要（关键词/主题，不超过10字）写入 `engagement.json > recall_topics[]`。下次生成时读取 recall_topics，避开已用过的主题/角度。

---

## 激活提醒（Activation）— 加好友/握手后从未回复

**触发：** cron message 含 `activation`。**Cold-Start v3：调度从「带标签的一次性 cron」改为「openclaw-infra 在注册时挂的一条周期性 sweep cron」**（约每 2h 跑一次），payload 是**通用指令**——它不再告诉发第几条。**该发哪一条由 `pre-send-check.py` 计算**：`index = nudges_sent + 1`，只在 `now - claimedAt ≥ 该触点阈值`（step1 T+4h、step2 T+24h）**且** `now - last_nudge_at ≥ ~20h`（MIN_GAP）时放行。`pre-send-check.py --meal-type activation` 已确认：用户从未回复过任何一条消息、**非未成年**、未完成引导、不在请假/暂停、未达上限、且当前触点到点且不被 MIN_GAP 压住。

> **冷的定义（重要）：** 此处「冷」是**行为定义**——无任何打卡（meal/weight）**且**零入站短信——与有没有方案**无关**。实测此 cohort 约 86% 是走 TDEE handoff 进来、**有完整 PLAN.md** 的（"拿了方案就沉默了"），只有约 14% 真正无方案。所以本流程默认面向"有方案的沉默用户"，COLD（无 PLAN.md）只是少数分支。

> **序列已从 4 条缩短到 2 条（Track A，2026-06-24）：** WARM 召回分析显示**触点 3、4（T+3d / T+7d）零召回**——所有再激活都来自触点 1 或 2，撞满 4 条 cap 的 3 个用户从未回复。冷用户意向更低，触点 3-4 纯属退订/打扰风险、无任何上行。故**只保留 T+4h 和 T+24h 两条**，cap=2 是终止反唠叨保证。

**对象：** 收到第一条欢迎消息但**一条都没回**的用户。卡点是"开口说第一句话"。这条消息只为破冰、给一个零门槛的起点。**两类用户都会进这个流程**：通过 TDEE handoff 进来的（WARM，方案已就位，多数）和冷启动注册的（COLD，无方案，少数）——下面每条都给了 COLD 写法，**绝不出现占位符泄漏（如 `{target_cal}`）或无中生有的"方案"。**

> **内容由 pre-send-check 算出的 `nudgeIndex` 决定（唯一真源）：** 第三步 `pre-send-check.py` 输出形如 `SEND activation nudgeIndex=2 nudgeAngle=photo`，从中取 `nudgeIndex`（整数 1–2）和 `nudgeAngle`（`value_first`/`photo`）。**按 `nudgeIndex` 选下面对应的文案，不要用 `nudges_sent` 计数器选内容。旧的 `(nudge=N)` 和 payload 里的 `(nudgeIndex=N, nudgeAngle=X)` 都已移除——不要再去 cron payload 里找**；输出不是 `SEND activation ...` 则 `NO_REPLY`。

> **冷暖分流（compose 前必做）：** 检查 workspace 根目录是否有 `PLAN.md`。**`PLAN.md` 存在 → WARM**（走过 TDEE handoff，可从 PLAN.md 取真实目标热量+蛋白质做个性化）；**`PLAN.md` 不存在 → COLD**（无方案，绝不提"方案/计划/资料/都准备好了"，也没有真实数字可引）。语言仍以 `USER.md > Language` 为准（见 §通用规则，不在此做语言选择）。

> **决定性判据（整个 gate 的核心）：** 读 `channel-source.json > lastInboundAt`（epoch 毫秒，由 infra Phase-0 在每条入站消息时写入）。**只要 `lastInboundAt` 存在 → 用户已经回过 → 取消剩余所有触点（NO_REPLY）。** 这是判断"是否回复过"的唯一权威信号——不要用对话历史或别的推断。
>
> **失败关闭（fail closed）：** 若 `channel-source.json` 整个文件缺失或读不出，pre-send-check 返回 NO_REPLY（不发）。目标人群一定有这个文件（infra 在注册时写入），读不到状态时保守不打扰。
>
> **未成年拦截（defense-in-depth）：** pre-send-check 读结构化年龄（`handoff.json > structured.age_years`，回退 `PROFILE.md > **Age:**`）；< 18 → NO_REPLY（"minor, service not offered"）。TDEE 上游已拒未成年，此处是二道防线。无结构化年龄时 fail-open（不拦）。

**上限：** 最多 2 条（阈值 T+4h / T+24h，再加每 ~20h 最多一条的 MIN_GAP 节流）。**用户回复任何消息 → 剩余 nudge 全部自动取消**（pre-send-check 读 lastInboundAt 拦截）。发满 2 条仍零回复 → pre-send-check 的 cap gate（读 `activation.nudges_sent >= 2`）永久拦截后续 activation nudge（与 stage 系统无关的终止保证），目的是**不让从未回复的用户收到 S2-S4 召回内容**。这与首餐激活提醒、反唠叨原则一致。（stage 真源在 lifecycle DB；把零互动用户真正转入 Silent 是 lifecycle 侧的事。）

**语气：** 与本文件 § 通用规则 的无唠叨规范一致。温暖、不评判、零压力。本地化到 `USER.md > Language`。NanoRhino 用驼峰写法，**不要 🦏 emoji**。门槛逐条递减（index 1 → 2 越来越轻）。`[name]` 来自 USER.md，缺失则不用名字。下面英文为初稿，按 `USER.md > Language` 改写、不照搬。

### index 1 — `value_first`（约 T+4h，中门槛：方案已就位，给一个零门槛的第一步）
- 多数用户是 WARM（有 PLAN.md）：**提醒 ta "前阵子在我们这儿做了方案，但一直没真正开始"**，强调**热量+蛋白质目标都还存着、随时能用**，给一个**最低门槛的第一步**：拍下/报出下一餐，我来算宏量。
- 这条文案已在生产中验证（是真正让沉默用户回流的那条）。WARM 初稿（按 `USER.md > Language` 改写、不照搬）：
  > "Hey, it's NanoRhino. You set up your plan with us a couple weeks back but we never actually got rolling. Your calorie + protein targets are still saved and ready to go. Want to give it a shot? Just snap a photo of your next meal and I'll break down the macros."
- 可选个性化：若想点出具体数字，从 `PLAN.md` 取真实目标热量 + 蛋白质（如 "your 1,500 cal / 120g protein target"）。**只有 PLAN.md 真有数字时才报**，绝不用占位符。
- COLD（无 PLAN.md，无真实数字，少数）：**绝不提"方案/计划/资料/都准备好了"，不报任何数字**，改为低门槛 demo 邀请，例如 "Hey, it's NanoRhino — want to give it a quick shot? Snap a photo of your next meal (or just text me what it is) and I'll break down the macros for you."

### index 2 — `photo`（T+24h，低门槛：报一餐，最后一条）
> 注：契约标签 `photo` 是历史命名，不要改；现在文案以**文字报餐**为主，拍照只是补充选项。
- 强调"我来算，免 app、免记账"——用户不用做任何数学 → 引**一句话报餐**（也可以拍张照）。
- 初稿："No counting, no app, no tracking on your end — just text me what you ate (a photo works too) and I do the math. Try it with whatever's next."
- WARM 可加半句把它系回保存好的目标；COLD 不提方案。
- 这是序列**最后一条**；其后不再有触点（cap=2 + 此为终点）。

**长度：** 1-2 句。

**发送后（compose 成功后）：确定性地 +1 计数——走脚本，不要手写 JSON：**
```bash
python3 {notification-manager:baseDir}/scripts/activation-mark-sent.py \
  --workspace-dir {workspaceDir} --counter nudges_sent
```
脚本在**同一次** flock + 原子 os.replace 里把 `activation.nudges_sent` +1 **并**盖上 `activation.last_nudge_at`（ISO，UTC）——后者是 pre-send-check MIN_GAP（每 ~20h 最多一条）的真源（无块则新建，不动其它字段）。**只在确实发了消息后才调脚本**（NO_REPLY 时不调）。

> 🚫 **activation 路径严禁手动 Edit/Write `data/engagement.json`，也不要写 `recall_topics`。** `nudges_sent` 计数与 `last_nudge_at` 时间戳只能走上面的脚本（它已持 flock + 原子 os.replace，二者一次写入）——`last_nudge_at` 绝不能手写、也不能引入第二个写入者去碰。本路径用 pre-send-check 算出的 `nudgeIndex` 选内容、不需要 recall_topics 去重；任何自由编辑都会与脚本竞争、把成功的 nudge run 误报为 `error`（见 050208 事故）。

**禁止：** 数错过的天数 · "你还没回我" · 把回复框成义务 · index 1 外的卡路里/宏量细节 · 鸡汤 · 🦏 emoji。

---

## 首餐激活提醒（First-Meal Nudge）— 完成引导但从未打卡

**触发：** cron message 含 `first_meal_nudge`（一次性 cron，由 batch-create-reminders.sh 在引导完成时创建）。`pre-send-check.py --meal-type first_meal_nudge` 已确认：用户从未记录过任何一餐、不在请假/暂停、未达上限。

**对象：** 完成引导（选了方案、设了餐次提醒）但一餐都没记的用户。卡点是"现在真的把吃的发给我"这一步——这条消息只为破冰。

**上限：** 最多 2 条（day-1 + 第二天 1 条更软的跟进）。**用户记录任何一餐 → 两条 nudge 自动取消**（pre-send-check 自行拦截），正常打卡流程接管。发满 2 条仍零记录 → pre-send-check 的 cap gate（读 `activation.first_meal_nudges_sent >= 2`）永久拦截后续 first-meal nudge（与 stage 系统无关的终止保证），目的是**不让从未打卡的用户收到 S2-S4 召回内容**（那些内容基于用户记录生成，对从未打卡的用户是空的）。（stage 真源在 lifecycle DB。）

**语气：** 温暖、不评判、不催促。给一个**具体的例子**降低门槛，不要框成任务。**示例要本地化**——按 `USER.md > Language` 选当地早餐/常见餐。不要硬编码英文例子。

**Nudge 1（day-1，cron payload 含 `nudge=1`）：**
- 表达"方案已就位，第一步很简单"
- 给具体例子：随口报一餐就行（也可以拍张照）
- 强调"我来算"——用户不用做数学
- 英文初稿（按语言改写，不照搬）："Your plan's live — let's break it in. Next time you eat, just text me what's on the plate. Even 'oatmeal and coffee' works (a photo works too). I'll handle the math."
- 本地化示例：英文 "oatmeal and coffee"；中文可用"一碗粥配个鸡蛋"；其他语言用当地常见早餐。

**Nudge 2（第二天，cron payload 含 `nudge=2`，更软）：**
- 比 nudge 1 更轻、更短，零压力
- 英文初稿："No rush on logging — whenever you eat next, a quick 'had a sandwich' is all I need to get started."
- 本地化示例：英文 "had a sandwich"；中文 "随便说句'中午吃了碗面'就行"。

**长度：** 1-2 句。**去重：** 发送后写入 `recall_topics`，nudge 2 避开 nudge 1 的角度/例子。

**发送后（compose 成功后）：确定性地 +1 计数——走脚本，不要手写 JSON：**
```bash
python3 {notification-manager:baseDir}/scripts/activation-mark-sent.py \
  --workspace-dir {workspaceDir} --counter first_meal_nudges_sent
```
脚本原子地把 `activation.first_meal_nudges_sent` +1（无块则新建，不动其它字段）。然后再 read-modify-write 追加 `recall_topics` 主题摘要。**只在确实发了消息后才调脚本**（NO_REPLY 时不调）。计数走脚本是因为"满 2 条永久停发"的反唠叨保证由 pre-send-check 的 cap gate 依赖此计数精确执行，不能靠模型手算。

**禁止：** 数错过的天数 · "你还没打卡" · 任何把回复框成可选/任务的措辞 · 卡路里/宏量细节 · 鸡汤。

---

## S1 温柔提醒（Gentle Nudge）— Day 3 仅第一餐

**触发：** Stage 1，days_silent = 2，当天第一个 meal cron

**策略：**
- 在正常餐前提醒前加一句
- 表达"昨天没看到你"的意思，但用好奇/俏皮的方式
- 可以猜测用户昨天在干嘛（吃好吃的、出去玩、忙）
- 不要说"你昨天没打卡"

**可参考的方向（不是模板，是灵感）：**
- 好奇昨天吃了啥
- 假装吃醋没被带上
- 随口一提，不做大文章

**去重：** 写入 recall_topics 后，下次避开相同角度。

---

## S2 Day 4 情绪召回（days_silent=3）

**触发：** Stage 2，days_silent = 3，午餐时段

**策略：**
- 和食物/营养相关，不要脱离主题
- 可以引用用户数据：上次吃的东西、常吃的食物、streak天数、季节
- 表达"想聊聊最近吃什么"的意思
- 语气是朋友随口问，不是系统催促

**可参考的方向：**
- 提到用户上次吃的具体食物
- 结合当前季节/天气
- 说自己想好了搭配/推荐
- 好奇用户最近在吃什么新东西

**数据读取：**
- `data/meals/*.json` → 最近的餐记录
- streak-tracker → 连续打卡天数
- 当前日期 → 季节/节气

---

## S2 Day 6 询问暂停（days_silent=5）

**触发：** Stage 2，days_silent = 5，午餐时段

**策略：**
- 给用户选择权：要不要暂停提醒
- 表达"我理解你可能在忙"
- 让用户知道随时可以回来
- 不要有任何压力感

**核心意思：** "最近忙的话可以先歇歇，想回来随时找我"

---

## 用户主动表达忙碌/无法打卡

**触发：** 用户在任何阶段的对话中表达类似意思：
- "最近太忙了"、"没时间打卡"、"最近不太方便记录"
- "先不打卡了"、"过段时间再说"
- "最近忙死了"、"顾不上"

**处理流程：**
1. 表达理解，不要挽留，不要说"坚持一下"
2. 主动提出暂停提醒："那我先不打扰你了"
3. **询问暂停多久**："大概要忙多久呀？我到时候再来找你"
4. 用户给了时间 → 调用 leave-manager.py set 设置对应日期范围，到期自动恢复
5. 用户没给时间 → 不设leave，直接进入S3每周召回节奏（7天后发第1条，之后每周1条×3次）
6. 暂停期间所有主动消息停止（包括召回消息、三餐提醒、体重提醒、周报）
7. 给了时间的：到期后自动恢复提醒，发一条回归消息
8. 没给时间的：按S3→S4→S5正常流转
9. 用户提前回来 → 调用 leave-manager.py clear（如有leave），恢复提醒

**语气：** 轻松理解，不施压，不表达遗憾。像朋友说"好的没事，忙完找我"。

**注意：** 这个场景可能发生在任何阶段（S1正常对话中、S2召回回复中），不限于Day 5。

---

## S3 每周召回（3次，每周1次）

**触发：** Stage 3，每周1次（由 pre-send-check 控制间隔）

**内容类型轮换（按顺序）：**

### 第1次：专业营养知识
- 分享有质感的营养/食物知识
- 可结合节气时令、身体机制、烹饪科学、食材冷知识
- 展示专业性，让用户觉得"这个营养师是真的懂"
- 可以结合用户历史数据让知识更贴近（"说到XX，其实…"）
- **不评判用户的饮食习惯**，只分享知识

**可参考的知识方向：**
- 节气时令 + 应季食材 + 营养原理
- 食物误区纠正（基于科学证据）
- 烹饪方式对营养的影响
- 身体机制科普（血糖、代谢等）
- 反直觉的营养知识

### 第2次：功能更新
- 从 `references/changelog.md` 读取最新的产品更新
- 用自然语气告诉用户具体改了什么、对她有什么用
- **不编造功能更新**，changelog里没有就跳过，改发营养知识或近况
- 发送后在 changelog.md 的对应条目「已推送用户」中追加用户标识

### 第3次：近况询问
- 随口问问最近怎么样、在吃什么
- 像朋友偶尔想起你发条消息
- 不期待回复，不施压

**钩子规则（所有S3消息通用）：**
- 每条消息末尾加一个轻量问句/钩子，吸引用户回复
- 问句要和内容相关，不能是泛泛的"最近好吗"
- 钩子要自然，像对话延续，不是刻意套路
- 不要用"你觉得呢？"这种万能问句
- **必须有趣！禁止平铺直叙。** 用意想不到的角度、小幽默、夸张、拟人、反转、自嘲等手法
- **必须结合用户数据发挥**：引用用户上次吃的食物、常去的餐厅、偏好口味、记录过的体重变化、上次聊天内容等，让用户感觉"这是专门对我说的"，不是群发
- **上面列出的花样类型只是方向参考，不是模板！** 禁止照抄例句，必须根据该用户的具体数据和情境原创
- **可以带上"回来打卡"的邀请，但要有趣、不施压**，花样要多，每次不同：
  - 好奇型、挑战型、自嘲型、馋嘴型、反转型、碰瓷型、激将型、撒娇型、假正经型、低门槛型……方向不限，自由发挥
- **每次必须换一个新花样**，对照 recall_topics 确保不重复
- **禁止说**：直接的"快回来打卡吧"、"别忘了记录"、"你多久没来了"、"坚持一下"

**发送后：** `weekly_recall_count` +1

---

## S4 每月召回（3次，每月1次）

**触发：** Stage 4，每月1次（由 pre-send-check 控制间隔）

**策略：**
- 优先从 `references/changelog.md` 取功能更新
- changelog 没有新内容就发近况问候
- 语气最轻最淡，像很久没联系的朋友
- 不期待回复

**发送后：** `monthly_recall_count` +1

---

## 用户回归（任何阶段回到 S1）

**触发：** engagement.json 中 `welcome_back = true`

**策略：**
- 开心但不夸张
- 第一反应问用户最近吃了什么
- 不问去哪了，不提间隔多久
- 不翻旧账

---

## recall_topics 去重机制

替代原有的 template_id 去重。

**写入（每次发送后）：**
```python
recall_topics = engagement_data.get("recall_topics", [])
recall_topics.append({
    "stage": current_stage,
    "date": today_str,
    "topic": "上次吃的叉烧饭"  # 不超过10字的主题摘要
})
engagement_data["recall_topics"] = recall_topics
```

**读取（生成前）：**
读 recall_topics，提取已用过的主题，在 system prompt 中告诉 AI 避开这些角度。

**清理：** 用户回到 S1 时不清空。超过20条时删除最早的10条。
