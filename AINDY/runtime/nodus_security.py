from __future__ import annotations

import ast
import re
from typing import Any, Optional

from AINDY.agents.capability_service import check_execution_capability, validate_token


class NodusSecurityError(ValueError):
    pass


DEFAULT_READONLY_OPERATIONS = [
    "recall",
    "recall_tool",
    "suggest",
    "recall_from",
    "recall_all",
]

ALLOWED_OPERATION_CAPABILITIES = {
    "recall": "read_memory",
    "recall_tool": "read_memory",
    "suggest": "read_memory",
    "recall_from": "read_memory",
    "recall_all": "read_memory",
    "remember": "write_memory",
    "record_outcome": "write_memory",
    "share": "write_memory",
}

RESTRICTED_OPERATION_SUMMARY = {
    "system_access": [
        "import",
        "os",
        "sys",
        "subprocess",
        "eval",
        "exec",
        "__import__",
    ],
    "file_access": [
        "open(",
        "pathlib",
        "shutil",
        "write(",
        "read(",
    ],
    "network_calls": [
        "socket",
        "requests",
        "urllib",
        "http://",
        "https://",
    ],
}

MAX_TASK_CODE_LENGTH = 12000

_FORBIDDEN_NODE_TYPES = (
    ast.Import,
    ast.ImportFrom,
)

_FORBIDDEN_FUNC_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",
        "breakpoint",
        "input",
    }
)

_FORBIDDEN_ATTR_CHAINS = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "pathlib",
        "shutil",
        "requests",
        "urllib",
        "http",
        "builtins",
    }
)

_FORBIDDEN_DUNDERS = frozenset(
    {
        "__builtins__",
        "__import__",
        "__class__",
        "__bases__",
        "__mro__",
        "__subclasses__",
    }
)


def normalize_allowed_operations(value: Optional[list[str]]) -> list[str]:
    operations = value or DEFAULT_READONLY_OPERATIONS
    normalized = sorted(
        {
            item.strip()
            for item in operations
            if isinstance(item, str) and item.strip() in ALLOWED_OPERATION_CAPABILITIES
        }
    )
    if not normalized:
        raise NodusSecurityError("No valid allowed_operations were provided.")
    return normalized


def _is_forbidden_name(node: ast.AST) -> bool:
    if isinstance(node, ast.Name) and node.id in _FORBIDDEN_FUNC_NAMES:
        return True
    if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_FUNC_NAMES:
        return True
    return False


def _is_forbidden_attr(node: ast.AST) -> bool:
    """Flag attribute/name access whose root or member name is forbidden."""
    if isinstance(node, ast.Name):
        return node.id in _FORBIDDEN_ATTR_CHAINS
    if isinstance(node, ast.Attribute):
        current: ast.AST | None = node
        while isinstance(current, ast.Attribute):
            if current.attr in _FORBIDDEN_ATTR_CHAINS:
                return True
            current = current.value
        if isinstance(current, ast.Name) and current.id in _FORBIDDEN_ATTR_CHAINS:
            return True
    return False


def validate_nodus_source(task_code: str) -> None:
    source = str(task_code or "")
    if not source.strip():
        raise NodusSecurityError("Operation code is required.")
    if len(source) > MAX_TASK_CODE_LENGTH:
        raise NodusSecurityError("Operation code exceeds maximum allowed length.")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise NodusSecurityError(f"Script has a syntax error: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODE_TYPES):
            raise NodusSecurityError("system import is not allowed")
        if isinstance(node, ast.Call):
            func = node.func
            if _is_forbidden_name(func):
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                raise NodusSecurityError(f"'{name}' is not allowed in Nodus scripts")
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = getattr(node, "id", None) or getattr(node, "attr", None)
            if name in _FORBIDDEN_DUNDERS:
                raise NodusSecurityError(f"Access to '{name}' is not allowed in Nodus scripts")
        if _is_forbidden_attr(node):
            name = getattr(node, "id", None) or getattr(node, "attr", None)
            raise NodusSecurityError(f"Access to '{name}' is not allowed in Nodus scripts")
        if isinstance(node, ast.Global):
            raise NodusSecurityError("'global' statement is not allowed")
        if isinstance(node, ast.Nonlocal):
            raise NodusSecurityError("'nonlocal' statement is not allowed")


def validate_requested_operation_usage(task_code: str, allowed_operations: list[str]) -> None:
    source = str(task_code or "")
    allowed = set(allowed_operations)
    for operation_name in ALLOWED_OPERATION_CAPABILITIES:
        if re.search(rf"\b{re.escape(operation_name)}\s*\(", source) and operation_name not in allowed:
            raise NodusSecurityError(
                f"Operation '{operation_name}' is used by the operation but not granted in allowed_operations."
            )


def required_capabilities_for_operations(allowed_operations: list[str]) -> list[str]:
    return sorted(
        {
            capability
            for operation_name in allowed_operations
            for capability in [ALLOWED_OPERATION_CAPABILITIES.get(operation_name)]
            if capability
        }
    )


def authorize_nodus_execution(
    *,
    task_code: str,
    allowed_operations: Optional[list[str]],
    capability_token: Optional[dict],
    execution_id: Optional[str],
    user_id: str,
) -> dict[str, Any]:
    validate_nodus_source(task_code)
    normalized_operations = normalize_allowed_operations(allowed_operations)
    validate_requested_operation_usage(task_code, normalized_operations)

    required_capabilities = required_capabilities_for_operations(normalized_operations)
    token_used = capability_token is not None

    if token_used:
        if not execution_id:
            raise NodusSecurityError("execution_id is required when capability_token is provided.")
        token_validation = validate_token(
            token=capability_token,
            run_id=str(execution_id),
            user_id=str(user_id),
        )
        if not token_validation["ok"]:
            raise NodusSecurityError(token_validation["error"] or "Capability token validation failed.")

        execute_check = check_execution_capability(
            token=capability_token,
            run_id=str(execution_id),
            user_id=str(user_id),
            capability_name="execute_flow",
        )
        if not execute_check["ok"]:
            raise NodusSecurityError(execute_check["error"] or "Execution capability denied.")

        granted_capabilities = set(token_validation.get("allowed_capabilities", []))
        for capability_name in required_capabilities:
            if capability_name not in granted_capabilities:
                raise NodusSecurityError(
                    f"Capability '{capability_name}' not granted by execution token."
                )
    else:
        disallowed_without_token = [
            op for op in normalized_operations if ALLOWED_OPERATION_CAPABILITIES.get(op) == "write_memory"
        ]
        if disallowed_without_token:
            raise NodusSecurityError(
                "Write-capable Nodus operations require a scoped capability token."
            )

    return {
        "allowed_operations": normalized_operations,
        "required_capabilities": required_capabilities,
        "token_used": token_used,
        "restricted_operations": RESTRICTED_OPERATION_SUMMARY,
    }

