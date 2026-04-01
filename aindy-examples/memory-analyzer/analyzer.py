"""
analyzer.py — pattern detection over a list of memory nodes.

Takes the raw node list returned by memory.read() and computes:
  - completion rate by status
  - tag frequency distribution
  - bottleneck detection (most common tag on blocked/in-progress items)
  - per-owner workload breakdown

All logic is pure Python — no external dependencies.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


def analyze(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Run pattern analysis over a list of memory nodes.

    Args:
        nodes: List of node dicts as returned by client.memory.read().

    Returns:
        Analysis dict with keys: summary, completion_rate, status_breakdown,
        tag_frequency, bottleneck_tag, top_tags, owner_breakdown, insights.
    """
    if not nodes:
        return {
            "summary":         "No nodes to analyze.",
            "completion_rate": 0.0,
            "status_breakdown": {},
            "tag_frequency":   {},
            "bottleneck_tag":  None,
            "top_tags":        [],
            "owner_breakdown": {},
            "insights":        [],
        }

    total = len(nodes)

    # ── Status breakdown ─────────────────────────────────────────────────────
    status_counts: Counter = Counter()
    for node in nodes:
        status = node.get("extra", {}).get("status") or "unknown"
        status_counts[status] += 1

    completed    = status_counts.get("completed", 0)
    in_progress  = status_counts.get("in-progress", 0)
    blocked      = status_counts.get("blocked", 0)
    completion_rate = round(completed / total * 100, 1) if total else 0.0

    # ── Tag frequency ─────────────────────────────────────────────────────────
    tag_counter: Counter = Counter()
    for node in nodes:
        for tag in node.get("tags", []):
            tag_counter[tag] += 1

    top_tags = [tag for tag, _ in tag_counter.most_common(5)]

    # ── Bottleneck detection ──────────────────────────────────────────────────
    # Tag most associated with blocked or in-progress items
    blocking_tags: Counter = Counter()
    for node in nodes:
        status = node.get("extra", {}).get("status") or "unknown"
        if status in ("blocked", "in-progress"):
            for tag in node.get("tags", []):
                if tag != "sprint-12":  # skip sprint labels
                    blocking_tags[tag] += 1

    bottleneck_tag = blocking_tags.most_common(1)[0][0] if blocking_tags else None

    # ── Owner workload ────────────────────────────────────────────────────────
    owner_counter: Counter = Counter()
    for node in nodes:
        owner = node.get("extra", {}).get("owner") or "unassigned"
        owner_counter[owner] += 1

    owner_breakdown = dict(owner_counter.most_common())

    # ── Build insights ────────────────────────────────────────────────────────
    insights = []

    # Completion insight
    insights.append({
        "type":    "completion_rate",
        "content": (
            f"Sprint completion rate: {completion_rate}% "
            f"({completed}/{total} tasks done). "
            f"{in_progress} in progress, {blocked} blocked."
        ),
        "tags":    ["completion", "sprint-metric"],
        "data": {
            "completion_rate": completion_rate,
            "completed":  completed,
            "in_progress": in_progress,
            "blocked":    blocked,
            "total":      total,
        },
    })

    # Tag frequency insight
    if top_tags:
        insights.append({
            "type":    "tag_frequency",
            "content": (
                f"Most active work areas this sprint: "
                + ", ".join(top_tags[:3]) + ". "
                + f"Total unique tags: {len(tag_counter)}."
            ),
            "tags":    ["tags", "work-distribution"],
            "data": {
                "top_tags":    top_tags,
                "tag_counts":  dict(tag_counter.most_common(10)),
            },
        })

    # Bottleneck insight
    if bottleneck_tag:
        insights.append({
            "type":    "bottleneck",
            "content": (
                f"Bottleneck detected in '{bottleneck_tag}': "
                f"{blocking_tags[bottleneck_tag]} blocked/in-progress task(s) carry this tag. "
                "Consider unblocking or reassigning."
            ),
            "tags":    ["bottleneck", "risk", bottleneck_tag],
            "data": {
                "bottleneck_tag":   bottleneck_tag,
                "affected_count":   blocking_tags[bottleneck_tag],
                "blocking_tags":    dict(blocking_tags.most_common(5)),
            },
        })

    # Summary line
    summary = (
        f"Analyzed {total} tasks: {completion_rate}% complete. "
        f"Top areas: {', '.join(top_tags[:3])}. "
        + (f"Bottleneck: {bottleneck_tag}." if bottleneck_tag else "No bottleneck detected.")
    )

    return {
        "summary":          summary,
        "completion_rate":  completion_rate,
        "status_breakdown": dict(status_counts),
        "tag_frequency":    dict(tag_counter.most_common()),
        "bottleneck_tag":   bottleneck_tag,
        "top_tags":         top_tags,
        "owner_breakdown":  owner_breakdown,
        "insights":         insights,
    }
