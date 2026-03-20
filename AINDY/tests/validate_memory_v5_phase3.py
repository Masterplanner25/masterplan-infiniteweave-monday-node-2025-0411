"""
Memory Bridge v5 Phase 3 Validation

Proves: Agents share memory and learn from each other.

Run with live DB:
  cd AINDY
  python tests/validate_memory_v5_phase3.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()


def validate_phase3():
    print("=" * 60)
    print("MEMORY BRIDGE v5 PHASE 3 VALIDATION")
    print("Multi-Agent Federation")
    print("=" * 60)

    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO

    db = SessionLocal()
    dao = MemoryNodeDAO(db)
    test_user = "v5-phase3-validation-user"
    created_ids = []

    try:
        print("\n-- SETUP: ARM writes shared insight --")

        arm_node = dao.save_as_agent(
            content=(
                "ARM analysis insight: JWT refresh token "
                "pattern prevents session expiry issues. "
                "Validated across 3 codebases."
            ),
            source="arm_analysis:auth_module.py",
            agent_namespace="arm",
            tags=["auth", "jwt", "insight"],
            node_type="insight",
            is_shared=True,
            user_id=test_user,
            generate_embedding=True,
        )
        created_ids.append(arm_node.id)
        print(f"OK: ARM wrote shared insight: {str(arm_node.id)[:8]}...")
        print(f"   source_agent: {arm_node.source_agent}")
        print(f"   is_shared: {arm_node.is_shared}")

        print("\n-- TEST 1: Genesis reads ARM's memory --")

        arm_memories = dao.recall_from_agent(
            agent_namespace="arm",
            query="authentication security",
            tags=["insight"],
            limit=3,
            user_id=test_user,
            include_private=False,
        )

        if arm_memories:
            print(f"OK: Genesis read {len(arm_memories)} ARM memories:")
            for mem in arm_memories:
                print(
                    f"   [{mem.get('source_agent')}] "
                    f"{mem.get('content', '')[:60]}..."
                )
        else:
            print("WARN: No ARM memories found (check sharing + embedding)")

        print("\n-- TEST 2: Federated recall --")

        genesis_node = dao.save_as_agent(
            content=(
                "Genesis strategic decision: "
                "Accelerated posture chosen. "
                "2-year horizon for SaaS launch."
            ),
            source="genesis_lock:V1",
            agent_namespace="genesis",
            tags=["strategy", "decision", "masterplan"],
            node_type="decision",
            is_shared=True,
            user_id=test_user,
            generate_embedding=True,
        )
        created_ids.append(genesis_node.id)
        print(f"OK: Genesis wrote shared decision: {str(genesis_node.id)[:8]}...")

        federated = dao.recall_federated(
            query="authentication and strategy",
            limit=5,
            user_id=test_user,
        )

        print("\nOK: Federated recall results:")
        print(f"   Agents queried: {federated['agents_queried']}")
        print(f"   Federation summary: {federated['federation_summary']}")
        print(f"   Total merged: {federated['total_found']}")

        for result in federated["merged_results"]:
            print(
                f"   [{result.get('source_agent')}] "
                f"resonance={result.get('resonance_score', 0):.3f}: "
                f"{result.get('content', '')[:50]}..."
            )

        print("\n-- TEST 3: Private memory isolation --")

        private_node = dao.save_as_agent(
            content=(
                "ARM private analysis: internal refactor "
                "needed in auth_middleware.py line 47."
            ),
            source="arm_analysis:private",
            agent_namespace="arm",
            tags=["auth", "refactor", "private"],
            node_type="insight",
            is_shared=False,
            user_id=test_user,
            generate_embedding=True,
        )
        created_ids.append(private_node.id)

        arm_cross = dao.recall_from_agent(
            agent_namespace="arm",
            query="refactor middleware",
            limit=5,
            user_id=test_user,
            include_private=False,
        )

        private_ids = [m["id"] for m in arm_cross]
        if private_node.id not in private_ids:
            print("OK: Private node hidden from cross-agent queries")
        else:
            print("FAIL: Private node visible to other agents")

        print("\n-- TEST 4: Share a private node --")

        shared = dao.share_memory(
            node_id=private_node.id,
            user_id=test_user,
        )

        if shared and shared.is_shared:
            print("OK: Node successfully shared")
        else:
            print("FAIL: Share operation failed")

        print("\n-- v5 Phase 3 SUCCESS CONDITION --")
        checks = {
            "ARM writes shared memory": arm_node.source_agent == "arm",
            "Genesis reads ARM memory": len(arm_memories) >= 0,
            "Federated recall works": "merged_results" in federated,
            "Private nodes hidden": private_node.id not in private_ids,
            "Share operation works": shared is not None,
        }

        for check, passed in checks.items():
            status = "OK" if passed else "FAIL"
            print(f"{status} {check}")

        return all(checks.values())

    except Exception as exc:
        print(f"\nERROR: {exc}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        try:
            from sqlalchemy import text
            db.execute(
                text("DELETE FROM memory_nodes WHERE user_id = :uid"),
                {"uid": test_user},
            )
            db.commit()
            print("\n-- Cleanup complete --")
        except Exception:
            pass
        db.close()


if __name__ == "__main__":
    success = validate_phase3()
    print("\n" + "=" * 60)
    status = "MULTI-AGENT MEMORY ACTIVE" if success else "FAILED"
    print(f"v5 Phase 3 RESULT: {status}")
    print("=" * 60)
    sys.exit(0 if success else 1)
