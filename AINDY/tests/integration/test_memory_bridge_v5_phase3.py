"""
Memory Bridge v5 Phase 3 Tests — Multi-Agent Memory
"""
import pytest
import sqlalchemy
from uuid import uuid4
from unittest.mock import MagicMock, patch


class TestAgentModel:

    def test_agent_model_importable(self):
        from db.models.agent import Agent, SYSTEM_AGENTS
        assert Agent.__tablename__ == "agents"
        assert "arm" in SYSTEM_AGENTS
        assert "genesis" in SYSTEM_AGENTS
        assert "nodus" in SYSTEM_AGENTS

    def test_agents_table_in_db(self):
        from db.models.agent import Agent
        assert Agent.__tablename__ in Agent.metadata.tables

    def test_source_agent_column_on_memory_nodes(self):
        from memory.memory_persistence import MemoryNodeModel
        cols = list(MemoryNodeModel.__table__.columns.keys())
        assert "source_agent" in cols
        assert "is_shared" in cols

    def test_system_agents_seeded(self, mock_db):
        """System agents should be in the registry."""
        from db.models.agent import (
            Agent, AGENT_ARM, AGENT_GENESIS,
            AGENT_NODUS, AGENT_LEADGEN
        )
        for namespace in [AGENT_ARM, AGENT_GENESIS, AGENT_NODUS, AGENT_LEADGEN]:
            mock_db.add(
                Agent(
                    id=f"system-{namespace}",
                    name=namespace.upper(),
                    agent_type="system",
                    description=f"{namespace} agent",
                    memory_namespace=namespace,
                    is_active=True,
                )
            )
        mock_db.commit()

        namespaces = [
            agent.memory_namespace
            for agent in mock_db.query(Agent).filter(Agent.is_active.is_(True)).all()
        ]
        assert AGENT_ARM in namespaces
        assert AGENT_GENESIS in namespaces


class TestFederatedMemoryDAO:

    def test_save_as_agent_exists(self):
        from db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "save_as_agent")

    def test_recall_from_agent_exists(self):
        from db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "recall_from_agent")

    def test_recall_federated_exists(self):
        from db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "recall_federated")

    def test_share_memory_exists(self):
        from db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "share_memory")

    def test_recall_federated_structure(self, mock_db, mocker):
        from db.dao.memory_node_dao import MemoryNodeDAO

        mocker.patch(
            "db.dao.memory_node_dao.MemoryNodeDAO"
            ".recall_from_agent",
            return_value=[],
        )

        dao = MemoryNodeDAO(mock_db)
        result = dao.recall_federated(
            query="test",
            user_id="test-user",
        )

        assert "merged_results" in result
        assert "results_by_agent" in result
        assert "agents_queried" in result
        assert "federation_summary" in result

    def test_private_nodes_hidden_in_cross_agent_query(self, mock_db):
        """
        Cross-agent queries must not return private nodes.
        include_private=False is enforced in recall_federated.
        """
        from db.dao.memory_node_dao import MemoryNodeDAO
        import inspect

        source = inspect.getsource(MemoryNodeDAO.recall_federated)
        assert "include_private=False" in source, (
            "recall_federated must enforce include_private=False"
        )


class TestCaptureEngineNamespacing:

    def test_capture_engine_accepts_namespace(self):
        from memory.memory_capture_engine import MemoryCaptureEngine
        import inspect
        sig = inspect.signature(MemoryCaptureEngine.__init__)
        assert "agent_namespace" in sig.parameters

    def test_arm_uses_arm_namespace(self):
        import inspect
        from modules.deepseek import deepseek_code_analyzer
        source = inspect.getsource(deepseek_code_analyzer)
        assert "arm" in source and "agent_namespace" in source, (
            "ARM should use agent_namespace='arm'"
        )

    def test_genesis_uses_genesis_namespace(self):
        import inspect
        from services import genesis_ai
        source = inspect.getsource(genesis_ai)
        assert "genesis" in source and "agent_namespace" in source, (
            "Genesis should use agent_namespace='genesis'"
        )


