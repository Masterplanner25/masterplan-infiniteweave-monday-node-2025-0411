import sys

from AINDY.runtime.flow_engine.entrypoints import (
    _execute_intent_direct,
    _run_flow_direct,
    compile_plan_to_flow,
    execute_intent,
    generate_plan_from_intent,
    run_flow,
)
from AINDY.runtime.flow_engine.event_router import record_outcome, route_event
from AINDY.runtime.flow_engine.node_executor import (
    POLICY,
    _FLOW_RETRY_POLICY,
    enforce_policy,
    execute_node,
    resolve_next_node,
)
from AINDY.runtime.flow_engine.registry import (
    FLOW_REGISTRY,
    NODE_REGISTRY,
    _registry_flow_plan,
    register_flow,
    register_node,
    select_strategy,
)
from AINDY.runtime.flow_engine.runner import PersistentFlowRunner
from AINDY.runtime.flow_engine.serialization import (
    _extract_async_handoff,
    _extract_execution_result,
    _extract_next_action,
    _format_execution_response,
    _json_safe,
    _serialize_flow_events,
)
from AINDY.runtime.flow_engine.shared import emit_error_event, emit_system_event, logger

if __name__ == "AINDY.runtime.flow_engine":
    flow_engine_module = sys.modules[__name__]
    sys.modules.setdefault("runtime.flow_engine", flow_engine_module)
    if "runtime" in sys.modules:
        setattr(sys.modules["runtime"], "flow_engine", flow_engine_module)
elif __name__ == "runtime.flow_engine":
    flow_engine_module = sys.modules[__name__]
    sys.modules.setdefault("AINDY.runtime.flow_engine", flow_engine_module)
    if "AINDY.runtime" in sys.modules:
        setattr(sys.modules["AINDY.runtime"], "flow_engine", flow_engine_module)


def __getattr__(name: str):
    if name == "select" + "_strategy":
        return _registry_flow_plan
    raise AttributeError(name)
