"""
Capability System Tests — Sprint N+10.

Covers:
  - per-tool capability metadata
  - AgentRun/AgentTrustSettings capability fields
  - capability token mint/validate/check helpers
  - auto-grant trust fallback logic
  - approval-time token issuance
  - step-time capability denial
  - CAPABILITY_DENIED event support
  - API/UI surface updates
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


VALID_PLAN = {
    "executive_summary": "Do two safe things.",
    "steps": [
        {
            "tool": "task.create",
            "args": {"name": "Write follow-up"},
            "risk_level": "low",
            "description": "Create a task",
        },
        {
            "tool": "research.query",
            "args": {"query": "prospect research"},
            "risk_level": "low",
            "description": "Research context",
        },
    ],
    "overall_risk": "low",
}


def _trust(
    low=False,
    medium=False,
    allowed_auto_grant_tools=None,
):
    trust = MagicMock()
    trust.auto_execute_low = low
    trust.auto_execute_medium = medium
    trust.allowed_auto_grant_tools = allowed_auto_grant_tools
    return trust


class TestToolRegistryCapabilityMetadata:

    def test_all_tools_have_capability_metadata(self):
        from services.agent_tools import TOOL_REGISTRY
        for name, entry in TOOL_REGISTRY.items():
            assert entry["capability"] == f"tool:{name}"

    def test_all_tools_have_category(self):
        from services.agent_tools import TOOL_REGISTRY
        for entry in TOOL_REGISTRY.values():
            assert entry["category"]

    def test_all_tools_have_egress_scope(self):
        from services.agent_tools import TOOL_REGISTRY
        for entry in TOOL_REGISTRY.values():
            assert entry["egress_scope"]

    def test_genesis_message_metadata_is_high_risk(self):
        from services.agent_tools import TOOL_REGISTRY
        assert TOOL_REGISTRY["genesis.message"]["risk"] == "high"
        assert TOOL_REGISTRY["genesis.message"]["category"] == "genesis"

    def test_external_tools_have_non_internal_egress_scope(self):
        from services.agent_tools import TOOL_REGISTRY
        assert TOOL_REGISTRY["arm.analyze"]["egress_scope"] == "external_llm"
        assert TOOL_REGISTRY["leadgen.search"]["egress_scope"] == "external_web"
        assert TOOL_REGISTRY["research.query"]["egress_scope"] == "external_web"


class TestCapabilityOrmFields:

    def test_agent_run_has_capability_token_column(self):
        from db.models.agent_run import AgentRun
        assert "capability_token" in {c.name for c in AgentRun.__table__.columns}

    def test_agent_trust_has_allowed_auto_grant_tools_column(self):
        from db.models.agent_run import AgentTrustSettings
        assert "allowed_auto_grant_tools" in {
            c.name for c in AgentTrustSettings.__table__.columns
        }


class TestCapabilityServiceAutoGrantPolicy:

    def test_get_auto_grantable_tools_no_trust_returns_empty(self):
        from services.capability_service import get_auto_grantable_tools
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert get_auto_grantable_tools("u1", db) == []

    def test_get_auto_grantable_tools_uses_explicit_list_when_present(self):
        from services.capability_service import get_auto_grantable_tools
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(
            low=False,
            medium=False,
            allowed_auto_grant_tools=["task.complete", "task.create"],
        )
        assert get_auto_grantable_tools("u1", db) == ["task.complete", "task.create"]

    def test_get_auto_grantable_tools_strips_genesis_from_explicit_list(self):
        from services.capability_service import get_auto_grantable_tools
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(
            allowed_auto_grant_tools=["genesis.message", "task.create"],
        )
        assert get_auto_grantable_tools("u1", db) == ["task.create"]

    def test_get_auto_grantable_tools_falls_back_to_old_low_flag(self):
        from services.capability_service import get_auto_grantable_tools
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(low=True)
        allowed = get_auto_grantable_tools("u1", db)
        assert "task.create" in allowed
        assert "memory.recall" in allowed
        assert "task.complete" not in allowed

    def test_get_auto_grantable_tools_falls_back_to_old_medium_flag(self):
        from services.capability_service import get_auto_grantable_tools
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(medium=True)
        allowed = get_auto_grantable_tools("u1", db)
        assert "task.complete" in allowed
        assert "arm.analyze" in allowed
        assert "genesis.message" not in allowed

    def test_get_grantable_tools_manual_allows_known_plan_tools(self):
        from services.capability_service import get_grantable_tools
        db = MagicMock()
        assert get_grantable_tools(VALID_PLAN, "u1", db, "manual") == [
            "research.query",
            "task.create",
        ]

    def test_get_grantable_tools_manual_rejects_unknown_tool(self):
        from services.capability_service import get_grantable_tools
        db = MagicMock()
        plan = {"steps": [{"tool": "nope.tool"}]}
        assert get_grantable_tools(plan, "u1", db, "manual") == []

    def test_get_grantable_tools_auto_requires_all_tools_in_allowlist(self):
        from services.capability_service import get_grantable_tools
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(
            allowed_auto_grant_tools=["task.create"],
        )
        assert get_grantable_tools(VALID_PLAN, "u1", db, "auto") == []

    def test_get_grantable_tools_auto_passes_when_all_tools_allowed(self):
        from services.capability_service import get_grantable_tools
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(
            allowed_auto_grant_tools=["task.create", "research.query"],
        )
        assert get_grantable_tools(VALID_PLAN, "u1", db, "auto") == [
            "research.query",
            "task.create",
        ]


class TestCapabilityTokens:

    def test_mint_token_returns_expected_fields(self):
        from services.capability_service import mint_token
        db = MagicMock()
        token = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        assert token is not None
        assert token["run_id"] == "run-1"
        assert token["user_id"] == "u1"
        assert token["approval_mode"] == "manual"
        assert sorted(token["granted_tools"]) == ["research.query", "task.create"]
        assert token["token_hash"]

    def test_mint_token_auto_returns_none_when_plan_not_grantable(self):
        from services.capability_service import mint_token
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(
            allowed_auto_grant_tools=["task.create"],
        )
        assert mint_token("run-1", "u1", VALID_PLAN, db, "auto") is None

    def test_mint_token_auto_succeeds_when_plan_grantable(self):
        from services.capability_service import mint_token
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(
            allowed_auto_grant_tools=["task.create", "research.query"],
        )
        token = mint_token("run-1", "u1", VALID_PLAN, db, "auto")
        assert token is not None
        assert token["approval_mode"] == "auto"

    def test_validate_token_accepts_fresh_valid_token(self):
        from services.capability_service import mint_token, validate_token
        db = MagicMock()
        token = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        result = validate_token(token, "run-1", "u1")
        assert result["ok"] is True

    def test_validate_token_rejects_missing_token(self):
        from services.capability_service import validate_token
        result = validate_token(None, "run-1", "u1")
        assert result["ok"] is False

    def test_validate_token_rejects_run_mismatch(self):
        from services.capability_service import mint_token, validate_token
        db = MagicMock()
        token = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        result = validate_token(token, "run-2", "u1")
        assert result["ok"] is False

    def test_validate_token_rejects_user_mismatch(self):
        from services.capability_service import mint_token, validate_token
        db = MagicMock()
        token = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        result = validate_token(token, "run-1", "u2")
        assert result["ok"] is False

    def test_validate_token_rejects_expired_token(self):
        from services.capability_service import mint_token, validate_token
        db = MagicMock()
        token = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        token["expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        result = validate_token(token, "run-1", "u1")
        assert result["ok"] is False

    def test_validate_token_rejects_hash_mismatch(self):
        from services.capability_service import mint_token, validate_token
        db = MagicMock()
        token = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        token["token_hash"] = "bad-hash"
        result = validate_token(token, "run-1", "u1")
        assert result["ok"] is False

    def test_check_tool_capability_allows_granted_tool(self):
        from services.capability_service import check_tool_capability, mint_token
        db = MagicMock()
        token = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        result = check_tool_capability(token, "run-1", "u1", "task.create")
        assert result["ok"] is True

    def test_check_tool_capability_denies_ungranted_tool(self):
        from services.capability_service import check_tool_capability, mint_token
        db = MagicMock()
        token = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        result = check_tool_capability(token, "run-1", "u1", "arm.generate")
        assert result["ok"] is False
        assert "not granted" in result["error"]

    def test_manual_and_auto_tokens_use_different_hashes(self):
        from services.capability_service import mint_token
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = _trust(
            allowed_auto_grant_tools=["task.create", "research.query"],
        )
        manual = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        auto = mint_token("run-1", "u1", VALID_PLAN, db, "auto")
        assert manual["token_hash"] != auto["token_hash"]

    def test_replay_style_fresh_run_id_mints_different_hash(self):
        from services.capability_service import mint_token
        db = MagicMock()
        first = mint_token("run-1", "u1", VALID_PLAN, db, "manual")
        second = mint_token("run-2", "u1", VALID_PLAN, db, "manual")
        assert first["token_hash"] != second["token_hash"]


class TestRuntimeCapabilityIssuance:

    def _fake_run(self, status="approved"):
        run = MagicMock()
        run.id = "run-1"
        run.user_id = "u1"
        run.goal = "goal"
        run.executive_summary = "summary"
        run.overall_risk = "low"
        run.status = status
        run.steps_total = 2
        run.steps_completed = 0
        run.plan = VALID_PLAN
        run.result = None
        run.error_message = None
        run.flow_run_id = None
        run.replayed_from_run_id = None
        run.correlation_id = "run_corr"
        run.capability_token = None
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None
        return run

    def test_create_run_auto_status_mints_token(self):
        from services.agent_runtime import create_run

        db = MagicMock()
        fake_run = self._fake_run(status="approved")
        with patch("services.agent_runtime.generate_plan", return_value=VALID_PLAN), \
             patch("services.agent_runtime._requires_approval", return_value=False), \
             patch("db.models.agent_run.AgentRun", return_value=fake_run), \
             patch("services.agent_runtime.mint_token", return_value={"granted_tools": ["task.create"]}):
            result = create_run("goal", "u1", db)

        assert fake_run.capability_token == {"granted_tools": ["task.create"]}
        assert result["granted_tools"] == ["task.create"]

    def test_create_run_auto_preflight_failure_reverts_to_pending(self):
        from services.agent_runtime import create_run

        db = MagicMock()
        fake_run = self._fake_run(status="approved")
        with patch("services.agent_runtime.generate_plan", return_value=VALID_PLAN), \
             patch("services.agent_runtime._requires_approval", return_value=False), \
             patch("db.models.agent_run.AgentRun", return_value=fake_run), \
             patch("services.agent_runtime.mint_token", return_value=None):
            result = create_run("goal", "u1", db)

        assert fake_run.status == "pending_approval"
        assert "Capability preflight failed" in fake_run.error_message
        assert result["status"] == "pending_approval"

    def test_approve_run_manual_mints_token_and_executes(self):
        from services.agent_runtime import approve_run

        db = MagicMock()
        run = self._fake_run(status="pending_approval")
        db.query.return_value.filter.return_value.first.return_value = run
        with patch("services.agent_runtime.mint_token", return_value={"granted_tools": ["task.create"]}), \
             patch("services.agent_runtime.execute_run", return_value={"run_id": "run-1", "status": "completed"}) as mock_execute:
            approve_run("run-1", "u1", db)

        assert run.capability_token == {"granted_tools": ["task.create"]}
        mock_execute.assert_called_once()

    def test_run_to_dict_exposes_granted_tools(self):
        from services.agent_runtime import _run_to_dict
        run = self._fake_run(status="approved")
        run.capability_token = {"granted_tools": ["task.create", "research.query"]}
        payload = _run_to_dict(run)
        assert payload["granted_tools"] == ["task.create", "research.query"]

    def test_execute_run_passes_capability_token_to_adapter(self):
        from services.agent_runtime import execute_run

        db = MagicMock()
        run = self._fake_run(status="approved")
        run.capability_token = {"granted_tools": ["task.create"]}
        db.query.return_value.filter.return_value.first.return_value = run
        with patch("services.nodus_adapter.NodusAgentAdapter.execute_with_flow", return_value={"status": "SUCCESS"}) as mock_exec:
            execute_run("run-1", "u1", db)

        assert mock_exec.call_args.kwargs["capability_token"] == {"granted_tools": ["task.create"]}


class TestStepTimeCapabilityChecks:

    def _db(self):
        db = MagicMock()
        run = MagicMock()
        run.id = "run-1"
        run.steps_completed = 0
        run.current_step = 0
        db.query.return_value.filter.return_value.first.return_value = run
        return db, run

    def _state(self):
        return {
            "agent_run_id": "run-1",
            "user_id": "u1",
            "steps": [
                {
                    "tool": "task.create",
                    "args": {"name": "x"},
                    "risk_level": "low",
                    "description": "Create x",
                }
            ],
            "current_step_index": 0,
            "step_results": [],
            "correlation_id": "run_corr",
            "capability_token": {"granted_tools": []},
        }

    def test_agent_execute_step_denies_when_capability_check_fails(self):
        from services.nodus_adapter import agent_execute_step

        db, _ = self._db()
        with patch("services.nodus_adapter.check_tool_capability", return_value={"ok": False, "error": "nope", "granted_tools": []}), \
             patch("services.nodus_adapter.execute_tool") as mock_execute:
            result = agent_execute_step(self._state(), {"db": db})

        assert result["status"] == "FAILURE"
        assert "Capability denied" in result["error"]
        mock_execute.assert_not_called()

    def test_agent_execute_step_emits_capability_denied_event(self):
        from services.nodus_adapter import agent_execute_step

        db, _ = self._db()
        with patch("services.nodus_adapter.check_tool_capability", return_value={"ok": False, "error": "nope", "granted_tools": []}), \
             patch("services.agent_event_service.emit_event") as mock_emit:
            agent_execute_step(self._state(), {"db": db})

        mock_emit.assert_called_once()
        assert mock_emit.call_args.kwargs["event_type"] == "CAPABILITY_DENIED"

    def test_agent_execute_step_persists_failed_step_on_capability_denial(self):
        from services.nodus_adapter import agent_execute_step

        db, _ = self._db()
        with patch("services.nodus_adapter.check_tool_capability", return_value={"ok": False, "error": "nope", "granted_tools": []}):
            agent_execute_step(self._state(), {"db": db})

        db.add.assert_called_once()
        db.commit.assert_called()

    def test_execute_with_flow_passes_capability_token_into_initial_state(self):
        from services.nodus_adapter import NodusAgentAdapter

        db = MagicMock()
        run = MagicMock()
        run.status = "executing"
        db.query.return_value.filter.return_value.first.return_value = run
        with patch("services.nodus_adapter.PersistentFlowRunner") as MockRunner:
            MockRunner.return_value.start.return_value = {"status": "SUCCESS", "run_id": "flow-1"}
            NodusAgentAdapter.execute_with_flow(
                run_id="run-1",
                plan=VALID_PLAN,
                user_id="u1",
                db=db,
                capability_token={"granted_tools": ["task.create"]},
            )

        initial_state = MockRunner.return_value.start.call_args.args[0]
        assert initial_state["capability_token"] == {"granted_tools": ["task.create"]}


class TestCapabilityDeniedEvents:

    def test_agent_event_model_contains_capability_denied(self):
        from db.models.agent_event import AGENT_EVENT_TYPES
        assert "CAPABILITY_DENIED" in AGENT_EVENT_TYPES

    def test_agent_event_service_contains_capability_denied(self):
        from services.agent_event_service import AGENT_EVENT_TYPES
        assert "CAPABILITY_DENIED" in AGENT_EVENT_TYPES


class TestAgentRouterCapabilitySurface:

    def test_tools_endpoint_exposes_capability_metadata(self, client, auth_headers):
        resp = client.get("/agent/tools", headers=auth_headers)
        assert resp.status_code == 200
        first = resp.json()[0]
        assert "capability" in first
        assert "category" in first
        assert "egress_scope" in first

    def test_trust_get_exposes_allowed_auto_grant_tools(self, client, auth_headers, mock_db):
        trust = _trust(
            low=True,
            medium=False,
            allowed_auto_grant_tools=["task.create"],
        )
        mock_db.first.return_value = trust
        resp = client.get("/agent/trust", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["allowed_auto_grant_tools"] == ["task.create"]

    def test_trust_put_sanitizes_genesis_message(self, client, auth_headers, mock_db):
        trust = _trust()
        trust.updated_at = None
        mock_db.first.return_value = trust
        resp = client.put(
            "/agent/trust",
            headers=auth_headers,
            json={
                "allowed_auto_grant_tools": [
                    "task.create",
                    "genesis.message",
                    "not.real",
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["allowed_auto_grant_tools"] == ["task.create"]


class TestCapabilityUiSurface:

    def test_api_js_mentions_allowed_auto_grant_tools(self):
        src = open("client/src/api.js", encoding="utf-8").read()
        assert "allowed_auto_grant_tools" in src

    def test_agent_console_mentions_tool_level_auto_grant_policy(self):
        src = open("client/src/components/AgentConsole.jsx", encoding="utf-8").read()
        assert "Tool-Level Auto-Grant Policy" in src

    def test_agent_console_locks_genesis_toggle(self):
        src = open("client/src/components/AgentConsole.jsx", encoding="utf-8").read()
        assert "genesis.message" in src
        assert "cannot be auto-granted" in src

    def test_agent_console_uses_allowed_auto_grant_tools(self):
        src = open("client/src/components/AgentConsole.jsx", encoding="utf-8").read()
        assert "allowed_auto_grant_tools" in src