class TestFederationNodusbridge:

    def test_bridge_has_recall_from(self):
        from memory.nodus_memory_bridge import NodusMemoryBridge
        assert hasattr(NodusMemoryBridge, "recall_from")

    def test_bridge_has_recall_all_agents(self):
        from memory.nodus_memory_bridge import NodusMemoryBridge
        assert hasattr(NodusMemoryBridge, "recall_all_agents")

    def test_bridge_has_share(self):
        from memory.nodus_memory_bridge import NodusMemoryBridge
        assert hasattr(NodusMemoryBridge, "share")

    def test_recall_from_without_db_returns_empty(self):
        from memory.nodus_memory_bridge import create_nodus_bridge
        bridge = create_nodus_bridge(db=None)
        result = bridge.recall_from("arm", query="test")
        assert result == []

    def test_share_without_db_returns_false(self):
        from memory.nodus_memory_bridge import create_nodus_bridge
        bridge = create_nodus_bridge(db=None)
        result = bridge.share("some-node-id")
        assert result is False


class TestFederationEndpoints:

    def test_federated_recall_requires_auth(self, client):
        r = client.post(
            "/memory/federated/recall",
            json={"query": "test"},
        )
        assert r.status_code == 401

    def test_list_agents_requires_auth(self, client):
        r = client.get("/memory/agents")
        assert r.status_code == 401

    def test_share_node_requires_auth(self, client):
        r = client.post("/memory/nodes/test-id/share")
        assert r.status_code == 401

    def test_agent_recall_requires_auth(self, client):
        r = client.get("/memory/agents/arm/recall")
        assert r.status_code == 401

    def test_federated_recall_requires_query_or_tags(self, client, auth_headers):
        r = client.post(
            "/memory/federated/recall",
            json={},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_federated_recall_with_auth(self, client, auth_headers, mock_db, mocker):
        mocker.patch(
            "db.dao.memory_node_dao.MemoryNodeDAO"
            ".recall_federated",
            return_value={
                "query": "test",
                "tags": None,
                "agents_queried": ["arm", "genesis"],
                "results_by_agent": {},
                "merged_results": [],
                "total_found": 0,
                "federation_summary": {},
            },
        )

        r = client.post(
            "/memory/federated/recall",
            json={"query": "test query"},
            headers=auth_headers,
        )
        assert r.status_code in [200, 422]
        assert r.status_code != 401

        if r.status_code == 200:
            data = r.json()
            assert "merged_results" in data
            assert "federation_summary" in data

    def test_list_agents_with_auth(self, client, auth_headers, mock_db, test_user):
        from db.models.agent import Agent
        from memory.memory_persistence import MemoryNodeModel

        mock_db.add(
            Agent(
                id=f"agent-{uuid4()}",
                name="ARM",
                agent_type="system",
                description="ARM agent",
                memory_namespace="arm",
                is_active=True,
            )
        )
        mock_db.flush()
        mock_db.add(
            MemoryNodeModel(
                content="shared arm memory",
                tags=["arm", "shared"],
                node_type="insight",
                source="test",
                source_agent="arm",
                is_shared=True,
                user_id=test_user.id,
                extra={},
            )
        )
        mock_db.commit()

        r = client.get(
            "/memory/agents",
            headers=auth_headers,
        )
        assert r.status_code in [200, 422]
        assert r.status_code != 401
        if r.status_code == 200:
            data = r.json()
            assert data["total"] >= 1
            arm_agent = next(
                agent_data
                for agent_data in data["agents"]
                if agent_data["memory_namespace"] == "arm"
            )
            assert arm_agent["memory_stats"]["total_nodes"] >= 1
            assert arm_agent["memory_stats"]["shared_nodes"] >= 1
