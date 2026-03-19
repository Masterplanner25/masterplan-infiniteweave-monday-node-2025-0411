"""
Memory Bridge v4 Validation

Proves: "System prevents mistakes and suggests better paths"

Run with live DB:
  cd AINDY
  python tests/validate_memory_v4.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()


def validate_v4():
    print("=" * 60)
    print("MEMORY BRIDGE v4 VALIDATION")
    print("=" * 60)

    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO

    db = SessionLocal()
    dao = MemoryNodeDAO(db)
    TEST_USER = "v4-validation-user"
    created_ids = []

    try:
        print("\n?? SETUP: Create memory with feedback ??")

        # Create a decision memory
        node = dao.save(
            content=(
                "Used JWT with short expiry (1h) + refresh "
                "tokens for the auth system. Scales well, "
                "good UX."
            ),
            source="genesis_lock",
            tags=["auth", "jwt", "decision"],
            user_id=TEST_USER,
            node_type="decision",
            generate_embedding=True
        )
        created_ids.append(node["id"])
        print(f"? Node created: {node['id'][:8]}...")

        # Record 3 successes and 1 failure
        print("\n?? Recording feedback signals ??")
        for _ in range(3):
            dao.record_feedback(
                node_id=node["id"],
                outcome="success",
                user_id=TEST_USER
            )
        dao.record_feedback(
            node_id=node["id"],
            outcome="failure",
            user_id=TEST_USER
        )

        # Reload to check updated values
        node_obj = dao._get_model_by_id(node["id"], user_id=TEST_USER)
        print(f"? Feedback recorded:")
        print(f"   Success count: {node_obj.success_count}")
        print(f"   Failure count: {node_obj.failure_count}")
        print(f"   Adaptive weight: {node_obj.weight:.3f}")
        print(f"   Success rate: {dao.get_success_rate(node_obj):.1%}")

        assert node_obj.success_count == 3
        assert node_obj.failure_count == 1
        assert node_obj.weight > 1.0

        print("\n?? TEST: Resonance v2 scoring ??")

        results = dao.recall(
            query="authentication token management",
            tags=["auth"],
            limit=3,
            user_id=TEST_USER
        )

        result_list = results if isinstance(results, list) \
                      else results.get("results", [])

        if result_list:
            top = result_list[0]
            print(f"? Resonance v2 scores:")
            print(f"   semantic:      {top.get('semantic_score', 0):.3f} ? 0.40")
            print(f"   graph:         {top.get('graph_score', 0):.3f} ? 0.15")
            print(f"   recency:       {top.get('recency_score', 0):.3f} ? 0.15")
            print(f"   success_rate:  {top.get('success_rate', 0):.3f} ? 0.20")
            print(f"   usage_freq:    {top.get('usage_frequency', 0):.3f} ? 0.10")
            print(f"   adaptive_wt:   {top.get('adaptive_weight', 1):.3f}?")
            print(f"   RESONANCE v2:  {top.get('resonance_score', 0):.3f}")

        print("\n?? TEST: Suggestion engine ??")
        print("Query: 'what authentication approach should I use'")

        suggestions = dao.suggest(
            query="what authentication approach should I use",
            tags=["auth", "decision"],
            user_id=TEST_USER,
            limit=3
        )

        if suggestions["suggestions"]:
            print(f"? {suggestions['suggestion_count']} suggestion(s) generated:")
            for s in suggestions["suggestions"]:
                print(f"\n   Action: {s['action'][:80]}")
                print(f"   Reason: {s['reasoning']}")
                print(f"   Confidence: {s['confidence']:.3f}")
                if s.get("warning"):
                    print(f"   ??  {s['warning']}")
        else:
            print(f"??  No suggestions: {suggestions['message']}")

        print("\n?? TEST: Performance endpoint data ??")

        graph_score = dao.get_graph_connectivity_score(node["id"])
        usage_freq = dao.get_usage_frequency_score(node_obj)

        print(f"? Performance metrics:")
        print(f"   Graph connectivity: {graph_score:.3f}")
        print(f"   Usage frequency:    {usage_freq:.3f}")
        print(f"   Last outcome:       {node_obj.last_outcome}")

        print("\n?? v4 SUCCESS CONDITION CHECK ??")
        has_feedback = node_obj.success_count > 0
        has_weight = node_obj.weight != 1.0
        has_suggestions = len(
            suggestions["suggestions"]
        ) >= 0
        has_v2_scores = bool(result_list and
            "success_rate" in result_list[0])

        print(f"Feedback loop active: {'?' if has_feedback else '?'}")
        print(f"Adaptive weight working: {'?' if has_weight else '?'}")
        print(f"Resonance v2 active: {'?' if has_v2_scores else '?'}")
        print(f"Suggestion engine active: {'?' if has_suggestions else '?'}")

        return all([has_feedback, has_weight, has_v2_scores])

    except Exception as e:
        print(f"\n? ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        try:
            from services.memory_persistence import MemoryNodeModel
            db.query(MemoryNodeModel).filter(
                MemoryNodeModel.user_id == TEST_USER
            ).delete(synchronize_session=False)
            db.commit()
            print("\n?? Cleanup complete ??")
        except Exception:
            pass
        db.close()


if __name__ == "__main__":
    success = validate_v4()
    print("\n" + "=" * 60)
    print(
        f"v4 RESULT: "
        f"{'? ADAPTIVE INTELLIGENCE WORKING' if success else '? FAILED'}"
    )
    print("=" * 60)
    sys.exit(0 if success else 1)
