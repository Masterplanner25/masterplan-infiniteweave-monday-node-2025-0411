# Formula and Algorithm Overview

This document extracts and documents computational formulas and algorithmic processes strictly from the current implementation.

## 1. Explicit Mathematical Formulas

### Calculation Services (`AINDY/services/calculation_services.py`)
- `calculate_twr(task)`
  - Reference: `AINDY/services/calculation_services.py`
  - LHI = time_spent × task_complexity × skill_level
  - TWR = (LHI × ai_utilization × time_spent) / task_difficulty
  - Notes: `time_spent` appears twice in the final TWR formula.

- `calculate_effort(task)`
  - Reference: `AINDY/services/calculation_services.py`
  - Effort = (time_spent × task_complexity) / (skill_level + ai_utilization + 1)

- `calculate_productivity(task)`
  - Reference: `AINDY/services/calculation_services.py`
  - Productivity = (ai_utilization × skill_level) / (time_spent + 1)

- `calculate_virality(share_rate, engagement_rate, conversion_rate, time_factor)`
  - Reference: `AINDY/services/calculation_services.py`
  - Virality = (share_rate × engagement_rate × conversion_rate) / (time_factor + 1)

- `calculate_engagement_score(data)`
  - Reference: `AINDY/services/calculation_services.py`
  - If total_views == 0 ? 0
  - Score = ((likes × 2) + (shares × 3) + (comments × 1.5) + (clicks × 1) + (time_on_page × 0.5)) / total_views
  - Returned as `round(score, 2)`

- `calculate_ai_efficiency(data)`
  - Reference: `AINDY/services/calculation_services.py`
  - If total_tasks == 0 ? 0
  - Score = (ai_contributions / (human_contributions + 1)) × (total_tasks / 10)
  - Returned as `round(score, 2)`

- `calculate_impact_score(data)`
  - Reference: `AINDY/services/calculation_services.py`
  - If reach == 0 ? 0
  - Score = (engagement / reach) × 100 + (conversion × 2)
  - Returned as `round(score, 2)`

- `income_efficiency(eff)`
  - Reference: `AINDY/services/calculation_services.py`
  - Income efficiency = (focused_effort × ai_utilization) / (time + capital)

- `revenue_scaling(rs)`
  - Reference: `AINDY/services/calculation_services.py`
  - Revenue scaling = ((ai_leverage + content_distribution) / time) × audience_engagement

- `execution_speed(es)`
  - Reference: `AINDY/services/calculation_services.py`
  - Execution speed = (ai_automations + systemized_workflows) / decision_lag

- `attention_value(input_data)`
  - Reference: `AINDY/services/calculation_services.py`
  - Attention value = (content_output × platform_presence) / time

- `engagement_rate(input_data)`
  - Reference: `AINDY/services/calculation_services.py`
  - Engagement rate = total_interactions / total_views

- `business_growth(input_data)`
  - Reference: `AINDY/services/calculation_services.py`
  - Business growth = (revenue - expenses) / scaling_friction

- `monetization_efficiency(input_data)`
  - Reference: `AINDY/services/calculation_services.py`
  - Monetization efficiency = total_revenue / audience_size

- `ai_productivity_boost(input_data)`
  - Reference: `AINDY/services/calculation_services.py`
  - AI productivity boost = (tasks_with_ai - tasks_without_ai) / time_saved

- `lost_potential(input_data)`
  - Reference: `AINDY/services/calculation_services.py`
  - Lost potential = (missed_opportunities × time_delayed) - gains_from_action

- `decision_efficiency(input_data)`
  - Reference: `AINDY/services/calculation_services.py`
  - Decision efficiency = automated_decisions / (manual_decisions + processing_time)

### Projection Service (`AINDY/services/projection_service.py`)
- `project_completion(masterplan, twr_values)`
  - Reference: `AINDY/services/projection_service.py`
  - If `twr_values` is empty ? return `None`
  - `conservative` = percentile(TWR, 30)
  - `aggressive` = percentile(TWR, 70)
  - `optimal` = max(TWR)
  - `remaining_days` = (target_date - today).days
  - `effective_rate` = rate / COMPRESSION_DIVISOR (COMPRESSION_DIVISOR = 100)
  - `adjusted_days` = remaining_days / effective_rate
  - `projected_eta` = today + adjusted_days (days)
  - If `rate <= 0` or `effective_rate <= 0`, return `target_date`.
  - Returns dict with `conservative_eta`, `aggressive_eta`, `optimal_eta`.

