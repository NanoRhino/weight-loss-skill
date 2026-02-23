# Weight Loss Skills 体系规划大纲

> 目标：为美国本土用户提供个性化减肥服务，通过多个 Skill 协作，以对话形式收集用户信息、生成方案、跟踪反馈、持续优化。

---

## 整体架构

```
用户入口
  │
  ▼
┌─────────────────────────────┐
│  Skill 1: Onboarding &      │  ◄── 所有用户的第一个 Skill
│  Assessment (入职评估)        │      收集基础信息，生成用户画像
└──────────────┬──────────────┘
               │ 用户画像 + 目标
               ▼
┌─────────────────────────────┐
│  Skill 2: Goal Setting &     │  ◄── 制定个性化减肥目标和总体策略
│  Planning (目标规划)          │      输出可执行的阶段计划
└──────────────┬──────────────┘
               │ 分发到各执行 Skill
               ▼
┌──────────────────────────────────────────────────────┐
│                   核心执行层 Skills                     │
│                                                        │
│  Skill 3: Nutrition &    Skill 4: Exercise &           │
│  Meal Planning           Fitness Planning              │
│  (营养与膳食规划)          (运动与健身规划)                │
│                                                        │
│  Skill 5: Calorie &      Skill 6: Habit Building       │
│  Food Tracking           & Behavioral Coaching         │
│  (热量与饮食追踪)          (习惯养成与行为教练)            │
└──────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│                   支撑增强层 Skills                     │
│                                                        │
│  Skill 7: Progress       Skill 8: Motivational        │
│  Tracking & Analytics    Coaching & Accountability     │
│  (进度追踪与数据分析)      (激励教练与问责陪伴)            │
│                                                        │
│  Skill 9: Sleep &        Skill 10: Grocery &           │
│  Recovery                Meal Prep                     │
│  (睡眠与恢复管理)          (采购与备餐指导)               │
│                                                        │
│  Skill 11: Nutrition     Skill 12: Emotional Eating    │
│  Education               & Mindfulness                 │
│  (营养知识教育)            (情绪饮食与正念)               │
└──────────────────────────────────────────────────────┘
```

---

## Skill 1: Onboarding & Assessment（入职评估）

**定位**：所有用户的入口，通过对话收集完整的用户画像。

**对话需收集的信息**：
- 基础人口统计：年龄、性别、身高、当前体重
- 健康状况：已知疾病、用药情况、过敏史、医生建议的饮食限制
- 生活方式：职业类型（久坐/活动量）、每日作息、烹饪能力、外食频率
- 饮食偏好：素食/杂食、文化饮食习惯、忌口食物、喜欢的菜系
- 运动基础：当前运动频率、运动类型、健身房/家庭锻炼、运动伤病史
- 心理状态：减肥动机、过去减肥经历、对体重的情绪关系
- 目标期望：目标体重、期望达成时间、最关注的改变领域

**输出**：
- 用户画像文件（User Profile）
- BMR（基础代谢率）和 TDEE（每日总能量消耗）计算
- 推荐每日热量目标
- 推荐激活的 Skill 列表（不是所有用户都需要所有 Skill）

**美国本土化要点**：
- 使用英制单位（lbs, feet/inches）同时支持公制
- 参考 FDA 和 USDA 饮食指南
- 考虑美国常见饮食文化（fast food 频率、portion size 偏大等）

---

## Skill 2: Goal Setting & Planning（目标规划）

**定位**：将评估结果转化为具体、可执行的阶段性减肥计划。

**对话流程**：
- 基于 Skill 1 数据，提出推荐目标（每周减 1-2 lbs 为健康速率）
- 与用户讨论并校准期望（纠正不切实际的目标）
- 设定里程碑（每 4 周一个 checkpoint）
- 制定总体策略：饮食调整为主 vs 运动增加为主 vs 综合方案
- 识别潜在障碍并制定应对方案

**输出**：
- 阶段性目标计划（Phase Plan）
- 每周热量预算
- 推荐的 Skill 使用节奏（如：每天用 Skill 5 追踪饮食，每周用 Skill 7 看报告）
- 可调整的里程碑时间表

**关键机制**：
- 每 4 周自动触发计划回顾与调整
- 根据实际进度动态修正目标

