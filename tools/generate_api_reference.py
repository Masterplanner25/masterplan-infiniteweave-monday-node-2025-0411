import os
import sys
import io

os.environ.setdefault("DATABASE_URL", "sqlite:///tmp_docgen.db")
os.environ.setdefault("SECRET_KEY", "docgen-placeholder")
os.environ.setdefault("ENV", "dev")
os.environ.setdefault("MONGO_REQUIRED", "false")
os.environ.setdefault("SKIP_MONGO_PING", "1")
os.environ.setdefault("AINDY_ALLOW_SQLITE", "1")
os.environ.setdefault("OPENAI_API_KEY", "docgen-openai-key")

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "buffer"):
        setattr(
            sys,
            _stream_name,
            io.TextIOWrapper(_stream.buffer, encoding="utf-8", errors="replace"),
        )

from collections import defaultdict
from pathlib import Path
from typing import Any

from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY
from AINDY.main import app


OUTPUT_PATH = Path("docs/api/API_REFERENCE.md")


def _resolve_ref(ref: str, openapi: dict[str, Any]) -> dict[str, Any]:
    node: Any = openapi
    for part in ref.lstrip("#/").split("/"):
        if isinstance(node, dict):
            node = node.get(part, {})
        else:
            return {}
    return node if isinstance(node, dict) else {}


def _merge_all_of(schema: dict[str, Any], openapi: dict[str, Any]) -> dict[str, Any]:
    parts = schema.get("allOf")
    if not isinstance(parts, list):
        return schema
    merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for part in parts:
        resolved = _resolve_schema(part, openapi)
        merged["properties"].update(resolved.get("properties", {}))
        merged["required"].extend(resolved.get("required", []))
        for key in ("title", "description"):
            if key not in merged and key in resolved:
                merged[key] = resolved[key]
    merged["required"] = sorted(set(merged["required"]))
    return merged