- `evaluate_phase(plan)`
  - Reference: `AINDY/services/projection_service.py`
  - `phase_end` = start_date + (duration_years × 365 days)
  - `thresholds_met` = all of:
    - total_wcu >= wcu_target
    - gross_revenue >= revenue_target
    - books_published >= books_required
    - (platform_required is False) OR platform_live
    - (studio_required is False) OR studio_ready
    - active_playbooks >= playbooks_required
  - Returns 2 if thresholds_met OR now >= phase_end; else returns 1.

### SEO Routes (`AINDY/routes/seo_routes.py`)
- `POST /analyze_seo/` (inline logic)
  - Reference: `AINDY/routes/seo_routes.py`
  - word_count = len(words)
  - readability = 100 - (len(words) / 200 × 10)
  - keyword_densities[w] = count(w)
  - top_keywords = sorted(keyword_densities, key=count desc)[:5]
  - densities[k] = round(count(k) / word_count × 100, 2)
  - Returns: `{word_count, readability, top_keywords, keyword_densities}` where `keyword_densities` is `densities` (percentage values).

### SEO Services (`AINDY/services/seo_services.py`)
- `keyword_density(text, keyword)`
  - Reference: `AINDY/services/seo_services.py`
  - `words = nltk.word_tokenize(text.lower())`
  - `keyword_norm = keyword.lower()`
  - `density = round((count(words, keyword_norm) / len(words)) × 100, 2)`
- `seo_analysis(text, top_n)`
  - Reference: `AINDY/services/seo_services.py`
  - keywords = extract_keywords(text, top_n)  # list of (keyword, count); preprocessing and filtering occur inside extract_keywords()
  - word_count = len(nltk.word_tokenize(text))
  - readability = textstat.flesch_reading_ease(text)
  - densities = {kw[0]: keyword_density(text, kw[0]) for kw in keywords}
  - Returns:
    - `top_keywords = [kw[0] for kw in keywords]`
    - `keyword_densities = densities`
  - Full return dict: `{word_count, readability, top_keywords, keyword_densities}`
 - `extract_keywords(text, top_n)`
   - Reference: `AINDY/services/seo_services.py`
   - tokens = nltk.word_tokenize(text.lower()) filtered to `.isalnum()`
   - returns `Counter(words).most_common(top_n)`

### Analytics Rate Calculator (`AINDY/services/analytics/rate_calculator.py`)
- Rates are calculated with division-by-zero guards:
  - Reference: `AINDY/services/analytics/rate_calculator.py`
  - interaction_rate = interaction_volume / passive_visibility (if visibility else 0)
  - attention_rate = deep_attention_units / passive_visibility (if visibility else 0)
  - intent_rate = intent_signals / unique_reach (if reach else 0)
  - conversion_rate = conversion_events / intent_signals (if intent else 0)
  - discovery_ratio = active_discovery / passive_visibility (if visibility else 0)
  - growth_rate = growth_velocity / unique_reach (if reach else 0)

### Analytics Adapter (`AINDY/services/analytics/linkedin_adapter.py`)
- interaction_volume = likes + comments + shares
- intent_signals = profile_views + link_clicks
- canonical_data updated with rates from `calculate_rates`.
  - Reference: `AINDY/services/analytics/linkedin_adapter.py`

### Freelance Metrics (`AINDY/services/freelance_service.py`)
- `update_revenue_metrics`:
  - total_revenue = sum(price) for delivered orders
  - Returns RevenueMetrics with `total_revenue` and `None` for other fields.

### Task Services (`AINDY/services/task_services.py`)
- `complete_task`:
  - Reference: `AINDY/services/task_services.py`
  - If started, `time_spent += (now - start_time).total_seconds()`
  - Converts to hours for TWR input: `time_spent / 3600`
  - Updates MongoDB metrics:
    - execution_velocity += 1
    - twr_score += (twr_score × 0.1)
  - Mongo update reference: `AINDY/services/task_services.py` (`update_one`), `AINDY/services/task_services.py` (metrics increments)

### RippleTrace Services (`AINDY/services/rippletrace_services.py`)
- `log_ripple_event`:
  - Generates `id` if absent: `ripple-{timestamp}`

