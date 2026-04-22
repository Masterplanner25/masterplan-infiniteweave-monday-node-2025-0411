from fastapi import APIRouter, Depends

from AINDY.services.auth_service import get_current_user
from AINDY.routes.platform.flows_router import (
    create_flow,
    delete_flow,
    get_flow,
    list_flows,
    run_flow_endpoint,
    router as flows_router,
)
from AINDY.routes.platform.keys_router import create_key, get_key, list_keys, revoke_key, router as keys_router
from AINDY.routes.platform.nodes_router import delete_node, get_node, list_nodes, register_node, router as nodes_router
from AINDY.routes.platform.nodus_flow_router import compile_and_run_nodus_flow, router as nodus_flow_router
from AINDY.routes.platform.nodus_router import list_nodus_scripts, run_nodus_script, upload_nodus_script, router as nodus_router
from AINDY.routes.platform.nodus_schedule_router import create_nodus_schedule, delete_nodus_schedule, list_nodus_schedules, router as nodus_schedule_router
from AINDY.routes.platform.nodus_shared import (
    _NODUS_SCRIPT_REGISTRY,
    _SCRIPTS_DIR,
    _ensure_nodus_flow_registered,
    _format_nodus_response,
    _run_flow_platform,
    _run_nodus_script,
    _validate_nodus_source,
    list_nodus_script_summaries,
    load_named_nodus_script_or_404,
    nodus_script_exists,
    save_nodus_script,
)
from AINDY.routes.platform.platform_ops_router import (
    dispatch_syscall,
    get_nodus_trace,
    get_tenant_usage,
    list_memory_path,
    list_syscalls,
    memory_trace,
    memory_tree,
    router as platform_ops_router,
)
from AINDY.routes.platform.schemas import NodusRunRequest, NodusScriptUpload
from AINDY.routes.platform.webhooks_router import (
    create_webhook,
    delete_webhook_subscription,
    get_webhook_subscription,
    list_webhook_subscriptions,
    router as webhooks_router,
)

router = APIRouter(prefix="/platform", tags=["Platform"], dependencies=[Depends(get_current_user)])
for child in (
    flows_router,
    nodes_router,
    webhooks_router,
    keys_router,
    nodus_router,
    nodus_flow_router,
    nodus_schedule_router,
    platform_ops_router,
):
    router.include_router(child)