def _resolve_schema(schema: dict[str, Any] | None, openapi: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        return _resolve_schema(_resolve_ref(schema["$ref"], openapi), openapi)
    if "allOf" in schema:
        return _merge_all_of(schema, openapi)
    return schema


def _schema_type(schema: dict[str, Any], openapi: dict[str, Any]) -> str:
    resolved = _resolve_schema(schema, openapi)
    if not resolved:
        return "unspecified"
    if "enum" in resolved and isinstance(resolved["enum"], list):
        return "enum(" + ", ".join(map(str, resolved["enum"])) + ")"
    if "anyOf" in resolved and isinstance(resolved["anyOf"], list):
        return " | ".join(_schema_type(part, openapi) for part in resolved["anyOf"])
    if "oneOf" in resolved and isinstance(resolved["oneOf"], list):
        return " | ".join(_schema_type(part, openapi) for part in resolved["oneOf"])
    schema_type = resolved.get("type")
    if schema_type == "array":
        return f"array[{_schema_type(resolved.get('items', {}), openapi)}]"
    if schema_type == "object":
        properties = resolved.get("properties")
        if isinstance(properties, dict) and properties:
            return "object"
        if "additionalProperties" in resolved:
            return f"map[{_schema_type(resolved['additionalProperties'], openapi)}]"
        return "object"
    if isinstance(schema_type, list):
        return " | ".join(map(str, schema_type))
    if schema_type:
        return str(schema_type)
    return "unspecified"


def _compact_schema(schema: dict[str, Any] | None, openapi: dict[str, Any], *, include_required: bool = True) -> str:
    resolved = _resolve_schema(schema, openapi)
    if not resolved:
        return "unspecified"

    if "properties" in resolved and isinstance(resolved["properties"], dict):
        required = set(resolved.get("required", [])) if include_required else set()
        fields: list[str] = []
        for name in sorted(resolved["properties"]):
            prop = resolved["properties"][name]
            label = f"{name}: {_schema_type(prop, openapi)}"
            if include_required and name in required:
                label += " (required)"
            fields.append(label)
        return ", ".join(fields) if fields else "object"

    if resolved.get("type") == "array":
        return _schema_type(resolved, openapi)

    return _schema_type(resolved, openapi)


def _group_name(path: str, methods: dict[str, Any]) -> str:
    tags = methods.get("tags")
    if isinstance(tags, list) and tags:
        return str(tags[0])
    parts = [part for part in path.split("/") if part]
    return parts[0] if parts else "root"


def _first_success_response(operation: dict[str, Any]) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    responses = operation.get("responses", {})
    success_codes = sorted(code for code in responses if str(code).startswith("2"))
    if not success_codes:
        return None, None
    code = success_codes[0]
    return str(code), responses[code]


def _content_schema(content: dict[str, Any], openapi: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(content, dict) or not content:
        return {}
    if "application/json" in content:
        return _resolve_schema(content["application/json"].get("schema", {}), openapi)
    first_media = next(iter(content.values()))
    if isinstance(first_media, dict):
        return _resolve_schema(first_media.get("schema", {}), openapi)
    return {}


def build_http_section(openapi: dict[str, Any]) -> tuple[list[str], int]:
    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for path, path_item in sorted(openapi.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method in sorted(path_item):
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            operation = path_item[method]
            group = _group_name(path, operation)
            grouped[group].append((method.upper(), path, operation))

    lines = ["# API Reference", "", "## HTTP API Reference", ""]
    count = 0
    for group in sorted(grouped):
        lines.extend([f"### {group}", ""])
        for method, path, operation in grouped[group]:
            count += 1
            summary = operation.get("summary") or operation.get("description") or "No summary."
            lines.extend([f"#### {method} {path}", summary.strip(), ""])

            parameters = operation.get("parameters", [])
            if parameters:
                param_parts: list[str] = []
                for parameter in parameters:
                    resolved = _resolve_schema(parameter, openapi)
                    name = resolved.get("name", "unnamed")
                    location = resolved.get("in", "unknown")
                    schema = resolved.get("schema", {})
                    param_parts.append(f"{name} ({location}): {_schema_type(schema, openapi)}")
                lines.extend([f"**Parameters:** {', '.join(param_parts)}", ""])

            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                body = _resolve_schema(request_body, openapi)
                body_schema = _content_schema(body.get("content", {}), openapi)
                lines.extend([f"**Body:** {_compact_schema(body_schema, openapi)}", ""])

            code, response = _first_success_response(operation)
            if code and isinstance(response, dict):
                response_schema = _content_schema(response.get("content", {}), openapi)
                lines.extend([f"**Response {code}:** {_compact_schema(response_schema, openapi)}", ""])
    return lines, count


def _syscall_status(entry: Any) -> str:
    if getattr(entry, "deprecated", False):
        return "deprecated"
    if getattr(entry, "stable", True):
        return "stable"
    return "experimental"


def build_syscall_section() -> tuple[list[str], int]:
    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for name, entry in sorted(SYSCALL_REGISTRY.items()):
        parts = name.split(".")
        domain = parts[2] if len(parts) > 2 else "unknown"
        grouped[domain].append((name, entry))

    lines = ["## Syscall Reference", ""]
    count = 0
    for domain in sorted(grouped):
        lines.extend([f"### {domain}", ""])
        for name, entry in grouped[domain]:
            count += 1
            heading = name
            if getattr(entry, "deprecated", False) and getattr(entry, "replacement", None):
                heading += f" [DEPRECATED -> {entry.replacement}]"
            lines.extend([f"#### {heading}", getattr(entry, "description", "") or "No description.", ""])
            lines.append(f"**Status:** {_syscall_status(entry)}")
            lines.append(f"**Capabilities:** {getattr(entry, 'capability', 'unspecified')}")
            lines.append(f"**Input:** {_compact_schema(getattr(entry, 'input_schema', {}), {})}")
            lines.append(f"**Output:** {_compact_schema(getattr(entry, 'output_schema', {}), {})}")
            if getattr(entry, "replacement", None):
                lines.append(f"**Replacement:** {entry.replacement}")
            lines.append("")
    return lines, count


def generate_reference() -> tuple[int, int]:
    openapi = app.openapi()
    http_lines, route_count = build_http_section(openapi)
    syscall_lines, syscall_count = build_syscall_section()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(http_lines + syscall_lines).rstrip() + "\n"
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    return route_count, syscall_count


def main() -> int:
    route_count, syscall_count = generate_reference()
    print(f"Generated: {route_count} HTTP routes, {syscall_count} syscalls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
