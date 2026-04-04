# Data Model Map

This document maps the current data model strictly as implemented in the repository. If a property cannot be confirmed, it is marked as not explicitly defined in the current implementation.

## 1. PostgreSQL / SQLAlchemy Models

### `AINDY/db/models/arm_models.py`

#### ARMRun (`arm_runs`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `file_path`: String, nullable=False, default: not defined
- `operation`: String, nullable: not explicitly set, default="analysis"
- `result_summary`: Text, nullable: not explicitly set, default: not defined
- `runtime`: Float, nullable: not explicitly set, default: not defined
- `created_at`: DateTime, nullable: not explicitly set, default=func.now()
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True)
- Foreign keys: None
- Relationships:
- `logs = relationship("ARMLog", back_populates="run", cascade="all, delete-orphan")`
- Cascade rules: `all, delete-orphan` on `ARMRun.logs`

#### ARMLog (`arm_logs`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `run_id`: Integer, ForeignKey("arm_runs.id"), nullable: not explicitly set, default: not defined
- `timestamp`: DateTime, nullable: not explicitly set, default=func.now()
- `level`: String, nullable: not explicitly set, default="INFO"
- `message`: Text, nullable: not explicitly set, default: not defined
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True)
- Foreign keys: `run_id -> arm_runs.id`
- Relationships:
- `run = relationship("ARMRun", back_populates="logs")`
- Cascade rules: Not explicitly defined in current implementation.

#### ARMConfig (`arm_configs`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `parameter`: String, nullable=False, default: not defined
- `value`: String, nullable=False, default: not defined
- `updated_at`: DateTime, nullable: not explicitly set, default=func.now()
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True)
- Foreign keys: None
- Relationships:
- `tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")`

### `AINDY/db/models/agent.py`

#### Agent (`agents`)
- Columns
- `id`: String, primary key, nullable: not explicitly set (primary key implies non-null), default: not defined
- `name`: String, nullable=False, unique=True
- `agent_type`: String, nullable=False
- `description`: Text, nullable=True
- `owner_user_id`: String, nullable=True
- `is_active`: Boolean, nullable=False, default=True
- `memory_namespace`: String, nullable=False, unique=True
- `created_at`: DateTime(timezone=True), nullable: not explicitly set, server_default=func.now()
- Primary key: `id`
- Unique constraints: `name`, `memory_namespace`
- Indexes: Not explicitly defined in current implementation.
- Foreign keys: None
- Relationships: None

### `AINDY/db/models/author_model.py`

#### AuthorDB (`authors`)
- Columns
- `id`: String, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `name`: String, nullable=False, default: not defined
- `platform`: String, nullable=False, default: not defined
- `notes`: Text, nullable=True, default: not defined
- `joined_at`: DateTime, nullable: not explicitly set, default=datetime.utcnow
- `last_seen`: DateTime, nullable: not explicitly set, default=datetime.utcnow
- `user_id`: UUID, nullable=True, index=True
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `user_id` (index=True, `ix_authors_user_id`)
- Foreign keys: None
- Relationships: None

### `AINDY/db/models/bridge_user_event.py`

#### BridgeUserEvent (`bridge_user_events`)
- Columns
- `id`: UUID, primary key, default=uuid.uuid4
- `user_name`: String, nullable=False, index=True
- `origin`: String, nullable=False, index=True
- `raw_timestamp`: String, nullable=True
- `occurred_at`: DateTime(timezone=True), nullable=True
- `created_at`: DateTime(timezone=True), nullable=False, server_default=func.now()
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `user_name` (index=True, `ix_bridge_user_events_user_name`), `origin` (index=True, `ix_bridge_user_events_origin`)
- Foreign keys: `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/background_task_lease.py`

#### BackgroundTaskLease (`background_task_leases`)
- Columns
- `id`: UUID, primary key, default=uuid.uuid4
- `name`: String, nullable=False, unique=True, index=True
- `owner_id`: String, nullable=False, index=True
- `acquired_at`: DateTime(timezone=True), nullable=False, server_default=func.now()
- `heartbeat_at`: DateTime(timezone=True), nullable=False, server_default=func.now()
- `expires_at`: DateTime(timezone=True), nullable=False
- Primary key: `id`
- Unique constraints: `name`
- Indexes: `name` (index=True, `ix_background_task_leases_name`), `owner_id` (index=True, `ix_background_task_leases_owner_id`)
- Foreign keys: `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/calculation.py`

