from __future__ import annotations


def __getattr__(name: str):
    from apps.agent.models import agent_run as _m

    return getattr(_m, name)