---

## Skill 3: Nutrition & Meal Planning（营养与膳食规划）

**定位**：根据用户的热量目标、口味偏好、生活方式生成个性化膳食方案。

**对话需收集的信息**：
- 每日餐数偏好（3 餐 vs 少食多餐 vs 间歇性断食）
- 烹饪时间预算（每天愿意花多少时间做饭）
- 预算范围（每周食品花费）
- 特殊饮食模式偏好（Keto, Mediterranean, Low-carb, Plant-based 等）
- 对 meal prep 的接受度

**功能**：
- 生成每周膳食计划（含早/中/晚/零食）
- 每个菜品附带：食材清单、简要做法、营养成分（Calories/Protein/Carbs/Fat）
- 提供替代选项（不喜欢某道菜可以换）
- 外食场景建议（常见美国餐厅如 Chipotle, Chick-fil-A 的健康点单方案）
- 节日/聚会饮食策略（Thanksgiving, Super Bowl party 等）

**美国本土化要点**：
- 参考 USDA MyPlate 指南
- 食材基于美国超市常见品（Walmart, Costco, Trader Joe's 等）
- 营养数据参考 USDA FoodData Central 数据库
- 考虑美国区域饮食差异（Southern food, Tex-Mex, East Coast 等）

---

## Skill 4: Exercise & Fitness Planning（运动与健身规划）

**定位**：根据用户体能水平和偏好，制定循序渐进的运动方案。

**对话需收集的信息**：
- 当前体能水平（完全不运动 / 偶尔运动 / 规律运动）
- 可用设备和场地（健身房会员 / 家庭锻炼 / 户外）
- 每周可运动时间和频率
- 运动偏好（力量 / 有氧 / 瑜伽 / 游泳等）
- 身体限制或伤病

**功能**：
- 生成每周运动计划（含具体动作、组数、次数/时长）
- 力量训练：渐进式超负荷规划
- 有氧训练：心率区间指导（Fat Burn Zone vs Cardio Zone）
- 提供动作替代方案（gym 版本 vs home 版本）
- 运动前热身和运动后拉伸指导
- 休息日安排和恢复建议

**方案调整机制**：
- 根据用户反馈调整强度（太难/太简单）
- 每 2-4 周渐进调整训练计划
- 遇到平台期的突破策略

---

## Skill 5: Calorie & Food Tracking（热量与饮食追踪）

**定位**：日常饮食记录工具，帮助用户量化每日摄入。

**核心交互模式**：
- 用户用自然语言描述吃了什么（如 "I had a chicken burrito from Chipotle for lunch"）
- AI 解析食物并估算热量和宏量营养素
- 支持批量录入和快速记录

**功能**：
- 自然语言食物识别和热量估算
- 每日摄入汇总（总热量、蛋白质、碳水、脂肪）
- 与每日目标对比（剩余热量预算提示）
- 水分摄入追踪
- 识别饮食模式和问题（如：蛋白质持续偏低、晚间零食过多）
- 常用食物记忆（快速重复记录）

**数据参考**：
- USDA FoodData Central
- 美国连锁餐厅公开营养数据（McDonald's, Starbucks, Subway 等）
- 常见包装食品营养标签数据

---

## Skill 6: Habit Building & Behavioral Coaching（习惯养成与行为教练）

**定位**：减肥的核心在于行为改变。此 Skill 聚焦建立可持续的健康习惯。

**对话需收集的信息**：
- 当前日常习惯盘点（饮食、运动、睡眠、压力管理）
- 识别需要改变的关键习惯（如：夜间零食、含糖饮料、久坐不动）
- 用户认为最难改变的习惯
- 过去尝试改变习惯的经验

**功能**：
- 基于行为科学设计习惯养成计划（Habit Stacking, Implementation Intentions）
- 每次聚焦 1-2 个新习惯（避免同时改变太多）
- 每日习惯打卡和检查
- 21 天/66 天习惯追踪
- 应对"破戒"的策略（不是失败，是学习机会）
- 环境设计建议（如：不在家存零食、把运动鞋放门口）

**行为科学框架**：
- Cue-Routine-Reward 循环识别与改造
- Tiny Habits（BJ Fogg 方法论）
- Temptation Bundling
- If-Then Planning