#### CalculationResult (`calculation_results`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `metric_name`: String, index=True, nullable: not explicitly set, default: not defined
- `result_value`: Float, nullable: not explicitly set, default: not defined
- `created_at`: DateTime, nullable: not explicitly set, default=func.now()
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`, `metric_name` (index=True)
- Foreign keys: None
- Relationships: None

### `AINDY/db/models/drop.py`

#### DropPointDB (`drop_points`)
- Columns
- `id`: String, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `title`: String, nullable: not explicitly set, default: not defined
- `platform`: String, nullable: not explicitly set, default: not defined
- `url`: String, nullable=True, default: not defined
- `date_dropped`: DateTime, nullable: not explicitly set, default: not defined
- `core_themes`: Text, nullable: not explicitly set, default: not defined
- `tagged_entities`: Text, nullable: not explicitly set, default: not defined
- `intent`: String, nullable: not explicitly set, default: not defined
- `user_id`: UUID, ForeignKey("users.id"), nullable=True, index=True — **added Sprint 5 (2026-03-18)** for per-user data isolation
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `user_id` (index=True, `ix_drop_points_user_id`)
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### PingDB (`pings`)
- Columns
- `id`: String, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `drop_point_id`: String, ForeignKey("drop_points.id"), nullable: not explicitly set, default: not defined
- `ping_type`: String, nullable: not explicitly set, default: not defined
- `source_platform`: String, nullable: not explicitly set, default: not defined
- `date_detected`: DateTime, nullable: not explicitly set, default: not defined
- `connection_summary`: Text, nullable=True, default: not defined
- `external_url`: String, nullable=True, default: not defined
- `reaction_notes`: Text, nullable=True, default: not defined
- `user_id`: UUID, ForeignKey("users.id"), nullable=True, index=True — **added Sprint 5 (2026-03-18)** for per-user data isolation
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `user_id` (index=True, `ix_pings_user_id`)
- Foreign keys: `drop_point_id -> drop_points.id`, `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/freelance.py`

#### FreelanceOrder (`freelance_orders`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `client_name`: String, nullable=False, default: not defined
- `client_email`: String, nullable=False, default: not defined
- `service_type`: String, nullable=False, default: not defined
- `project_details`: Text, nullable=True, default: not defined
- `ai_output`: Text, nullable=True, default: not defined
- `price`: Float, nullable=False, default=0.0
- `status`: String, nullable: not explicitly set, default="pending"
- `created_at`: DateTime, nullable: not explicitly set, default=func.now()
- `updated_at`: DateTime, nullable: not explicitly set, default=func.now(), onupdate=func.now()
- `user_id`: UUID, ForeignKey("users.id"), nullable=True, index=True — **added Sprint 5 (2026-03-18)** for per-user data isolation
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `user_id` (index=True, `ix_freelance_orders_user_id`)
- Foreign keys: `user_id -> users.id`
- Relationships: Not explicitly defined in current implementation.

#### ClientFeedback (`client_feedback`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `order_id`: Integer, ForeignKey("freelance_orders.id", ondelete="CASCADE"), nullable: not explicitly set, default: not defined
- `rating`: Integer, nullable=True, default: not defined
- `feedback_text`: Text, nullable=True, default: not defined
- `ai_summary`: Text, nullable=True, default: not defined
- `created_at`: DateTime, nullable: not explicitly set, default=func.now()
- `user_id`: UUID, ForeignKey("users.id"), nullable=True, index=True — **added Sprint 5 (2026-03-18)** for per-user data isolation (denormalized; no join needed for ownership checks)
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `user_id` (index=True, `ix_client_feedback_user_id`)
- Foreign keys: `order_id -> freelance_orders.id` (ondelete="CASCADE"), `user_id -> users.id`
- Relationships:
- `order = relationship("FreelanceOrder", backref="feedback")`
- Cascade rules: Not explicitly defined in current implementation.

#### RevenueMetrics (`revenue_metrics`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `date`: DateTime, nullable: not explicitly set, default=func.now()
- `total_revenue`: Float, nullable=False, default=0.0
- `avg_execution_time`: Float, nullable=True, default: not defined
- `income_efficiency`: Float, nullable=True, default: not defined
- `ai_productivity_boost`: Float, nullable=True, default: not defined
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True)
- Foreign keys: None
- Relationships: None

### `AINDY/db/models/leadgen_model.py`

#### LeadGenResult (`leadgen_results`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `query`: String, index=True, nullable: not explicitly set, default: not defined
- `user_id`: UUID, nullable=True, index=True
- `company`: String, index=True, nullable: not explicitly set, default: not defined
- `url`: String, nullable: not explicitly set, default: not defined
- `context`: String, nullable: not explicitly set, default: not defined
- `fit_score`: Float, nullable: not explicitly set, default: not defined
- `intent_score`: Float, nullable: not explicitly set, default: not defined
- `data_quality_score`: Float, nullable: not explicitly set, default: not defined
- `overall_score`: Float, nullable: not explicitly set, default: not defined
- `reasoning`: String, nullable: not explicitly set, default: not defined
- `created_at`: DateTime, nullable: not explicitly set, default=func.now()
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`, `query`, `company` (index=True), `user_id` (index=True, `ix_leadgen_results_user_id`)
- Foreign keys: `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/masterplan.py`

