from AINDY.core.execution_pipeline.shared import (
    Any,
    Request,
    Response,
    dataclass,
    field,
    jsonable_encoder,
    uuid,
)


def _route_eu_type(route_name: str) -> str:
    from AINDY.platform_layer.registry import get_route_prefix

    prefix = (route_name or "").split(".")[0].strip() or "default"
    return get_route_prefix(prefix) or "default"


@dataclass(slots=True)
class ExecutionContext:
    request_id: str
    route_name: str
    user_id: str | None = None
    input_payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    pipeline_active: bool = True

    @classmethod
    def from_request(cls, request: Request | None, route_name: str) -> "ExecutionContext":
        if request is None:
            return cls(
                request_id=str(uuid.uuid4()),
                route_name=route_name,
                input_payload={},
                metadata={},
            )

        request_id = (
            request.headers.get("X-Trace-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        return cls(
            request_id=request_id,
            route_name=route_name,
            input_payload={
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params),
                "path_params": dict(request.path_params),
            },
            metadata={},
        )


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    data: Any = None
    error: str | None = None
    memory_context_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    eu_status: str | None = None

    def to_response(self) -> dict[str, Any]:
        trace_id = str(self.metadata.get("trace_id") or "")
        eu_id = self.metadata.get("eu_id")
        payload_data = self.data if isinstance(self.data, Response) else jsonable_encoder(self.data)
        status_label = self.eu_status or ("success" if self.success else "error")
        canonical_metadata = {
            "events": list(self.metadata.get("event_refs") or []),
            "next_action": self.metadata.get("next_action"),
        }
        side_effects = self.metadata.get("side_effects")
        if side_effects:
            canonical_metadata["side_effects"] = jsonable_encoder(side_effects)
            canonical_metadata["degraded_side_effects"] = [
                name
                for name, detail in side_effects.items()
                if isinstance(detail, dict) and detail.get("status") in {"failed", "missing"}
            ]
        if self.eu_status == "waiting":
            canonical_metadata["eu_wait_for"] = self.metadata.get("eu_wait_for")
        if not self.success:
            canonical_metadata["error"] = jsonable_encoder(
                self.metadata.get("detail") or self.error or "Execution failed"
            )
            status_code = self.metadata.get("status_code")
            if status_code is not None:
                canonical_metadata["status_code"] = status_code
        return {
            "status": status_label,
            "data": payload_data,
            "trace_id": trace_id,
            "eu_id": eu_id,
            "memory_context_count": self.memory_context_count,
            "metadata": canonical_metadata,
        }