---

## Skill 7: Progress Tracking & Analytics（进度追踪与数据分析）

**定位**：数据驱动的进度监控，让用户看到趋势而非日常波动。

**追踪维度**：
- 体重（每日/每周，含趋势线和移动平均）
- 身体围度（腰围、臀围、胸围等 — 体重不变但围度减小也是进步）
- 体脂率（如用户有设备测量）
- 运动表现指标（如跑步距离、举重重量的进步）
- 习惯完成率

**功能**：
- 每周进度报告生成
- 每月深度分析报告
- 平台期检测和预警（体重连续 2+ 周无变化）
- 趋势可视化（ASCII charts 或推荐外部工具）
- 非体重胜利识别（Non-Scale Victories: 衣服更合身、精力更好、睡眠改善等）

**智能分析**：
- 将饮食/运动数据与体重变化关联分析
- 识别哪些行为对减肥效果最显著
- 提供数据驱动的调整建议

---

## Skill 8: Motivational Coaching & Accountability（激励教练与问责陪伴）

**定位**：减肥是长期过程，陪伴和激励是坚持的关键。

**功能**：
- 每日签到对话（How are you feeling today?）
- 根据用户状态提供情境化激励（不是空洞的鸡汤）
- 庆祝里程碑达成（每减 5 lbs, 连续打卡 7 天等）
- 低谷期支持（体重反弹、破戒、情绪低落时的应对）
- Weekly reflection 引导（本周什么做得好？什么需要改进？）

**问责机制**：
- 温和提醒未完成的每日任务
- "不评判"原则 — 错过一天不等于失败
- 帮助用户分析偏离计划的原因并制定预防措施
- 设定 mini rewards 系统（每达成一个小目标可以奖励自己）

**沟通风格**：
- 温暖但不虚伪，鼓励但基于事实
- 避免 toxic positivity，承认减肥确实不容易
- 使用动机式访谈（Motivational Interviewing）技巧

---

## Skill 9: Sleep & Recovery（睡眠与恢复管理）

**定位**：睡眠质量直接影响食欲激素（Ghrelin/Leptin）和减肥效果，是常被忽视的关键因素。

**对话需收集的信息**：
- 当前睡眠时长和质量
- 入睡困难或中途醒来情况
- 睡前习惯（屏幕时间、进食、咖啡因摄入时间）
- 压力水平和来源

**功能**：
- 睡眠质量评估和改善建议
- 睡眠卫生（Sleep Hygiene）指导清单
- 压力管理技巧（呼吸练习、渐进式肌肉放松等）
- 休息日和恢复日的运动建议（Active Recovery）
- 咖啡因和酒精对睡眠/减肥的影响教育
- 每日压力/能量水平追踪

---

## Skill 10: Grocery Shopping & Meal Prep（采购与备餐指导）

**定位**：将膳食计划转化为实际可执行的购物和烹饪行动。

**功能**：
- 根据周膳食计划自动生成购物清单（按超市分区组织）
- 预算优化建议（当季食材、打折替代品）
- 周日 Meal Prep 指南（批量烹饪方案，含时间线）
- 食材保鲜和储存建议
- 健康零食储备清单
- 适合不同超市的购物策略（Costco 批发 vs Trader Joe's 特色产品）

**美国本土化要点**：
- 按美国超市布局组织购物清单
- 纳入常见美国品牌的健康选择推荐
- 考虑食品荒漠（Food Desert）地区的替代方案

---

## Skill 11: Nutrition Education（营养知识教育）

**定位**：授人以鱼不如授人以渔 — 帮助用户建立长期受用的营养知识体系。

**教育模块**：
- **基础模块**：卡路里是什么、三大宏量营养素（Protein/Carbs/Fat）的角色
- **食品标签模块**：如何读懂 Nutrition Facts Label（FDA 格式）
- **份量认知模块**：美国 portion distortion 问题、如何估算 portion size
- **饮食迷思破除**：排毒饮食、代餐、"超级食物"等常见误区
- **餐厅点单模块**：外食场景下的健康选择策略
- **水分与饮料模块**：含糖饮料的隐藏热量、酒精热量