### Health Check (`AINDY/routes/health_router.py`)
- Measures endpoint latency:
  - `elapsed_ms = round((time.time() - start) * 1000, 2)`
  - Reference: `AINDY/routes/health_router.py`
- `avg_latency_ms = statistics.mean(latencies)`
  - Reference: `AINDY/routes/health_router.py`
- `status = "healthy"` if no component errors and all endpoints ok; else `"degraded"`.

## 2. Aggregation Logic

### Batch Processing (`AINDY/services/calculations.py`)
- For each list field in `BatchInput`, computes list of metric values using corresponding function:
  - e.g., `results["AI Productivity Boost"] = [ai_productivity_boost(x) for x in batch_data.ai_productivity_boost]`
- Returns a dict keyed by metric name with list values.

### Analytics Summary (`AINDY/routes/analytics_router.py`)
- Early return:
  - If no telemetry records exist: `return {"message": "No telemetry records found."}`
- For `group_by == "period"`:
  - Reference: `AINDY/routes/analytics_router.py`
  - Sums per-period totals for each metric.
  - Recomputes rates using per-period totals with `or 1` guards for denominators.
  - Rates calculation block reference: `AINDY/routes/analytics_router.py`
- For global summary:
  - Totals are sums across all records.
  - Rates recomputed using totals with `or 1` guards.
  - Rates calculation block reference: `AINDY/routes/analytics_router.py`

### Research Results (`AINDY/services/research_results_service.py`)
- Maintains a singleton runtime trace `_memory_trace` and appends nodes to it.

## 3. Decision Algorithms

### Masterplan Activation (`AINDY/routes/genesis_router.py`)
Pseudocode:
```
if plan_id not found:
  raise 404
set all MasterPlan.is_active = False
set selected plan.is_active = True
set activated_at = now
commit
```

### Genesis Locking (`AINDY/services/masterplan_factory.py`)
Pseudocode:
```
if session not found: error
if session.status == "locked": error
if no existing plans:
  version_label = "V1", is_origin = True, parent_id = None
else:
  version_label = "V{count+1}", is_origin = False, parent_id = last_plan.id
horizon = draft.time_horizon_years (default 5)
start_date = now
target_date = start_date + horizon*365 days
posture = determine_posture(draft)
create MasterPlan(...)
session.status = "locked"
commit
```

### Task State Transitions (`AINDY/services/task_services.py`)
Pseudocode:
```
start_task(name):
  if task not found -> return message
  if start_time not set:
    set start_time = now
    status = "in_progress"
  else:
    return already started message

pause_task(name):
  if task not found -> return message
  if status == "in_progress":
    time_spent += (now - start_time).total_seconds()
    status = "paused"
  else:
    return not in progress message

complete_task(name):
  if task not found -> return message
  if start_time set:
    time_spent += (now - start_time).total_seconds()
  status = "completed"
  end_time = now
  compute TWR and save calculations
```

### Memory Bridge Permission Validation (`AINDY/routes/bridge_router.py`)
Pseudocode:
```
expected = JWT(authenticated request)
if expected != signature: 403
if ts + ttl < now: 403
```
Reference: `AINDY/routes/bridge_router.py`

### Social Feed Scoring (`AINDY/routes/social_router.py`)
Pseudocode:
```
relevance = 1.0
if trust_tier_required == INNER_CIRCLE:
  relevance = 2.0
```

## 4. External Model Processing Logic

### Genesis LLM (`AINDY/services/genesis_ai.py`)
- Sends system and user messages to OpenAI chat completions.
- Parses `response.choices[0].message.content` as JSON.
- Fallback: returns static dict if JSON parsing fails.
- Reference: `AINDY/services/genesis_ai.py` (call), `AINDY/services/genesis_ai.py` (json.loads).

### LeadGen Scoring (`AINDY/services/leadgen_service.py`)
- Calls OpenAI chat completions with system prompt.
- Attempts to parse JSON; if output not JSON, extracts substring with regex.
- Fallback: returns scores of 0 on exception.
- Reference: `AINDY/services/leadgen_service.py` (score_lead), `AINDY/services/leadgen_service.py` (regex extraction), `AINDY/services/leadgen_service.py` (json.loads).

