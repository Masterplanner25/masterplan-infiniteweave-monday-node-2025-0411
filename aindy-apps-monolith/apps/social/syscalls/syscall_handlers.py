"""Social domain syscall handlers."""

from __future__ import annotations

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall


def _handle_adapt_linkedin(payload: dict, ctx: SyscallContext) -> dict:
    from apps.social.public import adapt_linkedin_metrics

    canonical = adapt_linkedin_metrics(payload.get("data", {}))
    return {"canonical": canonical}


def _handle_social_performance_signals(payload: dict, ctx: SyscallContext) -> dict:
    from apps.social.public import get_social_performance_signals

    signals = list(
        get_social_performance_signals(
            user_id=payload.get("user_id") or ctx.user_id or None,
            limit=int(payload.get("limit", 3) or 3),
        )
        or []
    )
    return {"signals": signals, "count": len(signals)}


def register_all() -> None:
    register_syscall(
        "sys.v1.social.adapt_linkedin",
        _handle_adapt_linkedin,
        "social.read",
        "Adapt LinkedIn metrics into canonical analytics format",
        input_schema={"properties": {"data": {"type": "dict"}}},
        stable=False,
    )
    register_syscall(
        "sys.v1.social.get_performance_signals",
        _handle_social_performance_signals,
        "social.read",
        "Return recent social performance signals",
        input_schema={
            "properties": {
                "user_id": {"type": "string"},
                "limit": {"type": "integer"},
            }
        },
        stable=False,
    )
