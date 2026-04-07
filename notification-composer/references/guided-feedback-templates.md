# Guided Feedback — Templates & Answer Mapping

Adapt language to match `locale.json`. Chinese templates below; translate
naturally for other locales.

## Message Templates

### `reminder-timing` (chain 1 head)

```
你已经打了 {total_check_ins} 次卡了，慢慢有感觉了吧 😊 想了解一下你的使用感受，我好调整配合你的节奏。

现在是饭前 15 分钟提醒你，你觉得这个时间：
1. 挺好的，刚刚好
2. 太晚了，想提前 30 分钟收到
3. 再早点，提前 1 小时提醒我

或者你有别的想法也行，随便说。
```

### `reminder-frequency`

```
再问一个提醒相关的 🙌 如果提醒发了你没回，你希望我：
1. 就提醒一次，没回就算了
2. 隔 30 分钟再提醒我一次
3. 隔 30 分钟提醒，还没回就再来一次（最多提醒 3 次）

或者你有别的想法也行，随便说。
```

### `reminder-style`

```
每次提醒的时候，你更希望我：
1. 现在这样就挺好
2. 简单提醒就行（"晚饭时间到了，记得拍照打卡～"）
3. 加点鼓励打气（"今天已经坚持第 X 天了，继续冲！"）

或者你有别的想法也行，随便说。
```

### `feedback-tone` (chain 2 head)

```
用了几天了，想了解一下你对饮食反馈的感受 😊

这几天我给的反馈（比如"蛋白质偏低""这顿热量有点高"），你觉得：
1. 挺好的，继续这样
2. 再严格一点，超标了就明确提醒我
3. 温柔一些，少挑毛病多鼓励
4. 别评价了，我记录你帮我存就行

了解你的感受，后面每天的反馈才对味。
```

### `food-preference`

```
这几天推荐的菜有没有不太合适的？
1. 都还行，继续推
2. 有些食材不喜欢或买不到（告诉我哪些）
3. 做法太复杂了，想要更简单的
4. 口味上想调整（比如偏中式、偏清淡等）

告诉我之后推荐会越来越对你胃口。
```

### `advice-intensity`

```
还有一个——我给建议的时候，你希望我：
1. 就告诉我怎么做就行
2. 多说说为什么这么建议，帮我理解
3. 可以说说不调整的话会怎样，帮我更有动力执行

你越告诉我你的习惯，我越能在对的时间说对的话。
```

### `open-review`

```
用了好几天了，整体感觉怎么样？有没有什么想让我调整的？比如说话方式、提醒频率、推荐内容……什么都行。没有的话也完全 OK 👍
```

## Answer → Preference Mapping

| Question | Choice | ai-preferences.md Update |
|----------|--------|--------------------------|
| `reminder-timing`: 1 | Keep | No change |
| `reminder-timing`: 2 | 30min | `Reminder Lead Time: 30min` |
| `reminder-timing`: 3 | 1h | `Reminder Lead Time: 60min` |
| `reminder-frequency`: 1 | Once | `Reminder Repeat: false` |
| `reminder-frequency`: 2 | +1 | `Reminder Repeat: true`, `Reminder Max Repeats: 1` |
| `reminder-frequency`: 3 | +2 | `Reminder Repeat: true`, `Reminder Max Repeats: 2` |
| `reminder-style`: 1 | Keep | No change |
| `reminder-style`: 2 | Brief | `Reminder Content: brief` |
| `reminder-style`: 3 | Motivational | `Reminder Content: motivational` |
| `feedback-tone`: 1 | Keep | No change |
| `feedback-tone`: 2 | Strict | `Strictness: strict` |
| `feedback-tone`: 3 | Gentle | `Strictness: relaxed`, `Tone: warm-friend` |
| `feedback-tone`: 4 | Silent | `Unsolicited Advice: none`, `Comparison with Plan: weekly-only` |
| `food-preference`: 1 | Keep | No change |
| `food-preference`: 2-4 | Specific | Append to `health-preferences.md` |
| `advice-intensity`: 1 | Action | `Advice Style: action-only` |
| `advice-intensity`: 2 | Reasoning | `Advice Style: with-reasoning` |
| `advice-intensity`: 3 | Consequences | `Advice Style: with-consequences` |
| `open-review` | Any | Parse and apply to relevant fields |

## Reply Detection

1. Number (1-4) → direct answer
2. Short phrase matching option → map to number
3. Food/exercise/emotional content → not an answer, route normally
4. Free-text feedback → treat as custom answer
