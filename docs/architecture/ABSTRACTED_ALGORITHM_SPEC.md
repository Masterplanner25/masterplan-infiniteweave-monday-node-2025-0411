# Abstracted Algorithm Spec

This document formalizes computational logic into implementation-agnostic mathematical representations.

**SEO Scoring**
Scoring formulas:
- Word count: `W = count(words)`
- Readability: `R = 100 - (W / 200 × 10)`
- Keyword density (percentage): `D(k) = round((count(k) / W) × 100, 2)`
- Top keywords: select up to 5 keywords with highest `count(k)`.
Output structure:
- `{word_count, readability, top_keywords, keyword_densities}` where `keyword_densities` contains `D(k)` values.

**Task State Logic**
Decision table:

| Action | Condition | State Update | Output |
| --- | --- | --- | --- |
| Start | Task missing | None | Not found message |
| Start | Start time not set | Start time = now; status = in progress | Started message |
| Start | Start time set | None | Already started message |
| Pause | Task missing | None | Not found message |
| Pause | Status = in progress | time_spent += Δt; status = paused | Paused message |
| Pause | Status ≠ in progress | None | Not in progress message |
| Complete | Task missing | None | Not found message |
| Complete | Start time set | time_spent += Δt; status = completed; end_time = now | Completed message |
| Complete | Start time not set | status = completed; end_time = now | Completed message |

Time delta equation:
- `Δt = (now - start_time)` in seconds.

**Projection Logic**
Empty-input behavior:
- If no historical rates, return `None`.
Percentiles and extrema:
- Conservative rate: 30th percentile of historical rates.
- Aggressive rate: 70th percentile of historical rates.
- Optimal rate: maximum historical rate.
Time compression:
- Effective rate: `r_eff = r / C` where `C = 100`.
- Remaining days: `d_rem = days(target_date - today)`.
- Adjusted days: `d_adj = d_rem / r_eff`.
Return rule:
- If `r ≤ 0` or `r_eff ≤ 0`, return `target_date`.
- Otherwise return `today + d_adj` (days) for each scenario.

**Masterplan Logic**
Activation decision table:

| Condition | Actions |
| --- | --- |
| Plan not found | Return 404 |
| Plan found | Deactivate all plans; activate selected plan; set activation time; commit |

Genesis locking decision table:

| Condition | Outcome |
| --- | --- |
| Session missing | Error |
| Session locked | Error |
| No existing plans | Version = V1; origin = true; parent = none |
| Existing plans | Version = V(n+1); origin = false; parent = last plan |

Time horizon equations:
- `target_date = start_date + (H × 365 days)`, where `H` is the time horizon in years.

**Memory Link Logic**
Link creation decision table:

| Condition | Outcome |
| --- | --- |
| Source = target | Error |
| Source or target missing | Error |
| Otherwise | Create link; commit |

**Metric Calculations**
General scoring formulas:
- Effort: `(time × complexity) / (skill + AI + 1)`
- Productivity: `(AI × skill) / (time + 1)`
- Virality: `(share × engagement × conversion) / (time_factor + 1)`
- Engagement score: `[(likes × 2) + (shares × 3) + (comments × 1.5) + (clicks × 1) + (time_on_page × 0.5)] / views`
- AI efficiency: `(AI_contrib / (human_contrib + 1)) × (total_tasks / 10)`
- Impact score: `(engagement / reach) × 100 + (conversion × 2)`

Business and growth formulas:
- Income efficiency: `(focused_effort × AI) / (time + capital)`
- Revenue scaling: `((AI_leverage + distribution) / time) × audience_engagement`
- Execution speed: `(AI_automations + systemized_workflows) / decision_lag`
- Attention value: `(content_output × presence) / time`
- Engagement rate: `interactions / views`
- Business growth: `(revenue - expenses) / scaling_friction`
- Monetization efficiency: `revenue / audience_size`
- AI productivity boost: `(tasks_with_AI - tasks_without_AI) / time_saved`
- Lost potential: `(missed_opportunities × time_delayed) - gains_from_action`
- Decision efficiency: `automated_decisions / (manual_decisions + processing_time)`

Rate calculations with zero guards:
- Interaction rate: `interaction_volume / visibility` if visibility > 0 else 0
- Attention rate: `deep_attention_units / visibility` if visibility > 0 else 0
- Intent rate: `intent_signals / reach` if reach > 0 else 0
- Conversion rate: `conversion_events / intent_signals` if intent_signals > 0 else 0
- Discovery ratio: `active_discovery / visibility` if visibility > 0 else 0
- Growth rate: `growth_velocity / reach` if reach > 0 else 0