#### MasterPlan (`master_plans`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `start_date`: DateTime, nullable=False, default: not defined
- `duration_years`: Float, nullable=False, default: not defined
- `target_date`: DateTime, nullable=False, default: not defined
- `is_active`: Boolean, nullable: not explicitly set, default=False
- `is_origin`: Boolean, nullable: not explicitly set, default=False
- `created_at`: DateTime, nullable: not explicitly set, default=func.now()
- `activated_at`: DateTime, nullable=True, default: not defined
- `structure_json`: JSON, nullable=True, default: not defined
- `posture`: String, nullable=True, default: not defined
- `version_label`: String, nullable=True, default: not defined
- `locked_at`: DateTime, nullable=True, default: not defined
- `parent_id`: Integer, ForeignKey("master_plans.id"), nullable=True, default: not defined
- `linked_genesis_session_id`: Integer, ForeignKey("genesis_sessions.id"), nullable=True, default: not defined
- `wcu_target`: Float, nullable: not explicitly set, default=3000
- `revenue_target`: Float, nullable: not explicitly set, default=100000
- `books_required`: Integer, nullable: not explicitly set, default=3
- `platform_required`: Boolean, nullable: not explicitly set, default=True
- `studio_required`: Boolean, nullable: not explicitly set, default=True
- `playbooks_required`: Integer, nullable: not explicitly set, default=2
- `total_wcu`: Float, nullable: not explicitly set, default=0
- `gross_revenue`: Float, nullable: not explicitly set, default=0
- `books_published`: Integer, nullable: not explicitly set, default=0
- `platform_live`: Boolean, nullable: not explicitly set, default=False
- `studio_ready`: Boolean, nullable: not explicitly set, default=False
- `active_playbooks`: Integer, nullable: not explicitly set, default=0
- `phase`: Integer, nullable: not explicitly set, default=1
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True)
- Foreign keys: `parent_id -> master_plans.id`, `linked_genesis_session_id -> genesis_sessions.id`
- Relationships:
- `parent = relationship("MasterPlan", remote_side=[id])`
- `canonical_metrics = relationship("CanonicalMetricDB", backref="masterplan", cascade="all, delete-orphan")`
- Cascade rules: `all, delete-orphan` on `MasterPlan.canonical_metrics`

#### GenesisSessionDB (`genesis_sessions`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null), default: not defined
- `user_id`: UUID, ForeignKey("users.id"), nullable=True, index=True
- `status`: String, nullable: not explicitly set, default="active"
- `summarized_state`: JSON, nullable=True, default: not defined
- `created_at`: DateTime(timezone=True), nullable: not explicitly set, server_default=func.now()
- `updated_at`: DateTime(timezone=True), nullable: not explicitly set, onupdate=func.now()
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `user_id` (index=True, `ix_genesis_sessions_user_id`)
- Foreign keys: `user_id -> users.id`
- Relationships: Not explicitly defined in current implementation.

### `AINDY/db/models/memory_metrics.py`

#### MemoryMetric (`memory_metrics`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `user_id`: String, nullable=False, index=True
- `task_type`: String, nullable=True, index=True
- `impact_score`: Float, nullable=False, default=0.0
- `memory_count`: Integer, nullable=False, default=0
- `avg_similarity`: Float, nullable=False, default=0.0
- `created_at`: DateTime, nullable=False, default=datetime.utcnow
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `user_id` (index=True, `ix_memory_metrics_user_id`), `task_type` (index=True, `ix_memory_metrics_task_type`)
- Foreign keys: `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/memory_trace.py`

#### MemoryTrace (`memory_traces`)
- Columns
- `id`: UUID, primary key
- `user_id`: String, nullable=False, index=True
- `title`: String, nullable=True
- `description`: Text, nullable=True
- `source`: String, nullable=True
- `extra`: JSONB, nullable=True
- `created_at`: DateTime, nullable=False, default=datetime.utcnow
- `updated_at`: DateTime, nullable=False, default=datetime.utcnow (onupdate)
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `user_id` (index=True, `ix_memory_traces_user_id`)
- Foreign keys: `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/memory_trace_node.py`

#### MemoryTraceNode (`memory_trace_nodes`)
- Columns
- `id`: UUID, primary key
- `trace_id`: UUID, ForeignKey(memory_traces.id), nullable=False, index=True
- `node_id`: UUID, ForeignKey(memory_nodes.id), nullable=False, index=True
- `position`: Integer, nullable=False
- `created_at`: DateTime, nullable=False, default=datetime.utcnow
- Primary key: `id`
- Unique constraints: `uq_trace_position` on (`trace_id`, `position`)
- Indexes: `trace_id` (index=True, `ix_memory_trace_nodes_trace_id`), `node_id` (index=True, `ix_memory_trace_nodes_node_id`)
- Foreign keys: `trace_id -> memory_traces.id`, `node_id -> memory_nodes.id`
- Relationships: None

### `AINDY/db/models/metrics_models.py`

