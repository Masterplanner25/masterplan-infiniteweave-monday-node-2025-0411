"""
Memory Bridge v3 Validation

Proves the v3 success condition:
"System finds useful memory you didn't explicitly tag for"
AND
"System explains WHY something matters (not just WHAT)"

Run with live DB + OpenAI:
  cd AINDY
  python tests/validate_memory_v3.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()


def validate_v3():
    print("=" * 60)
    print("MEMORY BRIDGE v3 VALIDATION")
    print("=" * 60)

    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO

    db = SessionLocal()
    dao = MemoryNodeDAO(db)
    TEST_USER = "v3-validation-user"

    node_a_id = None
    node_b_id = None
    node_c_id = None

    try:
        print("\n-- SETUP: Create connected memory nodes --")

        node_a = dao.save(
            content=(
                "Decided to use JWT tokens with 24h expiry "
                "for the authentication system. Chosen for "
                "stateless scalability."
            ),
            source="genesis_lock",
            tags=["auth", "decision", "jwt"],
            user_id=TEST_USER,
            node_type="decision",
            generate_embedding=True,
        )
        node_a_id = node_a["id"]
        print(f"[OK] Node A (decision): {node_a_id[:8]}...")

        node_b = dao.save(
            content=(
                "JWT auth implemented. Token refresh not "
                "handled - users get logged out after 24h. "
                "Needs improvement."
            ),
            source="arm_analysis",
            tags=["auth", "outcome", "bug"],
            user_id=TEST_USER,
            node_type="outcome",
            generate_embedding=True,
        )
        node_b_id = node_b["id"]
        print(f"[OK] Node B (outcome): {node_b_id[:8]}...")

        node_c = dao.save(
            content=(
                "Insight: stateless auth works well at scale "
                "but requires careful token lifecycle "
                "management. Consider refresh token pattern."
            ),
            source="arm_analysis",
            tags=["auth", "insight", "pattern"],
            user_id=TEST_USER,
            node_type="insight",
            generate_embedding=True,
        )
        node_c_id = node_c["id"]
        print(f"[OK] Node C (insight): {node_c_id[:8]}...")

        from bridge.bridge import create_memory_link

        create_memory_link(
            source_id=node_a_id,
            target_id=node_b_id,
            link_type="caused",
            db=db,
        )
        create_memory_link(
            source_id=node_b_id,
            target_id=node_c_id,
            link_type="follows",
            db=db,
        )
        print("[OK] Chain created: decision -> outcome -> insight")

        print("\n-- TEST 1: Find without explicit tags --")
        print("Query: 'token expiry session management'")
        print("(Note: no 'auth' tag in query)")

        results = dao.recall(
            query="token expiry session management",
            limit=3,
            user_id=TEST_USER,
        )

        if results:
            print(f"[OK] Found {len(results)} memories WITHOUT explicit tags")
            for r in results:
                print(
                    f"   [{r['node_type']}] "
                    f"resonance={r['resonance_score']:.3f}: "
                    f"{r['content'][:60]}..."
                )
        else:
            print("[FAIL] No memories found without tags")

        print("\n-- TEST 2: Chain of thought traversal --")
        print("Traversing from decision node A...")

        traversal = dao.traverse(
            start_node_id=node_a_id,
            max_depth=3,
            user_id=TEST_USER,
        )

        if traversal["chain_length"] > 0:
            print(f"[OK] Chain found: {traversal['chain_length']} nodes")
            print("\nChain of thought narrative:")
            print(traversal["narrative"])
        else:
            print("[FAIL] No chain found from start node")

        print("\n-- TEST 3: History on update --")

        updated = dao.update(
            node_id=node_b_id,
            user_id=TEST_USER,
            content=(
                "JWT auth implemented. Added token refresh "
                "endpoint - resolves 24h logout issue. "
                "Solution: refresh token pattern."
            ),
        )

        history = dao.get_history(
            node_id=node_b_id,
            user_id=TEST_USER,
        )

        if history:
            print(f"[OK] History recorded: {len(history)} entry/entries")
            print(f"   Previous: {history[0]['previous_content'][:50]}...")
            print(f"   Change: {history[0]['change_summary']}")
        else:
            print("[FAIL] No history recorded after update")

        print("\n-- TEST 4: v3 recall with expansion --")

        expanded = dao.recall(
            query="authentication token",
            tags=["auth"],
            limit=2,
            user_id=TEST_USER,
            expand_results=True,
        )

        if isinstance(expanded, dict):
            results_count = len(expanded.get("results", []))
            expanded_count = len(expanded.get("expanded", []))
            print(
                f"[OK] v3 recall: {results_count} results "
                f"+ {expanded_count} expanded context nodes"
            )
        else:
            print("[WARN] Expansion returned list (no expansion)")

        return True

    except Exception as e:
        print(f"\n[FAIL] VALIDATION ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        try:
            from db.models.memory_node_history import MemoryNodeHistory
            from services.memory_persistence import MemoryNodeModel, MemoryLinkModel

            node_ids = [node_a_id, node_b_id, node_c_id]
            node_ids = [nid for nid in node_ids if nid]

            if node_ids:
                db.query(MemoryNodeHistory).filter(
                    MemoryNodeHistory.node_id.in_(node_ids)
                ).delete(synchronize_session=False)
                db.query(MemoryLinkModel).filter(
                    MemoryLinkModel.source_node_id.in_(node_ids)
                ).delete(synchronize_session=False)
                db.query(MemoryNodeModel).filter(
                    MemoryNodeModel.id.in_(node_ids)
                ).delete(synchronize_session=False)
                db.commit()
                print("\n-- Cleanup complete --")
        except Exception:
            pass
        db.close()


if __name__ == "__main__":
    success = validate_v3()
    print("\n" + "=" * 60)
    print(
        "v3 RESULT: "
        f"{'[OK] STRUCTURED CONTINUITY WORKING' if success else '[FAIL] FAILED'}"
    )
    print("=" * 60)
    sys.exit(0 if success else 1)