**交互方式**：
- 每次推送一个小知识点（bite-sized learning）
- 配合用户当前遇到的实际问题进行教育（如：用户蛋白质摄入不够时，讲解蛋白质的重要性）
- 小测验巩固知识

---

## Skill 12: Emotional Eating & Mindfulness（情绪饮食与正念）

**定位**：很多人的体重问题根源在情绪和心理，这个 Skill 处理"为什么吃"而不只是"吃什么"。

**对话需收集的信息**：
- 情绪与进食的关系模式（压力大时是否暴食、无聊时是否找零食）
- 常见触发场景
- 与食物和身体的情感关系

**功能**：
- 情绪饮食触发器识别和记录
- 替代应对策略库（压力大时可以做什么来替代吃东西）
- 正念饮食练习引导（Mindful Eating：慢嚼、关注饱腹感）
- Hunger Scale 使用训练（1-10 饥饿量表，区分生理饥饿 vs 心理饥饿）
- 自我关怀练习（Self-Compassion，减少因饮食"失控"的自我攻击）
- Body Neutrality 引导（减少对体重的过度焦虑）

**重要边界**：
- 明确声明 AI 不能替代心理治疗师
- 检测到严重饮食障碍信号时（如极端节食、催吐）推荐专业帮助
- 提供 NEDA（National Eating Disorders Association）热线等资源

---

## Skills 之间的数据流转

```
Skill 1 (Assessment)
  └──► User Profile ──► 所有 Skills 共享

Skill 2 (Goal Setting)
  └──► Phase Plan + Calorie Target ──► Skill 3, 4, 5

Skill 3 (Meal Planning)
  └──► Weekly Meal Plan ──► Skill 10 (Shopping List)

Skill 5 (Food Tracking)
  ├──► Daily Intake Data ──► Skill 7 (Analytics)
  └──► Eating Patterns ──► Skill 6 (Habit Coaching)

Skill 4 (Exercise)
  └──► Workout Logs ──► Skill 7 (Analytics)

Skill 6 (Habits)
  └──► Habit Completion Data ──► Skill 7 (Analytics)

Skill 7 (Analytics)
  ├──► Progress Reports ──► Skill 8 (Motivation)
  └──► Plateau Alerts ──► Skill 2 (Plan Adjustment)

Skill 9 (Sleep)
  └──► Sleep Data ──► Skill 7 (Analytics)
```

---

## 实施优先级建议

### P0 — 最小可用产品（MVP）
1. **Skill 1: Onboarding & Assessment** — 没有用户画像一切无从谈起
2. **Skill 2: Goal Setting & Planning** — 有了画像需要立即转化为计划
3. **Skill 3: Nutrition & Meal Planning** — "70% 靠吃"，饮食是减肥核心
4. **Skill 5: Calorie & Food Tracking** — 追踪是执行力的保障

### P1 — 核心体验完善
5. **Skill 4: Exercise & Fitness Planning** — 运动是另一大支柱
6. **Skill 7: Progress Tracking & Analytics** — 数据反馈形成闭环
7. **Skill 8: Motivational Coaching** — 留存和坚持的关键

### P2 — 差异化增强
8. **Skill 6: Habit Building** — 长期行为改变
9. **Skill 12: Emotional Eating** — 处理根源问题
10. **Skill 9: Sleep & Recovery** — 常被忽视但影响巨大

### P3 — 锦上添花
11. **Skill 10: Grocery & Meal Prep** — 实用辅助工具
12. **Skill 11: Nutrition Education** — 知识赋能

---

## 每个 Skill 的通用设计原则

1. **对话优先**：所有信息通过自然对话收集，不要表单式问答
2. **渐进收集**：不一次问完所有问题，随使用深入逐步补充
3. **方案可调**：用户任何时候都可以对方案提出反馈，AI 即时调整
4. **科学依据**：所有建议需基于循证医学/营养学，标注信息来源
5. **安全边界**：检测危险行为（极端节食、过度运动），主动干预并推荐专业帮助
6. **文化敏感**：尊重美国多元文化饮食习惯（Latin, Asian, African American, etc.）
7. **隐私优先**：健康数据本地存储，不上传云端
8. **非评判态度**：不因体重或饮食选择进行道德评判