#### Engagement (`engagements`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `likes`: Integer, nullable: not explicitly set
- `shares`: Integer, nullable: not explicitly set
- `comments`: Integer, nullable: not explicitly set
- `clicks`: Integer, nullable: not explicitly set
- `time_on_page`: Float, nullable: not explicitly set
- `total_views`: Integer, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True)
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### AIEfficiency (`ai_efficiencies`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `ai_contributions`: Integer, nullable: not explicitly set
- `human_contributions`: Integer, nullable: not explicitly set
- `total_tasks`: Integer, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### Impact (`impacts`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `reach`: Integer, nullable: not explicitly set
- `engagement`: Integer, nullable: not explicitly set
- `conversion`: Integer, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### Efficiency (`efficiencies`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `focused_effort`: Float, nullable: not explicitly set
- `ai_utilization`: Float, nullable: not explicitly set
- `time`: Float, nullable: not explicitly set
- `capital`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### RevenueScaling (`revenue_scalings`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `ai_leverage`: Float, nullable: not explicitly set
- `content_distribution`: Float, nullable: not explicitly set
- `time`: Float, nullable: not explicitly set
- `audience_engagement`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### ExecutionSpeed (`execution_speeds`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `ai_automations`: Float, nullable: not explicitly set
- `systemized_workflows`: Float, nullable: not explicitly set
- `decision_lag`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### AttentionValue (`attention_values`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `content_output`: Float, nullable: not explicitly set
- `platform_presence`: Float, nullable: not explicitly set
- `time`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### EngagementRate (`engagement_rates`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `total_interactions`: Float, nullable: not explicitly set
- `total_views`: Integer, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### BusinessGrowth (`business_growths`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `revenue`: Float, nullable: not explicitly set
- `expenses`: Float, nullable: not explicitly set
- `scaling_friction`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### MonetizationEfficiency (`monetization_efficiencies`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `total_revenue`: Float, nullable: not explicitly set
- `audience_size`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### AIProductivityBoost (`ai_productivity_boosts`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `tasks_with_ai`: Float, nullable: not explicitly set
- `tasks_without_ai`: Float, nullable: not explicitly set
- `time_saved`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### LostPotential (`lost_potentials`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `missed_opportunities`: Float, nullable: not explicitly set
- `time_delayed`: Float, nullable: not explicitly set
- `gains_from_action`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### DecisionEfficiency (`decision_efficiencies`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `automated_decisions`: Float, nullable: not explicitly set
- `manual_decisions`: Float, nullable: not explicitly set
- `processing_time`: Float, nullable: not explicitly set
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`
- Foreign keys: `user_id -> users.id`
- Relationships: None

#### CanonicalMetricDB (`canonical_metrics`)
- Table args
- `UniqueConstraint` on (`masterplan_id`, `platform`, `scope_type`, `scope_id`, `period_type`, `period_start`) named `uq_canonical_period_scope`
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `masterplan_id`: Integer, ForeignKey("master_plans.id"), nullable=False
- `user_id`: UUID, ForeignKey("users.id"), nullable=True, index=True
- `platform`: String, nullable: not explicitly set
- `scope_type`: String, nullable: not explicitly set
- `scope_id`: String, nullable=True
- `period_type`: String, nullable: not explicitly set
- `period_start`: Date, nullable: not explicitly set
- `period_end`: Date, nullable: not explicitly set
- `created_at`: DateTime, nullable: not explicitly set, default=datetime.utcnow
- `passive_visibility`: Float, nullable: not explicitly set
- `active_discovery`: Float, nullable: not explicitly set
- `unique_reach`: Float, nullable: not explicitly set
- `interaction_volume`: Float, nullable: not explicitly set
- `deep_attention_units`: Float, nullable: not explicitly set
- `intent_signals`: Float, nullable: not explicitly set
- `conversion_events`: Float, nullable: not explicitly set
- `growth_velocity`: Float, nullable: not explicitly set
- `audience_quality_score`: Float, nullable: not explicitly set
- `interaction_rate`: Float, nullable: not explicitly set
- `attention_rate`: Float, nullable: not explicitly set
- `intent_rate`: Float, nullable: not explicitly set
- `conversion_rate`: Float, nullable: not explicitly set
- `discovery_ratio`: Float, nullable: not explicitly set
- `growth_rate`: Float, nullable: not explicitly set
- Primary key: `id`
- Unique constraints: `uq_canonical_period_scope`
- Indexes: `id` (index=True), `user_id` (index=True, `ix_canonical_metrics_user_id`)
- Foreign keys: `masterplan_id -> master_plans.id`, `user_id -> users.id`
- Relationships: Not explicitly defined in current implementation.

### `AINDY/db/models/research_results.py`

#### ResearchResult (`research_results`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `query`: String, nullable=False
- `summary`: Text, nullable=True
- `source`: String, nullable=True
- `data`: JSON (postgresql JSON), nullable=True
- `created_at`: DateTime, nullable: not explicitly set, default=func.now()
- `user_id`: UUID, ForeignKey("users.id"), nullable=True, index=True — **added Sprint 5 (2026-03-18)** for per-user data isolation
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `user_id` (index=True, `ix_research_results_user_id`)
- Foreign keys: `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/system_health_log.py`

#### SystemHealthLog (`system_health_logs`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `timestamp`: DateTime, nullable: not explicitly set, default=datetime.utcnow
- `status`: String(50), nullable: not explicitly set
- `components`: JSON, nullable: not explicitly set
- `api_endpoints`: JSON, nullable: not explicitly set
- `avg_latency_ms`: Float, nullable: not explicitly set
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True)
- Foreign keys: `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/request_metric.py`

#### RequestMetric (`request_metrics`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `request_id`: String, nullable=True, index=True
- `user_id`: UUID, nullable=True, index=True
- `method`: String, nullable=False
- `path`: String, nullable=False, index=True
- `status_code`: Integer, nullable=False
- `duration_ms`: Float, nullable=False
- `created_at`: DateTime, nullable: not explicitly set, default=datetime.utcnow
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id` (index=True), `request_id` (index=True, `ix_request_metrics_request_id`), `user_id` (index=True, `ix_request_metrics_user_id`), `path` (index=True, `ix_request_metrics_path`), `created_at` (index=True, `ix_request_metrics_created_at`), `(path, created_at)` (index `ix_request_metrics_path_created_at`)
- Foreign keys: `user_id -> users.id`
- Relationships: None

