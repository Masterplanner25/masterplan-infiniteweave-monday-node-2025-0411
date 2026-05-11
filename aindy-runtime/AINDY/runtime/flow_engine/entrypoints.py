from AINDY.runtime.flow_engine.registry import FLOW_REGISTRY, _registry_flow_plan
from AINDY.runtime.flow_engine.runner import PersistentFlowRunner
from AINDY.runtime.flow_engine.shared import Session, logger, normalize_uuid


def generate_plan_from_intent(intent: dict) -> dict:
    from AINDY.platform_layer.registry import get_flow_plan

    workflow_type = intent.get("workflow_type", "generic")
    return (
        get_flow_plan(workflow_type)
        or get_flow_plan("generic")
        or {"steps": ["execute", "store_result"]}
    )


def compile_plan_to_flow(plan: dict) -> dict:
    steps = plan["steps"]
    if not steps:
        raise ValueError("Plan must have at least one step")

    flow: dict = {"start": steps[0], "edges": {}, "end": [steps[-1]]}
    for index in range(len(steps) - 1):
        flow["edges"][steps[index]] = [steps[index + 1]]
    return flow


def _execute_intent_direct(intent_data: dict, db: Session, user_id: str = None) -> dict:
    from AINDY.runtime import enforce_engine_boundary

    intent_type = intent_data.get("workflow_type", "generic")
    enforce_engine_boundary(
        entrypoint="flow.execute_intent",
        workflow_type=str(intent_type),
    )
    flow = _registry_flow_plan(intent_type, db, user_id)
    if not flow:
        plan = generate_plan_from_intent(intent_data)
        flow = compile_plan_to_flow(plan)
        flow_name = f"generated_{intent_type}"
    else:
        flow_name = f"registered_{intent_type}"

    FLOW_REGISTRY[flow_name] = flow
    normalized_user_id = normalize_uuid(user_id) if user_id is not None else None
    runner = PersistentFlowRunner(
        flow=flow,
        db=db,
        user_id=normalized_user_id,
        workflow_type=intent_type,
    )
    return runner.start(initial_state=intent_data, flow_name=flow_name)


def execute_intent(intent_data: dict, db: Session, user_id: str = None) -> dict:
    from AINDY.runtime import enforce_engine_boundary

    intent_type = intent_data.get("workflow_type", "generic")
    enforce_engine_boundary(
        entrypoint="flow.execute_intent",
        workflow_type=str(intent_type),
    )
    if not user_id:
        logger.debug(
            "[execute_intent] no user_id - executing directly "
            "(syscall layer requires identity)"
        )
        return _execute_intent_direct(intent_data, db, user_id)

    import uuid as _uuid
    from AINDY.kernel.syscall_dispatcher import (
        _EU_ID_CTX,
        _TRACE_ID_CTX,
        SyscallContext,
        get_dispatcher,
    )

    trace_id = _TRACE_ID_CTX.get() or str(_uuid.uuid4())
    eu_id = _EU_ID_CTX.get() or trace_id
    ctx = SyscallContext(
        execution_unit_id=eu_id,
        user_id=str(user_id),
        capabilities=["flow.run", "flow.execute"],
        trace_id=trace_id,
        metadata={"_db": db},
    )
    result = get_dispatcher().dispatch(
        "sys.v1.flow.execute_intent",
        {"intent_data": intent_data},
        ctx,
    )
    if result["status"] == "error":
        raise RuntimeError(
            f"sys.v1.flow.execute_intent failed: {result.get('error', '')}"
        )
    return result["data"]["intent_result"]


def _run_flow_direct(
    flow_name: str,
    state: dict,
    db: Session = None,
    user_id: str = None,
) -> dict:
    from AINDY.runtime import enforce_engine_boundary

    enforce_engine_boundary(entrypoint="flow.run", flow_name=str(flow_name))
    flow = FLOW_REGISTRY.get(flow_name)
    if not flow:
        raise KeyError(
            f"Flow '{flow_name}' not registered. "
            f"Available: {sorted(FLOW_REGISTRY.keys())}"
        )
    normalized_user_id = normalize_uuid(user_id) if user_id is not None else None
    runner = PersistentFlowRunner(
        flow=flow,
        db=db,
        user_id=normalized_user_id,
        workflow_type=flow_name,
    )
    return runner.start(initial_state=dict(state), flow_name=flow_name)


def run_flow(flow_name: str, state: dict, db: Session = None, user_id: str = None) -> dict:
    from AINDY.runtime import enforce_engine_boundary

    enforce_engine_boundary(entrypoint="flow.run", flow_name=str(flow_name))
    if not user_id:
        logger.debug(
            "[run_flow] no user_id - executing '%s' directly "
            "(syscall layer requires identity)",
            flow_name,
        )
        return _run_flow_direct(flow_name, state or {}, db, user_id)

    import uuid as _uuid
    from AINDY.kernel.syscall_dispatcher import (
        _EU_ID_CTX,
        _TRACE_ID_CTX,
        SyscallContext,
        get_dispatcher,
    )

    trace_id = _TRACE_ID_CTX.get() or str(_uuid.uuid4())
    eu_id = _EU_ID_CTX.get() or trace_id
    ctx = SyscallContext(
        execution_unit_id=eu_id,
        user_id=str(user_id),
        capabilities=["flow.run"],
        trace_id=trace_id,
        metadata={"_db": db},
    )
    result = get_dispatcher().dispatch(
        "sys.v1.flow.run",
        {
            "flow_name": flow_name,
            "initial_state": state or {},
            "workflow_type": flow_name,
        },
        ctx,
    )
    if result["status"] == "error":
        error_msg = result.get("error", "")
        if "not registered" in error_msg or "unknown flow" in error_msg.lower():
            raise KeyError(error_msg)
        raise RuntimeError(f"sys.v1.flow.run failed: {error_msg}")
    return result["data"]["flow_result"]
