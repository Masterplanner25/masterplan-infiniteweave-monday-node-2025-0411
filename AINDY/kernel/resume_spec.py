from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Callable, Protocol


RESUME_HANDLER_EU = "execution_unit.resume"


class ResumeCallbackBuilder(Protocol):
    def __call__(self, spec: "ResumeSpec") -> Callable[[], None]:
        ...


@dataclass
class ResumeSpec:
    handler: str
    eu_id: str
    tenant_id: str
    run_id: str
    eu_type: str | None = None


_RESUME_CALLBACK_BUILDERS: dict[str, ResumeCallbackBuilder] = {}


def spec_to_json(spec: ResumeSpec) -> str:
    return json.dumps(asdict(spec))


def spec_from_json(raw: str) -> ResumeSpec:
    return ResumeSpec(**json.loads(raw))


def register_resume_callback_builder(handler: str, builder: ResumeCallbackBuilder) -> None:
    _RESUME_CALLBACK_BUILDERS[handler] = builder


def _build_execution_unit_resume_callback(spec: ResumeSpec) -> Callable[[], None]:
    from AINDY.core.execution_unit_service import ExecutionUnitService
    from AINDY.db import SessionLocal

    def _resume():
        with SessionLocal() as db:
            ExecutionUnitService(db).resume_execution_unit(spec.eu_id)

    return _resume


register_resume_callback_builder(RESUME_HANDLER_EU, _build_execution_unit_resume_callback)


def build_callback_from_spec(spec: ResumeSpec):
    """Reconstruct an executable callback from a ResumeSpec."""
    builder = _RESUME_CALLBACK_BUILDERS.get(spec.handler)
    if builder is not None:
        return builder(spec)
    raise ValueError(f"Unknown resume handler: {spec.handler}")