### `AINDY/db/models/task.py`

#### Task (`tasks`)
- Columns
- `id`: Integer, primary key, index=True, nullable: not explicitly set (primary key implies non-null)
- `name`: String, nullable=False, index=True
- `category`: String, nullable: not explicitly set, default="general"
- `priority`: String, nullable: not explicitly set, default="medium"
- `status`: String, nullable: not explicitly set, default="pending"
- `due_date`: DateTime, nullable=True
- `start_time`: DateTime, nullable=True
- `end_time`: DateTime, nullable=True
- `duration`: Float, nullable: not explicitly set, default=0.0
- `scheduled_time`: DateTime, nullable=True
- `reminder_time`: DateTime, nullable=True
- `recurrence`: String, nullable=True
- `time_spent`: Float, nullable: not explicitly set, default=0.0
- `task_complexity`: Integer, nullable: not explicitly set, default=1
- `skill_level`: Integer, nullable: not explicitly set, default=1
- `ai_utilization`: Integer, nullable: not explicitly set, default=0
- `task_difficulty`: Integer, nullable: not explicitly set, default=1
- `user_id`: UUID, nullable=True, index=True
- Primary key: `id`
- Unique constraints: Not explicitly defined in current implementation.
- Indexes: `id`, `name` (index=True), `user_id` (index=True, `ix_tasks_user_id`)
- Foreign keys: `user_id -> users.id`
- Relationships: `user = relationship("User", back_populates="tasks")`

### `AINDY/db/models/user.py`

#### User (`users`)
- Columns
- `id`: UUID (postgresql UUID), primary key, default=uuid.uuid4, nullable: not explicitly set (primary key implies non-null)
- `email`: String, unique=True, index=True, nullable=False
- `username`: String, unique=True, index=True, nullable=True
- `hashed_password`: String, nullable=False
- `is_active`: Boolean, nullable=False, default=True
- `created_at`: DateTime(timezone=True), nullable: not explicitly set, server_default=func.now()
- Primary key: `id`
- Unique constraints: `email` (unique=True), `username` (unique=True)
- Indexes: `email` (index=True), `username` (index=True)
- Foreign keys: `user_id -> users.id`
- Relationships: None
- Purpose: Stores authenticated application users. Created by `register_user()` in `AINDY/services/auth_service.py`. Password is stored as a bcrypt hash; plaintext is never persisted.

### `AINDY/db/models/user_identity.py`

#### UserIdentity (`user_identity`)
- Table args
- `UniqueConstraint` on (`user_id`) named `uq_user_identity_user`
- Columns
- `id`: String, primary key, default: uuid.uuid4 (stringified), nullable: not explicitly set (primary key implies non-null)
- `user_id`: String, ForeignKey("users.id"), nullable=False, unique=True, index=True
- `tone`: String, nullable=True
- `communication_notes`: Text, nullable=True
- `preferred_languages`: JSON, nullable: not explicitly set, default=list
- `preferred_tools`: JSON, nullable: not explicitly set, default=list
- `avoided_tools`: JSON, nullable: not explicitly set, default=list
- `risk_tolerance`: String, nullable=True
- `speed_vs_quality`: String, nullable=True
- `decision_notes`: Text, nullable=True
- `learning_style`: String, nullable=True
- `detail_preference`: String, nullable=True
- `learning_notes`: Text, nullable=True
- `observation_count`: Integer, nullable: not explicitly set, default=0
- `last_updated`: DateTime(timezone=True), nullable=True
- `evolution_log`: JSON, nullable: not explicitly set, default=list
- `created_at`: DateTime(timezone=True), nullable: not explicitly set, server_default=func.now()
- Primary key: `id`
- Unique constraints: `uq_user_identity_user` (user_id unique)
- Indexes: `user_id` (index=True)
- Foreign keys: `user_id -> users.id`
- Relationships: None
- Purpose: Stores per-user identity preferences and evolution history inferred by `IdentityService`.

### `AINDY/db/models/social_models.py`
- Not an ORM module. Defines Pydantic models only (`SocialProfile`, `SocialPost`, `Connection`, `FeedItem`).
- No SQLAlchemy tables are declared in this file.

## 2. Relationship Mapping

Only relationships declared via SQLAlchemy `relationship()` are listed.

- ARMRun (`arm_runs`) 1-to-many ARMLog (`arm_logs`) via `ARMRun.logs` / `ARMLog.run`.
- FreelanceOrder (`freelance_orders`) 1-to-many ClientFeedback (`client_feedback`) via `ClientFeedback.order` with `backref="feedback"`.
- MasterPlan (`master_plans`) self-referential many-to-one via `MasterPlan.parent` (child points to parent via `parent_id`).
- MasterPlan (`master_plans`) 1-to-many CanonicalMetricDB (`canonical_metrics`) via `MasterPlan.canonical_metrics` with `backref="masterplan"`.
- User (`users`) 1-to-many Task (`tasks`) via `User.tasks` / `Task.user`.
- No many-to-many relationships are explicitly defined.

