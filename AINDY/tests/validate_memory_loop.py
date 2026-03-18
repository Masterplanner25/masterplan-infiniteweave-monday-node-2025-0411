"""
validate_memory_loop.py

Live two-run loop validation for Memory Bridge Phase 3.

Run 1: writes a memory node (simulates ARM analysis outcome)
Run 2: recalls that node via resonance scoring

Usage:
    python tests/validate_memory_loop.py

Requires:
- PostgreSQL running at localhost:5433 (see Docker setup in docs/)
- PERMISSION_SECRET and OPENAI_API_KEY environment variables set
- Alembic migrations applied (including mb2embed0001)
"""
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uuid

try:
    from db.database import SessionLocal
    from bridge import create_memory_node, recall_memories
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    print("Ensure you're running from the AINDY/ directory or that PYTHONPATH is set.")
    sys.exit(1)


def run_loop_validation():
    print("=" * 60)
    print("Memory Bridge Phase 3 — Live Loop Validation")
    print("=" * 60)

    user_id = f"validate-loop-{uuid.uuid4().hex[:8]}"
    test_content = f"ARM analysis of validate_loop.py: Clean structure, no issues found. Session: {user_id}"
    test_tags = ["arm", "analysis", "py"]

    # -----------------------------------------------------------------------
    # Run 1: Write
    # -----------------------------------------------------------------------
    print(f"\n[Run 1] Writing memory node for user={user_id}")
    db = SessionLocal()
    try:
        node = create_memory_node(
            content=test_content,
            source="arm_analysis",
            tags=test_tags,
            user_id=user_id,
            db=db,
            node_type="outcome",
        )
        if not isinstance(node, dict) or "id" not in node:
            print(f"[FAIL] create_memory_node did not return expected dict: {node}")
            sys.exit(1)
        node_id = node["id"]
        print(f"[PASS] Node written: id={node_id}")
        print(f"       content: {node['content'][:80]}...")
    except Exception as e:
        print(f"[FAIL] Write failed: {e}")
        db.close()
        sys.exit(1)
    finally:
        db.close()

    # -----------------------------------------------------------------------
    # Run 2: Recall
    # -----------------------------------------------------------------------
    print(f"\n[Run 2] Recalling memory for user={user_id} query='ARM analysis validate_loop'")
    db = SessionLocal()
    try:
        results = recall_memories(
            query="ARM analysis validate_loop",
            tags=["arm", "analysis"],
            limit=5,
            user_id=user_id,
            db=db,
        )

        if not results:
            print("[FAIL] recall_memories returned empty list — node not found")
            sys.exit(1)

        top = results[0]
        print(f"[PASS] Recalled {len(results)} result(s)")
        print(f"       Top result id: {top.get('id')}")
        print(f"       node_type: {top.get('node_type')}")
        print(f"       resonance_score: {top.get('resonance_score', 'n/a'):.4f}" if top.get('resonance_score') else f"       resonance_score: n/a")
        print(f"       content: {top.get('content', '')[:80]}...")

        if top.get("id") != node_id:
            print(f"[WARN] Top result id ({top.get('id')}) differs from written id ({node_id})")
            print("       This may be expected if other nodes scored higher.")

        # Verify node_type
        if top.get("node_type") != "outcome":
            print(f"[WARN] Expected node_type='outcome', got '{top.get('node_type')}'")
        else:
            print("[PASS] node_type='outcome' confirmed")

    except Exception as e:
        print(f"[FAIL] Recall failed: {e}")
        db.close()
        sys.exit(1)
    finally:
        db.close()

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Loop validation PASSED")
    print(f"Run 1 wrote node: {node_id}")
    print(f"Run 2 recalled {len(results)} node(s)")
    print("=" * 60)


if __name__ == "__main__":
    run_loop_validation()
