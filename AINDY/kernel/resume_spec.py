from __future__ import annotations

from dataclasses import asdict, dataclass
import json


RESUME_HANDLER_EU = "execution_unit.resume"


@dataclass
class ResumeSpec:
    handler: str
    eu_id: str
    tenant_id: str
    run_id: str
    eu_type: str | None = None


def spec_to_json(spec: ResumeSpec) -> str:
    return json.dumps(asdict(spec))


def spec_from_json(raw: str) -> ResumeSpec:
    return ResumeSpec(**json.loads(raw))


def build_callback_from_spec(spec: ResumeSpec):
    """Reconstruct an executable callback from a ResumeSpec."""
    if spec.handler == RESUME_HANDLER_EU:
        try:
            from apps.execution_units.services.execution_unit_service import ExecutionUnitService
        except ImportError:
            from AINDY.core.execution_unit_service import ExecutionUnitService
        from AINDY.db import SessionLocal

        def _resume():
            with SessionLocal() as db:
                ExecutionUnitService(db).resume_execution_unit(spec.eu_id)

        return _resume
    raise ValueError(f"Unknown resume handler: {spec.handler}")