## 3. Alembic Migration Alignment

**Phase 2 migration (2026-03-18):**
- `mb2embed0001` — `memory_bridge_phase2_embedding_column`: adds `embedding VECTOR(1536)` to `memory_nodes`, enables pgvector extension. Applied at `alembic upgrade head`. Current head: `mb2embed0001`.

**Sprint 5 migration (2026-03-18):**
- `d37ae6ebc319` — `sprint5_user_id_freelance_research_rippletrace`: adds `user_id` (String, nullable, indexed) to 5 tables: `freelance_orders`, `client_feedback`, `research_results`, `drop_points`, `pings`. Applied at `alembic upgrade head`.

**Memory Bridge v3 migration (2026-03-18):**
- `dc59c589ab1e` - `memory_bridge_v3_history_table`: adds `memory_node_history` table (append-only change log) with index on (`node_id`, `changed_at`).
- `edc8c8d84cbb` - `repair_memory_nodes_tsv_trigger_drift`: removes stale `content_tsv` trigger/function/index drift from `memory_nodes` on upgraded databases.

**Memory Bridge v4 migration (2026-03-18):**
- `5b14b05e179f` - `memory_bridge_v4_feedback_columns`: adds feedback columns to `memory_nodes` (`success_count`, `failure_count`, `usage_count`, `last_used_at`, `last_outcome`, `weight`).

**Identity Layer migration (2026-03-19):**
- `bb4935e07dec` - `identity_layer_v5_phase2`: adds `user_identity` table (one row per user) with preference dimensions and evolution tracking.

**Memory Bridge v5 Phase 3 migration (2026-03-19):**
- `a2ec23964f2c` - `multi_agent_memory_v5_phase3`: adds `agents` table, adds `source_agent` + `is_shared` columns to `memory_nodes`, seeds system agents.

**Memory Metrics migration (2026-03-21):**
- `7c12f8c9a1b4` - `add_memory_metrics_table`: adds `memory_metrics` table with per-run impact metrics.

**Data ownership migration (2026-03-21):**
- `64b531720229` - `add_user_id_to_tasks_leadgen_authors`: adds `user_id` to `tasks`, `leadgen_results`, and `authors` for ownership scoping.

**Bridge user events migration (2026-03-21):**
- `cb417760d319` - `add_bridge_user_events`: adds `bridge_user_events` table for persisted `/bridge/user_event` audit trail.

**Auth identity cleanup + request metrics (2026-03-22):**
- `b7c8d9e0f1a2` - `auth_identity_cleanup_and_request_metrics`: adds `request_metrics` table and converts `genesis_sessions.user_id` + `canonical_metrics.user_id` to UUID with FK to `users.id`.

**Masterplan version cleanup (2026-03-22):**
- `c4f2a9d1e7b3` - `drop_masterplan_version_column`: removes redundant `master_plans.version` column.

**Request metrics index improvement (2026-03-22):**
- `d2a7f4c1b9e8` - `add_request_metrics_indexes`: adds `created_at` and `(path, created_at)` indexes for request metrics queries.

**Ownership UUID normalization (2026-03-22):**
- `2359cded7445` - `normalize_user_id_uuid`: converts `user_id` columns to UUID and adds FKs on `research_results`, `freelance_orders`, `client_feedback`, `drop_points`, `pings` (invalid UUIDs set to NULL before cast).

**Nodus scheduled jobs migration (2026-04-01):**
- Adds `nodus_scheduled_jobs` table: `id`, `name`, `user_id`, `flow_name`, `cron_expr`, `state`, `last_run_at`, `next_run_at`, `is_active`, `created_at`.

**Nodus trace events migration (2026-04-01):**
- Adds `nodus_trace_events` table: `id`, `execution_id`, `node_name`, `event_type`, `payload`, `created_at`.

**OS Isolation Layer migration (2026-04-01):**
- Adds 6 columns to `execution_units`: `tenant_id` (String), `cpu_time_ms` (Integer, default 0), `memory_bytes` (Integer, default 0), `syscall_count` (Integer, default 0), `priority` (Integer, default 5), `quota_group` (String, default `"default"`).

**Platform API key migration (2026-03-31):**
- Adds `platform_api_keys` table: `id`, `user_id`, `name`, `key_prefix`, `key_hash`, `scopes` (JSONB), `expires_at`, `last_used_at`, `is_active`, `created_at`.

**Dynamic registry persistence migrations (2026-03-31):**
- Adds `dynamic_flows`, `dynamic_nodes`, `webhook_subscriptions` tables for persistent platform registry.

**Memory Address Space (MAS) migration (2026-04-01):**
- `g5h6i7j8k9l0` - `add_memory_address_space_columns`: adds `path` String(512), `namespace` String(128), `addr_type` String(128), `parent_path` String(512) to `memory_nodes`. All nullable, all indexed.

> **Migration Reminder:** Always run `alembic upgrade head` immediately after any SQLAlchemy model change. SQLAlchemy models alone do not alter the live database — migrations must be applied explicitly.



