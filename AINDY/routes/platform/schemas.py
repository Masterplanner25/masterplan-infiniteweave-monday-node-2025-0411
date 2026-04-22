from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator
from AINDY.platform_layer.nodus_script_store import (
    _NODUS_SCRIPT_REGISTRY,
    _SCRIPTS_DIR,
    _script_lock,
)


class FlowDefinition(BaseModel):
    name: str = Field(...)
    nodes: List[str] = Field(..., min_length=1)
    edges: Dict[str, List[str]] = Field(default_factory=dict)
    start: str = Field(...)
    end: List[str] = Field(..., min_length=1)
    overwrite: bool = Field(False)


class FlowRunRequest(BaseModel):
    state: Dict[str, Any] = Field(default_factory=dict)


class NodeRegistration(BaseModel):
    name: str = Field(...)
    type: str = Field(...)
    handler: str = Field(...)
    timeout_seconds: int = Field(10, ge=1, le=30)
    secret: Optional[str] = Field(None)
    overwrite: bool = Field(False)


class WebhookSubscription(BaseModel):
    event_type: str = Field(...)
    callback_url: str = Field(...)
    secret: Optional[str] = Field(None)


class NodusRunRequest(BaseModel):
    script: Optional[str] = Field(None)
    script_name: Optional[str] = Field(None)
    input: Dict[str, Any] = Field(default_factory=dict)
    error_policy: str = Field("fail")

    @model_validator(mode="after")
    def _require_source(self) -> "NodusRunRequest":
        if not self.script and not self.script_name:
            raise ValueError(
                "Provide either 'script' (inline source) or 'script_name' (uploaded script name)"
            )
        if self.script and self.script_name:
            raise ValueError("Provide 'script' or 'script_name', not both")
        if self.error_policy not in ("fail", "retry"):
            raise ValueError("error_policy must be 'fail' or 'retry'")
        return self


class NodusScriptUpload(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    content: str = Field(..., min_length=1)
    description: Optional[str] = Field(None, max_length=512)
    overwrite: bool = Field(False)


class NodusFlowRequest(BaseModel):
    flow_name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]+$")
    script: str = Field(..., min_length=1)
    input: Dict[str, Any] = Field(default_factory=dict)
    register: bool = Field(False)
    run: bool = Field(True)


class NodusScheduleRequest(BaseModel):
    script: Optional[str] = Field(None)
    script_name: Optional[str] = Field(None)
    cron: str = Field(...)
    input: Dict[str, Any] = Field(default_factory=dict)
    job_name: Optional[str] = Field(None, max_length=256)
    error_policy: str = Field("fail")
    max_retries: int = Field(3, ge=1, le=10)

    @model_validator(mode="after")
    def _require_source(self) -> "NodusScheduleRequest":
        if not self.script and not self.script_name:
            raise ValueError(
                "Provide either 'script' (inline source) or 'script_name' (uploaded script name)"
            )
        if self.script and self.script_name:
            raise ValueError("Provide 'script' or 'script_name', not both")
        if self.error_policy not in ("fail", "retry"):
            raise ValueError("error_policy must be 'fail' or 'retry'")
        return self


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scopes: List[str] = Field(..., min_length=1)
    expires_at: Optional[str] = Field(None)


class SyscallDispatchRequest(BaseModel):
    name: str = Field(..., examples=["sys.v1.memory.read"])
    payload: Dict[str, Any] = Field(default_factory=dict)
