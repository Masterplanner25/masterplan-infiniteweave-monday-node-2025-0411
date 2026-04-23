"""
Tests for services/syscall_handlers.py — domain syscall handler implementations.

Groups
------
A  register_all_domain_handlers()         (4 tests)
B  task domain handlers                   (8 tests)
C  leadgen domain handlers                (5 tests)
D  arm domain handlers                    (5 tests)
E  genesis domain handlers                (5 tests)
F  score domain handlers                  (5 tests)
G  watcher domain handlers                (4 tests)
H  goal domain handlers                   (3 tests)
I  research + agent domain handlers       (5 tests)

Testing strategy:
  Handlers use lazy imports (inside function bodies). We mock the modules
  they import via patch.dict("sys.modules", {...}) so the handler gets our
  mock objects instead of real DB/service calls.
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch, call

import pytest

from AINDY.kernel.syscall_registry import SyscallContext, SYSCALL_REGISTRY


# ── Helpers ───────────────────────────────────────────────────────────────────

_TEST_UUID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


def _ctx(**kwargs) -> SyscallContext:
    defaults = dict(
        execution_unit_id="eu-test",
        user_id=_TEST_UUID,
        capabilities=[],
        trace_id="eu-test",
    )
    defaults.update(kwargs)
    return SyscallContext(**defaults)


def _make_db_modules(session_instance=None):
    """Return a minimal sys.modules patch for db.database."""
    if session_instance is None:
        session_instance = MagicMock()
    db_database = MagicMock()
    db_database.SessionLocal.return_value = session_instance
    return {"db.database": db_database}


# ═══════════════════════════════════════════════════════════════════════════════
# A: register_all_domain_handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegisterAllDomainHandlers:
    def test_registers_handlers(self):
        from AINDY.kernel.syscall_handlers import register_all_domain_handlers
        register_all_domain_handlers()
        domain_syscalls = [k for k in SYSCALL_REGISTRY if k not in (
            "sys.v1.memory.read", "sys.v1.memory.write", "sys.v1.memory.search",
            "sys.v1.flow.run", "sys.v1.event.emit",
        )]
        # 20 original + 3 MAS handlers (memory.list, memory.tree, memory.trace)
        assert len(domain_syscalls) >= 23

    def test_all_expected_names_registered(self):
        from AINDY.kernel.syscall_handlers import register_all_domain_handlers
        register_all_domain_handlers()
        expected = [
            "sys.v1.task.create", "sys.v1.task.complete", "sys.v1.task.complete_full",
            "sys.v1.task.start", "sys.v1.task.pause", "sys.v1.task.orchestrate",
            "sys.v1.leadgen.search", "sys.v1.leadgen.search_ai", "sys.v1.leadgen.store",
            "sys.v1.arm.analyze", "sys.v1.arm.generate", "sys.v1.arm.store",
            "sys.v1.genesis.execute_llm", "sys.v1.genesis.message",
            "sys.v1.score.recalculate", "sys.v1.score.feedback",
            "sys.v1.watcher.ingest",
            "sys.v1.goal.create",
            "sys.v1.research.query",
            "sys.v1.agent.suggest_tools",
        ]
        for name in expected:
            assert name in SYSCALL_REGISTRY, f"Missing: {name}"

    def test_idempotent_registration(self):
        from AINDY.kernel.syscall_handlers import register_all_domain_handlers
        register_all_domain_handlers()
        count_after_first = len(SYSCALL_REGISTRY)
        register_all_domain_handlers()
        assert len(SYSCALL_REGISTRY) == count_after_first

    def test_entries_have_handler_and_capability(self):
        from AINDY.kernel.syscall_handlers import register_all_domain_handlers
        register_all_domain_handlers()
        entry = SYSCALL_REGISTRY["sys.v1.task.create"]
        assert callable(entry.handler)
        assert entry.capability == "task.create"


# ═══════════════════════════════════════════════════════════════════════════════
# B: task domain handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskHandlers:
    def test_task_create_returns_task_fields(self):
        from AINDY.kernel.syscall_handlers import _handle_task_create

        mock_task = MagicMock()
        mock_task.id = "tid-1"
        mock_task.name = "Write tests"
        mock_task.category = "dev"
        mock_task.priority = "high"
        mock_task.time_spent = 0
        mock_task.masterplan_id = None
        mock_task.parent_task_id = None
        mock_task.depends_on = []
        mock_task.dependency_type = "hard"
        mock_task.automation_type = None
        mock_task.automation_config = None
        mock_task.status = "active"
        mock_db = MagicMock()
        mock_task_svc = MagicMock(create_task=MagicMock(return_value=mock_task))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.tasks.services.task_service": mock_task_svc,
            "apps.tasks.services.task_service": mock_task_svc,
        }):
            result = _handle_task_create({"task_name": "Write tests"}, _ctx())

        assert result["task_id"] == "tid-1"
        assert result["task_name"] == "Write tests"
        assert result["category"] == "dev"

    def test_task_create_raises_on_missing_name(self):
        from AINDY.kernel.syscall_handlers import _handle_task_create
        with pytest.raises(ValueError, match="requires 'task_name'"):
            _handle_task_create({}, _ctx())

    def test_task_create_accepts_name_key(self):
        from AINDY.kernel.syscall_handlers import _handle_task_create

        mock_task = MagicMock()
        mock_task.id = "tid-2"
        mock_task.name = "Review PR"
        mock_task.category = "general"
        mock_task.priority = "medium"
        mock_task.time_spent = 0
        mock_task.masterplan_id = None
        mock_task.parent_task_id = None
        mock_task.depends_on = []
        mock_task.dependency_type = "hard"
        mock_task.automation_type = None
        mock_task.automation_config = None
        mock_task.status = "active"
        mock_db = MagicMock()
        mock_task_svc = MagicMock(create_task=MagicMock(return_value=mock_task))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.tasks.services.task_service": mock_task_svc,
            "apps.tasks.services.task_service": mock_task_svc,
        }):
            result = _handle_task_create({"name": "Review PR"}, _ctx())

        assert result["task_name"] == "Review PR"

    def test_task_complete_returns_task_result(self):
        from AINDY.kernel.syscall_handlers import _handle_task_complete

        mock_db = MagicMock()
        mock_task_svc = MagicMock(complete_task=MagicMock(return_value={"completed": True}))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.tasks.services.task_service": mock_task_svc,
            "apps.tasks.services.task_service": mock_task_svc,
        }):
            result = _handle_task_complete({"task_name": "Write tests"}, _ctx())

        assert result["task_result"] == {"completed": True}

    def test_task_complete_raises_on_missing_name(self):
        from AINDY.kernel.syscall_handlers import _handle_task_complete
        with pytest.raises(ValueError):
            _handle_task_complete({}, _ctx())

    def test_task_complete_full_returns_service_result(self):
        from AINDY.kernel.syscall_handlers import _handle_task_complete_full

        mock_db = MagicMock()
        svc_result = {"status": "done", "score_delta": 5}
        mock_task_svc = MagicMock(execute_task_completion=MagicMock(return_value=svc_result))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.tasks.services.task_service": mock_task_svc,
            "apps.tasks.services.task_service": mock_task_svc,
        }):
            result = _handle_task_complete_full({"task_name": "Write tests"}, _ctx())

        assert result == svc_result

    def test_task_start_returns_message(self):
        from AINDY.kernel.syscall_handlers import _handle_task_start

        mock_db = MagicMock()
        mock_task_svc = MagicMock(start_task=MagicMock(return_value="Task started"))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.tasks.services.task_service": mock_task_svc,
            "apps.tasks.services.task_service": mock_task_svc,
        }):
            result = _handle_task_start({"task_name": "Write tests"}, _ctx())

        assert result["task_start_result"]["message"] == "Task started"

    def test_task_pause_returns_message(self):
        from AINDY.kernel.syscall_handlers import _handle_task_pause

        mock_db = MagicMock()
        mock_task_svc = MagicMock(pause_task=MagicMock(return_value="Task paused"))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.tasks.services.task_service": mock_task_svc,
            "apps.tasks.services.task_service": mock_task_svc,
        }):
            result = _handle_task_pause({"task_name": "Write tests"}, _ctx())

        assert result["task_pause_result"]["message"] == "Task paused"


# ═══════════════════════════════════════════════════════════════════════════════
# C: leadgen domain handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeadgenHandlers:
    def test_leadgen_search_returns_serialized_results(self):
        from AINDY.kernel.syscall_handlers import _handle_leadgen_search

        mock_lead = MagicMock(
            company="Acme", url="https://acme.com", fit_score=0.9,
            intent_score=0.8, data_quality_score=0.7, overall_score=0.85,
            reasoning="Good fit",
        )
        mock_lead.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01"))
        mock_db = MagicMock()
        mock_leadgen_svc = MagicMock(
            create_lead_results=MagicMock(return_value=[(mock_lead, 0.95)])
        )

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.search.services.leadgen_service": mock_leadgen_svc,
            "apps.search.services.leadgen_service": mock_leadgen_svc,
        }):
            result = _handle_leadgen_search({"query": "fintech startup"}, _ctx())

        assert result["count"] == 1
        assert result["search_results"][0]["company"] == "Acme"

    def test_leadgen_search_raises_on_empty_query(self):
        from AINDY.kernel.syscall_handlers import _handle_leadgen_search
        with pytest.raises(ValueError, match="requires 'query'"):
            _handle_leadgen_search({}, _ctx())

    def test_leadgen_search_ai_returns_leads(self):
        from AINDY.kernel.syscall_handlers import _handle_leadgen_search_ai

        mock_db = MagicMock()
        mock_svc = MagicMock(run_ai_search=MagicMock(return_value=[{"name": "Lead A"}]))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.search.services.leadgen_service": mock_svc,
            "apps.search.services.leadgen_service": mock_svc,
        }):
            result = _handle_leadgen_search_ai({"query": "saas companies"}, _ctx())

        assert result["count"] == 1
        assert result["leads"][0]["name"] == "Lead A"

    def test_leadgen_store_skips_memory_on_no_user(self):
        from AINDY.kernel.syscall_handlers import _handle_leadgen_store

        mock_db = MagicMock()
        mock_qmc = MagicMock()

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "core.execution_signal_helper": MagicMock(queue_memory_capture=mock_qmc),
            "AINDY.core.execution_signal_helper": MagicMock(queue_memory_capture=mock_qmc),
            "apps.search.services.search_service": MagicMock(persist_search_result=MagicMock()),
            "apps.search.services.search_service": MagicMock(persist_search_result=MagicMock()),
        }):
            result = _handle_leadgen_store(
                {"query": "test", "results": []},
                _ctx(user_id=""),
            )

        mock_qmc.assert_not_called()
        assert result["stored"] is True

    def test_leadgen_store_returns_count(self):
        from AINDY.kernel.syscall_handlers import _handle_leadgen_store

        mock_db = MagicMock()

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "core.execution_signal_helper": MagicMock(queue_memory_capture=MagicMock()),
            "AINDY.core.execution_signal_helper": MagicMock(queue_memory_capture=MagicMock()),
            "apps.search.services.search_service": MagicMock(persist_search_result=MagicMock()),
            "apps.search.services.search_service": MagicMock(persist_search_result=MagicMock()),
        }):
            result = _handle_leadgen_store(
                {"query": "test", "results": [{"name": "A"}, {"name": "B"}]},
                _ctx(),
            )

        assert result["count"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# D: arm domain handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestArmHandlers:
    def test_arm_analyze_returns_analysis_fields(self):
        from AINDY.kernel.syscall_handlers import _handle_arm_analyze

        mock_db = MagicMock()
        analysis_result = {
            "summary": "Looks good",
            "architecture_score": 8,
            "integrity_score": 7,
            "analysis_id": "ana-1",
        }
        mock_analyzer = MagicMock()
        mock_analyzer.run_analysis.return_value = analysis_result
        mock_deepseek = MagicMock(DeepSeekCodeAnalyzer=MagicMock(return_value=mock_analyzer))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.arm.services.deepseek.deepseek_code_analyzer": mock_deepseek,
        }):
            result = _handle_arm_analyze({"file_path": "app.py"}, _ctx())

        assert result["summary"] == "Looks good"
        assert result["architecture_score"] == 8
        assert result["analysis_id"] == "ana-1"

    def test_arm_analyze_raises_on_missing_file_path(self):
        from AINDY.kernel.syscall_handlers import _handle_arm_analyze
        with pytest.raises(ValueError, match="requires 'file_path'"):
            _handle_arm_analyze({}, _ctx())

    def test_arm_generate_returns_generated_code(self):
        from AINDY.kernel.syscall_handlers import _handle_arm_generate

        mock_db = MagicMock()
        gen_result = {
            "generated_code": "def foo(): pass",
            "explanation": "A function",
            "generation_id": "gen-1",
        }
        mock_analyzer = MagicMock()
        mock_analyzer.generate_code.return_value = gen_result
        mock_deepseek = MagicMock(DeepSeekCodeAnalyzer=MagicMock(return_value=mock_analyzer))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.arm.services.deepseek.deepseek_code_analyzer": mock_deepseek,
        }):
            result = _handle_arm_generate({"prompt": "write foo"}, _ctx())

        assert result["generated_code"] == "def foo(): pass"
        assert result["generation_id"] == "gen-1"

    def test_arm_generate_raises_on_missing_prompt(self):
        from AINDY.kernel.syscall_handlers import _handle_arm_generate
        with pytest.raises(ValueError, match="requires 'prompt'"):
            _handle_arm_generate({}, _ctx())

    def test_arm_store_returns_stored_true(self):
        from AINDY.kernel.syscall_handlers import _handle_arm_store

        mock_db = MagicMock()
        mock_qmc = MagicMock()

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "core.execution_signal_helper": MagicMock(queue_memory_capture=mock_qmc),
            "AINDY.core.execution_signal_helper": MagicMock(queue_memory_capture=mock_qmc),
        }):
            result = _handle_arm_store({"result": {"score": 8}}, _ctx())

        assert result["stored"] is True
        mock_qmc.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# E: genesis domain handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenesisHandlers:
    def test_genesis_execute_llm_returns_reply(self):
        from AINDY.kernel.syscall_handlers import _handle_genesis_execute_llm

        mock_session = MagicMock()
        mock_session.summarized_state = {"confidence": 0.5}
        mock_session.synthesis_ready = False

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        llm_output = {
            "reply": "Let's plan your goals.",
            "state_update": {"confidence": 0.7},
            "synthesis_ready": False,
        }
        mock_genesis_ai = MagicMock(call_genesis_llm=MagicMock(return_value=llm_output))
        mock_genesis_model = MagicMock()
        mock_genesis_model.GenesisSessionDB = MagicMock()

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.models": mock_genesis_model,
            "AINDY.db.models": mock_genesis_model,
            "apps.masterplan.services.genesis_ai": mock_genesis_ai,
            "apps.masterplan.services.genesis_ai": mock_genesis_ai,
        }):
            result = _handle_genesis_execute_llm(
                {"session_id": "sess-1", "message": "Plan my week"},
                _ctx(),
            )

        assert result["genesis_response"]["reply"] == "Let's plan your goals."

    def test_genesis_execute_llm_raises_on_missing_session_id(self):
        from AINDY.kernel.syscall_handlers import _handle_genesis_execute_llm
        with pytest.raises(ValueError, match="requires 'session_id'"):
            _handle_genesis_execute_llm({"message": "hello"}, _ctx())

    def test_genesis_execute_llm_raises_on_missing_message(self):
        from AINDY.kernel.syscall_handlers import _handle_genesis_execute_llm
        with pytest.raises(ValueError, match="requires 'message'"):
            _handle_genesis_execute_llm({"session_id": "sess-1"}, _ctx())

    def test_genesis_execute_llm_raises_on_session_not_found(self):
        from AINDY.kernel.syscall_handlers import _handle_genesis_execute_llm

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_genesis_model = MagicMock()
        mock_genesis_model.GenesisSessionDB = MagicMock()

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.models": mock_genesis_model,
            "AINDY.db.models": mock_genesis_model,
            "apps.masterplan.services.genesis_ai": MagicMock(),
            "apps.masterplan.services.genesis_ai": MagicMock(),
        }):
            with pytest.raises(ValueError, match="not found"):
                _handle_genesis_execute_llm(
                    {"session_id": "sess-x", "message": "hello"},
                    _ctx(),
                )

    def test_genesis_message_calls_execute_intent(self):
        from AINDY.kernel.syscall_handlers import _handle_genesis_message

        mock_db = MagicMock()
        intent_result = {"status": "completed", "reply": "Done"}
        mock_flow_engine = MagicMock(execute_intent=MagicMock(return_value=intent_result))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "runtime.flow_engine": mock_flow_engine,
            "AINDY.runtime.flow_engine": mock_flow_engine,
        }):
            result = _handle_genesis_message(
                {"session_id": "sess-1", "message": "Run plan"},
                _ctx(),
            )

        assert result == intent_result
        mock_flow_engine.execute_intent.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# F: score domain handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreHandlers:
    def test_score_recalculate_returns_score_data(self):
        from AINDY.kernel.syscall_handlers import _handle_score_recalculate

        mock_db = MagicMock()
        orch_result = {"score": {"master_score": 72.5}}
        mock_orch = MagicMock(execute=MagicMock(return_value=orch_result))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.analytics.services.infinity_orchestrator": mock_orch,
            "apps.analytics.services.infinity_orchestrator": mock_orch,
        }):
            result = _handle_score_recalculate({}, _ctx())

        assert result["score_recalculate_result"] == {"master_score": 72.5}

    def test_score_recalculate_raises_on_empty_result(self):
        from AINDY.kernel.syscall_handlers import _handle_score_recalculate

        mock_db = MagicMock()
        mock_orch = MagicMock(execute=MagicMock(return_value=None))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.analytics.services.infinity_orchestrator": mock_orch,
            "apps.analytics.services.infinity_orchestrator": mock_orch,
        }):
            with pytest.raises(ValueError, match="empty result"):
                _handle_score_recalculate({}, _ctx())

    def test_score_recalculate_uses_manual_trigger_by_default(self):
        from AINDY.kernel.syscall_handlers import _handle_score_recalculate

        mock_db = MagicMock()
        mock_execute = MagicMock(return_value={"score": {}})
        mock_orch = MagicMock(execute=mock_execute)

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.analytics.services.infinity_orchestrator": mock_orch,
            "apps.analytics.services.infinity_orchestrator": mock_orch,
        }):
            _handle_score_recalculate({}, _ctx())

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs.get("trigger_event") == "manual"

    def test_score_feedback_persists_and_returns_id(self):
        from AINDY.kernel.syscall_handlers import _handle_score_feedback

        mock_feedback_obj = MagicMock()
        mock_feedback_obj.id = "fb-123"

        mock_db = MagicMock()

        mock_user_feedback_cls = MagicMock(return_value=mock_feedback_obj)
        mock_infinity_loop = MagicMock(UserFeedback=mock_user_feedback_cls)

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.models.infinity_loop": mock_infinity_loop,
            "apps.automation.models": mock_infinity_loop,
        }):
            result = _handle_score_feedback(
                {"source_type": "manual", "feedback_value": 0.8},
                _ctx(),
            )

        assert result["score_feedback_result"]["id"] == "fb-123"
        mock_db.add.assert_called_once_with(mock_feedback_obj)
        mock_db.commit.assert_called_once()
        assert str(mock_user_feedback_cls.call_args.kwargs["user_id"]) == _TEST_UUID

    def test_score_feedback_ignores_payload_user_id(self):
        from AINDY.kernel.syscall_handlers import _handle_score_feedback

        mock_feedback_obj = MagicMock()
        mock_feedback_obj.id = "fb-123"
        mock_db = MagicMock()
        mock_user_feedback_cls = MagicMock(return_value=mock_feedback_obj)
        mock_infinity_loop = MagicMock(UserFeedback=mock_user_feedback_cls, LoopAdjustment=MagicMock())

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.models.infinity_loop": mock_infinity_loop,
            "apps.automation.models": mock_infinity_loop,
        }):
            _handle_score_feedback(
                {
                    "source_type": "manual",
                    "feedback_value": 1.0,
                    "user_id": "00000000-0000-0000-0000-000000000001",
                },
                _ctx(user_id=_TEST_UUID),
            )

        assert str(mock_user_feedback_cls.call_args.kwargs["user_id"]) == _TEST_UUID

    def test_score_feedback_rolls_back_on_error(self):
        from AINDY.kernel.syscall_handlers import _handle_score_feedback

        mock_db = MagicMock()
        mock_db.commit.side_effect = RuntimeError("DB error")

        mock_user_feedback_cls = MagicMock()
        mock_infinity_loop = MagicMock(UserFeedback=mock_user_feedback_cls)

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.models.infinity_loop": mock_infinity_loop,
            "apps.automation.models": mock_infinity_loop,
        }):
            with pytest.raises(RuntimeError):
                _handle_score_feedback({"source_type": "manual"}, _ctx())

        mock_db.rollback.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# G: watcher domain handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestWatcherHandlers:
    def _valid_signal(self):
        return {
            "signal_type": "app_focused",
            "activity_type": "coding",
            "timestamp": "2026-01-01T10:00:00Z",
            "session_id": "sess-1",
            "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        }

    def test_watcher_ingest_raises_on_empty_signals(self):
        from AINDY.kernel.syscall_handlers import _handle_watcher_ingest
        with pytest.raises(ValueError, match="requires non-empty 'signals'"):
            _handle_watcher_ingest({"signals": []}, _ctx())

    def test_watcher_ingest_raises_on_invalid_signal_type(self):
        from AINDY.kernel.syscall_handlers import _handle_watcher_ingest

        mock_db = MagicMock()
        mock_watcher_signal_mod = MagicMock()
        mock_watcher_contract = MagicMock(
            get_valid_signal_types=MagicMock(return_value={"app_focused", "session_ended"}),
            get_valid_activity_types=MagicMock(return_value={"coding"}),
            parse_signal_timestamp=MagicMock(return_value=None),
        )

        sig = self._valid_signal()
        sig["signal_type"] = "INVALID"

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.models.watcher_signal": mock_watcher_signal_mod,
            "AINDY.db.models.watcher_signal": mock_watcher_signal_mod,
            "AINDY.platform_layer.watcher_contract": mock_watcher_contract,
        }):
            with pytest.raises(ValueError, match="unknown signal_type"):
                _handle_watcher_ingest({"signals": [sig]}, _ctx())

    def test_watcher_ingest_persists_signals(self):
        from AINDY.kernel.syscall_handlers import _handle_watcher_ingest

        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_watcher_signal_mod = MagicMock(WatcherSignal=MagicMock(return_value=mock_row))
        mock_watcher_contract = MagicMock(
            get_valid_signal_types=MagicMock(return_value={"app_focused", "session_ended"}),
            get_valid_activity_types=MagicMock(return_value={"coding"}),
            parse_signal_timestamp=MagicMock(return_value=None),
        )

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.models.watcher_signal": mock_watcher_signal_mod,
            "AINDY.db.models.watcher_signal": mock_watcher_signal_mod,
            "AINDY.platform_layer.watcher_contract": mock_watcher_contract,
        }):
            result = _handle_watcher_ingest({"signals": [self._valid_signal()]}, _ctx())

        assert result["watcher_ingest_result"]["accepted"] == 1
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_watcher_ingest_counts_session_ended(self):
        from AINDY.kernel.syscall_handlers import _handle_watcher_ingest

        mock_db = MagicMock()
        mock_watcher_signal_mod = MagicMock(WatcherSignal=MagicMock(return_value=MagicMock()))
        mock_watcher_contract = MagicMock(
            get_valid_signal_types=MagicMock(return_value={"app_focused", "session_ended"}),
            get_valid_activity_types=MagicMock(return_value={"coding"}),
            parse_signal_timestamp=MagicMock(return_value=None),
        )

        sig1 = self._valid_signal()
        sig2 = {**self._valid_signal(), "signal_type": "session_ended"}

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.models.watcher_signal": mock_watcher_signal_mod,
            "AINDY.db.models.watcher_signal": mock_watcher_signal_mod,
            "AINDY.platform_layer.watcher_contract": mock_watcher_contract,
        }):
            result = _handle_watcher_ingest({"signals": [sig1, sig2]}, _ctx())

        assert result["watcher_ingest_result"]["session_ended_count"] == 1
        assert result["watcher_session_ended_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# H: goal domain handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoalHandlers:
    def test_goal_create_raises_on_missing_name(self):
        from AINDY.kernel.syscall_handlers import _handle_goal_create
        with pytest.raises(ValueError, match="requires 'name'"):
            _handle_goal_create({}, _ctx())

    def test_goal_create_returns_goal(self):
        from AINDY.kernel.syscall_handlers import _handle_goal_create

        mock_db = MagicMock()
        goal_result = {"id": "goal-1", "name": "Ship v2"}
        mock_goal_svc = MagicMock(create_goal=MagicMock(return_value=goal_result))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.masterplan.services.goal_service": mock_goal_svc,
            "apps.masterplan.services.goal_service": mock_goal_svc,
        }):
            result = _handle_goal_create({"name": "Ship v2"}, _ctx())

        assert result["goal_create_result"] == goal_result

    def test_goal_create_passes_defaults(self):
        from AINDY.kernel.syscall_handlers import _handle_goal_create

        mock_db = MagicMock()
        mock_create = MagicMock(return_value={"id": "g1", "name": "N"})
        mock_goal_svc = MagicMock(create_goal=mock_create)

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.masterplan.services.goal_service": mock_goal_svc,
            "apps.masterplan.services.goal_service": mock_goal_svc,
        }):
            _handle_goal_create({"name": "N"}, _ctx())

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["goal_type"] == "strategic"
        assert call_kwargs["priority"] == 0.5
        assert call_kwargs["status"] == "active"


# ═══════════════════════════════════════════════════════════════════════════════
# I: research + agent domain handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestResearchAndAgentHandlers:
    def test_research_query_raises_on_empty_query(self):
        from AINDY.kernel.syscall_handlers import _handle_research_query
        with pytest.raises(ValueError, match="requires 'query'"):
            _handle_research_query({}, _ctx())

    def test_research_query_returns_raw_result(self):
        from AINDY.kernel.syscall_handlers import _handle_research_query

        mock_research = MagicMock(web_search=MagicMock(return_value="Some result text"))

        with patch.dict("sys.modules", {"apps.search.services.research_engine": mock_research}):
            result = _handle_research_query({"query": "python best practices"}, _ctx())

        assert "raw_result" in result
        assert result["raw_result"] == "Some result text"

    def test_research_query_truncates_long_results(self):
        from AINDY.kernel.syscall_handlers import _handle_research_query

        long_text = "x" * 5000
        mock_research = MagicMock(web_search=MagicMock(return_value=long_text))

        with patch.dict("sys.modules", {"apps.search.services.research_engine": mock_research}):
            result = _handle_research_query({"query": "something"}, _ctx())

        assert len(result["raw_result"]) == 2000

    def test_agent_suggest_tools_returns_empty_on_no_kpi(self):
        from AINDY.kernel.syscall_handlers import _handle_agent_suggest_tools

        mock_db = MagicMock()
        mock_infinity = MagicMock(get_latest_adjustment=MagicMock(return_value=None))

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.analytics.services.infinity_loop": mock_infinity,
            "apps.analytics.services.infinity_loop": mock_infinity,
        }):
            result = _handle_agent_suggest_tools({}, _ctx())

        assert result["suggestions"] == []

    def test_agent_suggest_tools_returns_suggestions_for_low_focus(self):
        from AINDY.kernel.syscall_handlers import _handle_agent_suggest_tools

        mock_db = MagicMock()
        mock_infinity = MagicMock(get_latest_adjustment=MagicMock(return_value=None))

        kpi = {"focus_quality": 20.0, "execution_speed": 80.0, "ai_productivity_boost": 80.0, "master_score": 50.0}

        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.analytics.services.infinity_loop": mock_infinity,
            "apps.analytics.services.infinity_loop": mock_infinity,
        }):
            result = _handle_agent_suggest_tools({"kpi_snapshot": kpi}, _ctx())

        suggestions = result["suggestions"]
        assert len(suggestions) >= 1
        assert suggestions[0]["tool"] == "memory.recall"