Migration filenames exist in `AINDY/alembic/versions/`, but alignment requires a migration diff check. The following filename matches suggest possible related migrations:

- `arm_runs`, `arm_logs`, `arm_configs`: `0cea8869744b_add_arm_models.py`, `8e2909eee86c_add_arm_models.py`, `8addbdf88330_add_deepseek_arm_tables.py`, `bad4f7003aa5_register_arm_tables_properly.py`
- `authors`: `51b6f9f455d1_add_authors_table.py`, `72724b428ba5_add_authors_table.py`, `7abafedb7e1e_register_authordb_properly.py`
- `calculation_results`: Not explicitly identified by filename. Verification requires migration diff check.
- `drop_points`, `pings`: Not explicitly identified by filename. Verification requires migration diff check.
- `freelance_orders`, `client_feedback`, `revenue_metrics`: `717f7034ec27_add_freelance_automation_tables.py`, `825fc6015dda_add_freelance_automation_tables.py`, `05502a7f9fe8_regenerate_freelance_automation_tables.py`
- `leadgen_results`: `4cc6abbb35cb_add_leadgen_results_table.py`
- `master_plans`: `1a085e32efd4_add_master_plans_table.py`, `ae693412325e_add_master_plans_table.py`, `b72d3989ae01_masterplan.py`, `af746d976e73_add_activated_at.py`, `390e474b9ff0_extend_masterplan_for_genesis_lock.py`
- `genesis_sessions`: `0ffe8ba14fb8_add_genesis_session_model.py`
- `canonical_metrics`: `4021f10066c3_add_canonical_metrics_telemetry_table.py`
- `metrics_models` (engagement, etc.): `94bcd9284285_move_metrics_models_to_db_models.py` appears related by filename only
- `research_results`: `4e392d916569_add_research_results_table.py`, `64872a402355_add_research_results_table.py`, `8b57835a640c_add_research_results_table.py`, `ec0e78e6e306_align_researchresult_schema_with_.py`
- `system_health_logs`: `03adbb4b957b_add_system_health_logs_table.py`, `e52a1f667323_add_system_health_logs_table.py`
- `request_metrics`: `b7c8d9e0f1a2_auth_identity_cleanup_and_request_metrics.py`
- `users`: `37f972780d54_create_users_table.py` — applied; head revision as of Phase 3 security implementation.

Alignment for each model cannot be confirmed from static inspection alone; verification requires a migration diff check against the current ORM metadata.

## 4. MongoDB Collections

MongoDB usage is implemented in `AINDY/db/mongo_setup.py`, `AINDY/routes/social_router.py`, and `AINDY/services/task_services.py`.

### Collections and Observed Document Structure

- `profiles` collection
- Inserted/updated in `AINDY/routes/social_router.py`.
- Document structure from `SocialProfile` (`AINDY/db/models/social_models.py`):
- `id` (string UUID)
- `username` (string)
- `tagline` (string, optional)
- `bio` (string, optional)
- `metrics_snapshot` (object with `twr_score`, `trust_score`, `execution_velocity`)
- `tags` (array of strings)
- `joined_at` (datetime)
- `updated_at` (datetime)
- Updated in `AINDY/services/task_services.py`:
- `$inc` on `metrics_snapshot.execution_velocity` and `metrics_snapshot.twr_score`
- `$set` `updated_at`

- `posts` collection
- Inserted in `AINDY/routes/social_router.py`.
- Document structure from `SocialPost` (`AINDY/db/models/social_models.py`):
- `id`, `author_id`, `author_username`, `content`, `media_url`, `tags`, `trust_tier_required`, `likes`, `boosts`, `comments_count`, `created_at`, `ai_context`

No schema validation is defined in current implementation.

## 5. Memory Bridge Schema

Defined in `AINDY/services/memory_persistence.py`.

### `memory_nodes`
- Model: `MemoryNodeModel`
- Columns
- `id`: UUID (postgresql UUID), primary key, default=uuid.uuid4
- `content`: Text, nullable=False
- `tags`: JSONB, nullable=False, default=list
- `node_type`: String(50), nullable=False
- `source`: String(255), nullable=True
- `source_agent`: String, nullable=True
- `is_shared`: Boolean, nullable=False, default=False
- `user_id`: String(255), nullable=True
- `created_at`: DateTime, nullable=False, server_default=func.now()
- `updated_at`: DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
- `extra`: JSONB, nullable=False, default=dict
- `embedding`: Vector(1536), nullable=True — **added Memory Bridge Phase 2** (migration `mb2embed0001`)
- `success_count`: Integer, nullable=False, default=0
- `failure_count`: Integer, nullable=False, default=0
- `usage_count`: Integer, nullable=False, default=0
- `last_used_at`: DateTime(timezone=True), nullable=True
- `last_outcome`: String, nullable=True
- `weight`: Float, nullable=False, default=1.0
- `path`: String(512), nullable=True, index=True — **added MAS sprint (2026-04-01)** full MAS path `/memory/{tenant}/{namespace}/{addr_type}/{node_id}`
- `namespace`: String(128), nullable=True, index=True — **added MAS sprint (2026-04-01)** logical namespace segment
- `addr_type`: String(128), nullable=True, index=True — **added MAS sprint (2026-04-01)** type segment (named `addr_type` to avoid Python `type` keyword collision)
- `parent_path`: String(512), nullable=True, index=True — **added MAS sprint (2026-04-01)** parent path for tree queries
- Indexes
- `ix_memory_nodes_tags_gin` on `tags` using GIN
- `ix_memory_nodes_source_agent` on `source_agent`
- `ix_memory_nodes_path` on `path` (added migration `g5h6i7j8k9l0`)
- `ix_memory_nodes_namespace` on `namespace` (added migration `g5h6i7j8k9l0`)
- `ix_memory_nodes_addr_type` on `addr_type` (added migration `g5h6i7j8k9l0`)
- `ix_memory_nodes_parent_path` on `parent_path` (added migration `g5h6i7j8k9l0`)
- Unique constraints: Not explicitly defined in current implementation.
- Node type enforcement: `VALID_NODE_TYPES = {"decision", "outcome", "insight", "relationship"}` validated by SQLAlchemy `before_insert` / `before_update` event listener in `services/memory_persistence.py`. Non-null `node_type` values outside this set raise `ValueError` at ORM layer.
- pgvector extension required: `CREATE EXTENSION IF NOT EXISTS vector` (included in migration `mb2embed0001`).

