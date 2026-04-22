from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.nodus_shared import _validate_nodus_source
from AINDY.routes.platform.schemas import NodusFlowRequest
from AINDY.services.auth_service import get_current_user

router = APIRouter()


@router.post("/nodus/flow", response_model=None)
@limiter.limit("30/minute")
def compile_and_run_nodus_flow(request: Request, body: NodusFlowRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["sub"])
    _validate_nodus_source(body.script, field="script")

    def handler(_ctx):
        from AINDY.runtime.nodus_flow_compiler import compile_nodus_flow
        from AINDY.runtime.flow_engine import PersistentFlowRunner, register_flow
        from AINDY.utils.uuid_utils import normalize_uuid
        from AINDY.platform_layer.user_ids import require_user_id

        try:
            compiled_flow = compile_nodus_flow(body.script, body.flow_name)
        except (ValueError, RuntimeError) as exc:
            return {"flow_name": body.flow_name, "compiled": False, "error": str(exc)}

        response: Dict[str, Any] = {
            "flow_name": body.flow_name,
            "compiled": True,
            "start": compiled_flow["start"],
            "nodes": list(compiled_flow["edges"].keys()),
            "end": compiled_flow["end"],
            "registered": False,
        }
        if body.register:
            register_flow(body.flow_name, compiled_flow)
            response["registered"] = True
        if body.run:
            import uuid as _uuid
            from AINDY.core.execution_gate import flow_result_to_envelope, require_execution_unit

            uid = require_user_id(user_id)
            correlation = str(_uuid.uuid4())
            pre_eu = require_execution_unit(
                db=db,
                eu_type="flow",
                user_id=str(uid),
                source_type="nodus_flow_run",
                source_id=correlation,
                correlation_id=correlation,
                extra={"flow_name": body.flow_name, "workflow_type": "nodus_flow"},
            )
            result = PersistentFlowRunner(flow=compiled_flow, db=db, user_id=uid, workflow_type="nodus_flow").start(initial_state=dict(body.input), flow_name=body.flow_name)
            try:
                if pre_eu is not None:
                    from AINDY.core.execution_unit_service import ExecutionUnitService

                    eus = ExecutionUnitService(db)
                    if result.get("run_id"):
                        eus.link_flow_run(pre_eu.id, result["run_id"])
                    eus.update_status(pre_eu.id, "completed" if result.get("status") == "SUCCESS" else "failed")
            except Exception:
                pass
            response["run_result"] = {"status": result.get("status"), "run_id": result.get("run_id"), "trace_id": result.get("trace_id"), "error": result.get("error"), "execution_envelope": flow_result_to_envelope(result)}
        return response

    return execute_with_pipeline_sync(
        request=request,
        route_name="platform.nodus.flow",
        handler=handler,
        user_id=user_id,
        input_payload={"flow_name": body.flow_name, "run": body.run, "register": body.register},
        metadata={"db": db},
    )
