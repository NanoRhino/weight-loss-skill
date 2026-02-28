# Risk Alert Rules

Risk alerts are triggered based on patterns detected across the user's exercise history. When triggered, set `risk_alert` in the JSON response and include a gentle warning in the `feedback` field.

---

## Alert Types

### 1. Overtraining — Consecutive High Intensity

**Trigger**: 3 or more consecutive days with `intensity: "high"` logged.

**Alert message** (adapt to user's language):
- "连续3天高强度了，身体需要恢复时间。明天可以安排一个休息日或者做做拉伸/瑜伽。"
- "That's 3 high-intensity days in a row — your body needs recovery time. Consider a rest day or light stretching tomorrow."

**JSON**: `risk_alert: "consecutive_high_intensity"`

---

### 2. Volume Spike — Sudden Increase

**Trigger**: Current week's total duration exceeds previous week's by more than 50%, AND previous week had at least 3 sessions logged.

**Alert message**:
- "这周运动量比上周增加了不少，注意循序渐进，别一下子加太多，受伤就不值了。"
- "Big jump in volume this week compared to last. Remember to increase gradually — a good rule of thumb is no more than 10-20% per week."

**JSON**: `risk_alert: "volume_spike"`

---

### 3. Pain or Discomfort Mentioned

**Trigger**: User mentions pain, soreness, injury, or discomfort in their log. Keywords:

| Language | Keywords |
|----------|----------|
| English | pain, hurt, sore, injury, injured, pulled, strained, ache, discomfort, twinge, sharp pain |
| Chinese | 痛, 疼, 受伤, 拉伤, 扭伤, 不舒服, 酸痛, 伤了, 难受 |

**Distinguish**: Normal post-workout soreness ("muscles are sore" / "肌肉酸") vs. acute pain ("sharp pain in knee" / "膝盖刺痛"). Only alert for acute/specific pain.

**Alert message**:
- "听到你提到[部位]不舒服，建议先休息观察。如果持续或加重，建议看一下运动医学科。"
- "I noticed you mentioned [body part] pain. Take it easy and monitor it. If it persists or worsens, consider seeing a sports medicine professional."

**JSON**: `risk_alert: "pain_reported"`

---

### 4. Exercise Monotony — Lack of Variety

**Trigger**: For the past 2 weeks (14 days), all logged exercises fall into the same single category (e.g., all `cardio`, no strength/flexibility).

**Alert message**:
- "最近两周都是[类型]，考虑加一些[缺少的类型]，均衡一下训练结构。比如加一次力量训练可以帮助提高跑步表现。"
- "You've been doing exclusively [category] for 2 weeks. Adding some [missing category] would help balance your training. For example, strength work can actually improve your cardio performance."

**JSON**: `risk_alert: "exercise_monotony"`

**Suggestion mapping**:
- Only cardio → suggest adding strength
- Only strength → suggest adding cardio + flexibility
- Only flexibility → suggest adding cardio or strength
- Only sports → suggest adding strength + flexibility

---

## Alert Behavior Rules

1. **One alert per response** — if multiple alerts trigger simultaneously, prioritize: `pain_reported` > `consecutive_high_intensity` > `volume_spike` > `exercise_monotony`
2. **Don't repeat the same alert within 3 days** — if user was already alerted about consecutive high intensity on Monday, don't re-alert on Tuesday for the same pattern unless it has worsened
3. **Tone is always supportive, never scolding** — frame as care, not criticism
4. **Never give medical diagnoses** — for pain alerts, always recommend seeing a professional for persistent issues
5. **Respect user autonomy** — if user acknowledges the alert and continues, don't keep nagging