### `memory_links`
- Model: `MemoryLinkModel`
- Columns
- `id`: UUID (postgresql UUID), primary key, default=uuid.uuid4
- `source_node_id`: UUID, ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False
- `target_node_id`: UUID, ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False
- `link_type`: String(50), nullable=False
- `strength`: String(20), nullable=False, default="medium"
- `weight`: Float, nullable=False, default=0.5
- `created_at`: DateTime, nullable=False, server_default=func.now()
- Indexes
- `ix_memory_links_source` on `source_node_id`
- `ix_memory_links_target` on `target_node_id`
- `uq_memory_links_unique` unique index on (`source_node_id`, `target_node_id`, `link_type`)
- Link-type constraints: Not explicitly defined in current implementation.

### `memory_metrics`
- Model: `MemoryMetric` (`AINDY/db/models/memory_metrics.py`)
- Columns
- `id`: Integer, primary key
- `user_id`: String, nullable=False, index=True
- `task_type`: String, nullable=True, index=True
- `impact_score`: Float, nullable=False, default=0.0
- `memory_count`: Integer, nullable=False, default=0
- `avg_similarity`: Float, nullable=False, default=0.0
- `created_at`: DateTime, nullable=False, server_default=func.now()

### `memory_node_history`
- Model: `MemoryNodeHistory` (`AINDY/db/models/memory_node_history.py`)
- Columns
  - `id`: String, primary key, default `uuid.uuid4()`
  - `node_id`: UUID, ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False, index=True
  - `changed_at`: DateTime(timezone=True), server_default=func.now(), nullable=False
  - `changed_by`: String, nullable=True
  - `previous_content`: Text, nullable=True
  - `previous_tags`: JSON, nullable=True
  - `previous_node_type`: String, nullable=True
  - `previous_source`: String, nullable=True
  - `change_type`: String, nullable=False
  - `change_summary`: Text, nullable=True
- Indexes
  - `ix_memory_node_history_node_changed` on (`node_id`, `changed_at`)
- Purpose: Append-only change history for MemoryNode updates (stores previous values only).

## 5.5 Symbolic Ingest (Operational)

- Ingest service: `AINDY/services/memory_ingest_service.py` reads `memorytraces/` and `memoryevents/` files, creates `memory_traces`, `memory_trace_nodes`, and `memory_nodes` with provenance in `extra`.

## 6. Cross-Database Boundaries

- PostgreSQL is used by all SQLAlchemy ORM models in `AINDY/db/models/` and by Memory Bridge models in `AINDY/services/memory_persistence.py`.
- MongoDB is used by the Social Layer in `AINDY/routes/social_router.py` and by task completion logic in `AINDY/services/task_services.py`.
- Cross-database coordination occurs in:
- `AINDY/routes/social_router.py`: writes to MongoDB (`posts`) and uses `memory.memory_capture_engine.MemoryCaptureEngine` to persist related memory records into PostgreSQL when social content or performance signals should be captured.
- `AINDY/services/task_services.py`: writes to PostgreSQL `tasks` and updates MongoDB `profiles` metrics snapshot.

## 7. Known Structural Risks

- Missing foreign keys:
- Many models have no foreign keys and rely on application logic only (e.g., `calculation_results`, `tasks`, most metrics tables).
- Lack of cascades:
- Cascades are defined only for `ARMRun.logs` and `MasterPlan.canonical_metrics`. Other related data (e.g., `DropPointDB` -> `PingDB`) has no cascade configuration at ORM level.
- Unindexed lookup fields:
- No explicit indexes beyond `index=True` on select columns; GIN index exists only on `memory_nodes.tags`.
- Potential migration drift:
- Multiple overlapping migration filenames suggest possible historical drift; alignment requires migration diff checks.
- Implicit constraints enforced only in application logic:
- Examples include Memory Bridge JWT validation (`AINDY/routes/bridge_router.py`) and genesis session locking (`AINDY/services/masterplan_factory.py`).