### DeepSeek ARM (`AINDY/services/deepseek_arm_service.py`)
- Validates file path.
- Runs analysis/generation synchronously.
- Truncates outputs for DB summaries (first 1000 chars and 250 chars for memory log summary).
- References: `AINDY/services/deepseek_arm_service.py` (run_analysis), `AINDY/services/deepseek_arm_service.py` (start_time), `AINDY/services/deepseek_arm_service.py` (duration), `AINDY/services/deepseek_arm_service.py` (analysis_summary[:1000]), `AINDY/services/deepseek_arm_service.py` (analysis_summary[:250]), `AINDY/services/deepseek_arm_service.py` (generate_code), `AINDY/services/deepseek_arm_service.py` (output_code[:1000]).

## 5. Memory Bridge Algorithms

### Node Creation (`AINDY/services/memory_persistence.py`)
- Creates a `MemoryNodeModel` with:
  - id: provided or generated UUID
  - content: string coercion
  - tags: list coercion
  - node_type: default "generic"
  - extra: dict
- Persists and returns the DB row.

### Link Creation (`AINDY/services/memory_persistence.py`)
Pseudocode:
```
if source_id == target_id: error
if source_id or target_id not in memory_nodes: error
create MemoryLinkModel(source_id, target_id, link_type)
commit
```

### Tag Filtering (`AINDY/services/memory_persistence.py`)
- `find_by_tags(tags, mode)`:
  - If mode == "OR": OR of `tags.contains([t])`
  - Else: AND by successive `tags.contains([t])`

### Relationship Traversal (`AINDY/bridge/bridge.py`)
- `find_by_tag` recursively traverses `MemoryNode.children` tree and collects nodes with tag.

## 6. Background Task Algorithms

### Reminders (`AINDY/services/task_services.py`)
Pseudocode:
```
loop forever:
  now = datetime.now()
  for task in tasks:
    if reminder_time and now >= reminder_time and status != completed:
      print reminder
      reminder_time = None
      commit
  sleep 60s
```

### Recurrence (`AINDY/services/task_services.py`)
Pseudocode:
```
loop forever:
  tasks = tasks where status == completed
  (no recurrence logic implemented)
  sleep 60s
```

### Startup Thread Stubs (`AINDY/main.py`)
- Startup event defines local `handle_recurrence` and `check_reminders` that only log and do not loop.

## 7. Data Transformation Pipelines

### LinkedIn Analytics (`AINDY/services/analytics/linkedin_adapter.py`)
- Input: `LinkedInRawInput`
- Transform: compute interaction_volume and intent_signals; compute rates via `calculate_rates`
- Output: canonical dict persisted to `CanonicalMetricDB` (`AINDY/routes/analytics_router.py`)

### Research Results (`AINDY/services/research_results_service.py`)
- Input: `ResearchResultCreate`
- Persist: `ResearchResult` ORM record
- Side effect: create `MemoryNode` in runtime trace and persist via `create_memory_node`

### SEO Analysis (`AINDY/routes/seo_routes.py`, `AINDY/services/seo_services.py`)
- Input: raw content or SEOInput
- Transform: compute word counts, readability, keyword densities
- Persist: `save_calculation` called for readability and word count (and avg density)

### LeadGen (`AINDY/services/leadgen_service.py`)
- Input: query string
- Transform: run AI search (mocked), score leads via OpenAI
- Persist: `LeadGenResult` ORM entries
- Side effect: `create_memory_node` per lead

### ARM/DeepSeek (`AINDY/services/deepseek_arm_service.py`)
- Input: file_path (+ optional instructions)
- Transform: analyze/generate; track duration
- Persist: `ARMRun` and `ARMLog` entries; Memory Bridge node

## 8. Known Algorithmic Gaps
- Magic numbers:
  - `COMPRESSION_DIVISOR = 100` in `AINDY/services/projection_service.py`.
  - Multiple fixed multipliers in `calculate_engagement_score` and `calculate_impact_score`.
- Division-by-zero safeguards are inconsistent:
  - Some functions guard (e.g., `calculate_engagement_score`, `calculate_ai_efficiency`, `calculate_impact_score`), others do not (e.g., `execution_speed`, `engagement_rate`, `attention_value`).
- Duplicate function name in `AINDY/services/seo_services.py`: `generate_meta_description` defined twice; later definition overrides earlier one.
- `AINDY/services/leadgen_service.py` contains duplicated scoring logic (dead code after first return block).
- `AINDY/routes/seo_routes.py` has two `analyze_seo` functions with different behaviors; both are bound to different routes.
- In `AINDY/bridge/bridge.py`, the `create_memory_node` function persists to `CalculationResult` with placeholder values.


