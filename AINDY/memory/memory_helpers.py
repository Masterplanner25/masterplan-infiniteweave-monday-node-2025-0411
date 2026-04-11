"""
memory_helpers.py — shared memory enrichment for all execution contexts.

Provides a single enrich_context() entry point that any execution surface
(flow node, agent tool step, planning prompt) can call to hydrate
context["memory_context"] from MemoryNodeDAO without duplicating recall logic.

Design decisions
----------------
* Tags are pulled from whichever of the standard signal keys happen to be
  present in the context dict — callers set the ones they have.
* limit=5 is kept consistent with the existing flow_engine inline recall.
* All failures are non-fatal: context["memory_context"] defaults to [].
* format_memories_for_prompt() converts the recall list into a compact
  text block suitable for LLM system-prompt injection.
"""
import logging

logger = logging.getLogger(__name__)

# Keys consulted (in priority order) to build recall tags.
# Callers set whichever are meaningful for their context.
_TAG_KEYS = (
    "node_name",    # flow node currently executing
    "flow_name",    # registered flow name
    "workflow_type",# flow workflow_type (overlaps flow_name; both kept)
    "tool_name",    # agent tool currently executing
    "operation",    # router operation label
    "agent_type",   # agent personality / type
)


def enrich_context(context: dict) -> dict:
    """
    Inject memory_context into *context* using available context signals as recall tags.

    Mutates context["memory_context"] in place and returns context for chaining.
    Always safe: sets context["memory_context"] = [] when db is absent, no tags
    can be derived, or MemoryNodeDAO.recall() raises.

    Usage
    -----
        context["node_name"] = node_name   # set whichever signals apply
        enrich_context(context)
        memories = context["memory_context"]  # list[dict]
    """
    db = context.get("db")
    if db is None:
        context.setdefault("memory_context", [])
        return context

    tags = [context[k] for k in _TAG_KEYS if context.get(k)]
    if not tags:
        context.setdefault("memory_context", [])
        return context

    user_id = context.get("user_id")

    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        memories = MemoryNodeDAO(db).recall(tags=tags, limit=5, user_id=user_id)
        context["memory_context"] = memories
        logger.debug(
            "[memory] enrich_context | tags=%s user=%s count=%d",
            tags, user_id, len(memories),
        )
    except Exception as exc:
        context["memory_context"] = []
        logger.warning("[memory] enrich_context fallback | tags=%s error=%s", tags, exc)

    return context


def record_execution_feedback(context: dict, outcome: str) -> None:
    """
    Record the outcome of a node execution against every memory recalled for it.

    Mutates MemoryNode.usage_count (+1 always), success_count / failure_count
    (+1 on "success" / "failure"), and adjusts the adaptive weight.  Non-fatal:
    any DB error is logged and swallowed so it never blocks execution.

    Args:
        context: The same context dict passed to the node — must already have
                 been enriched by enrich_context().
        outcome: "success" | "failure" | "neutral"
    """
    db = context.get("db")
    memories = context.get("memory_context") or []
    if db is None or not memories:
        return

    user_id = context.get("user_id")
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        dao = MemoryNodeDAO(db)
        for memory in memories:
            node_id = memory.get("id")
            if node_id:
                try:
                    dao.record_feedback(str(node_id), outcome, user_id=user_id)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "[memory] record_execution_feedback skip | node_id=%s error=%s",
                        node_id, exc,
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[memory] record_execution_feedback failed | outcome=%s error=%s", outcome, exc)


def format_memories_for_prompt(memories: list, max_items: int = 3, max_chars: int = 200) -> str:
    """
    Convert a memory recall list into a compact text block for LLM system-prompt injection.

    Returns an empty string when memories is empty so callers can concatenate
    unconditionally without adding blank sections to the prompt.

    Example output
    --------------
        ## Relevant Past Context
        - Completed task 'ARM analysis' in 320ms with high success rate.
        - Lead search for 'SaaS startups' returned 12 results; top fit_score 0.92.
        - Goal drift detected on 'Revenue' goal after agent run 7e3a...
    """
    if not memories:
        return ""

    lines = []
    for m in memories[:max_items]:
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"- {content[:max_chars]}")

    if not lines:
        return ""

    return "\n\n## Relevant Past Context\n" + "\n".join(lines)
