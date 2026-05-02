#!/usr/bin/env python3
"""
cli.py — A.I.N.D.Y. Nodus CLI

Routes `nodus run <file>` through the A.I.N.D.Y. platform API instead of
executing locally.  Supports the full output surface including execution
result, trace summary, and optional bytecode disassembly.

Configuration
=============
Set via environment variables or CLI flags (flags take precedence):

  AINDY_API_URL     Base URL of the A.I.N.D.Y. server
                    Default: http://localhost:8000
  AINDY_API_TOKEN   JWT or platform API key for authentication

Usage
=====
  python cli.py run <file.nd> [options]
  python cli.py trace <trace_id>
  python cli.py upload <file.nd> [--name NAME] [--description TEXT]

Run options:
  --api-url URL          Override AINDY_API_URL
  --api-token TOKEN      Override AINDY_API_TOKEN
  --project-root PATH    Resolve relative file paths from this directory
  --input JSON           Input payload (JSON object) exposed as input_payload
  --error-policy POLICY  "fail" (default) or "retry"
  --max-retries N        Max retries when error-policy=retry (default 3)
  --trace                Fetch and display trace after execution
  --dump-bytecode        Show local bytecode disassembly before API execution
  --json                 Print raw JSON API response (no formatting)

Examples:
  python cli.py run script.nd
  python cli.py run script.nd --trace --input '{"goal": "Q2 growth"}'
  python cli.py run script.nd --dump-bytecode
  python cli.py trace <trace_id>
  python cli.py upload my_script.nd --name my_processor
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_API_URL = "http://localhost:8000"
_ENV_API_URL = "AINDY_API_URL"
_ENV_API_TOKEN = "AINDY_API_TOKEN"


# ---------------------------------------------------------------------------
# Helpers — config
# ---------------------------------------------------------------------------

def _api_url(override: str | None = None) -> str:
    return (override or os.environ.get(_ENV_API_URL) or _DEFAULT_API_URL).rstrip("/")


def _api_token(override: str | None = None) -> str | None:
    return override or os.environ.get(_ENV_API_TOKEN) or None


def _auth_headers(token: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if not token:
        return headers

    token = str(token).strip()  # 🔥 THIS LINE FIXES IT

    if token.startswith("aindy_"):
        headers["X-Platform-Key"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Helpers — HTTP
# ---------------------------------------------------------------------------

def _http_post(url: str, payload: dict, *, token: str | None) -> tuple[int, dict]:
    """POST JSON to *url*, return (status_code, response_dict)."""
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **_auth_headers(token),
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"detail": raw or str(exc)}
        return exc.code, data


def _http_get(url: str, *, token: str | None) -> tuple[int, dict]:
    """GET JSON from *url*, return (status_code, response_dict)."""
    headers = {"Accept": "application/json", **_auth_headers(token)}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"detail": raw or str(exc)}
        return exc.code, data


# ---------------------------------------------------------------------------
# Helpers — output formatting
# ---------------------------------------------------------------------------

def _print_err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _unwrap_platform_response(resp: dict) -> dict:
    """Return the inner Nodus payload when the API returns an execution envelope."""
    data = resp.get("data")
    if isinstance(data, dict) and any(
        key in data for key in ("nodus_status", "output_state", "events", "memory_writes", "run_id", "trace_id")
    ):
        return data
    return resp


def _fmt_run_result(resp: dict) -> str:
    """Format a /platform/nodus/run response as human-readable text."""
    resp = _unwrap_platform_response(resp)
    nodus_status = resp.get("nodus_status", "unknown")
    flow_status = resp.get("status", "?")
    trace_id = resp.get("trace_id") or ""
    run_id = resp.get("run_id") or ""
    error = resp.get("error")

    lines = [
        f"[AINDY Nodus] status={nodus_status}  flow={flow_status}  run_id={run_id[:12]}…",
    ]
    if trace_id:
        lines.append(f"              trace_id={trace_id}")

    output_state = resp.get("output_state") or {}
    if output_state:
        lines.append("")
        lines.append("output_state:")
        for k, v in output_state.items():
            lines.append(f"  {k}: {v!r}")

    events = resp.get("events") or []
    mem_writes = resp.get("memory_writes") or []
    lines.append("")
    lines.append(f"events_emitted: {len(events)}   memory_writes: {len(mem_writes)}")

    if error:
        lines.append("")
        lines.append(f"error: {error}")

    return "\n".join(lines)


def _fmt_trace(resp: dict) -> str:
    """Format a /platform/nodus/trace/{id} response."""
    resp = _unwrap_platform_response(resp)
    trace_id = resp.get("trace_id", "?")
    count = resp.get("count", 0)
    steps = resp.get("steps") or []
    summary = resp.get("summary") or {}

    lines = [
        "",
        f"Trace  {trace_id}  ({count} steps)",
        "-" * 60,
    ]

    # Summary block
    fn_counts = summary.get("fn_counts") or {}
    total_ms = summary.get("total_duration_ms", 0)
    err_count = summary.get("error_count", 0)
    fn_names = summary.get("fn_names") or []

    if fn_counts:
        counts_str = "  ".join(f"{fn}={n}" for fn, n in fn_counts.items())
        lines.append(f"fn_calls: {counts_str}")
    lines.append(f"duration: {total_ms}ms total")
    lines.append(f"errors:   {err_count}")
    if fn_names:
        lines.append(f"sequence: {' → '.join(fn_names)}")

    # Step list
    if steps:
        lines.append("")
        lines.append("Steps:")
        for step in steps:
            seq = step.get("sequence", "?")
            fn = (step.get("fn_name") or "?").ljust(14)
            dur = step.get("duration_ms")
            dur_str = f"{dur}ms" if dur is not None else "  -"
            status = step.get("status", "?")
            err = f"  [{step['error']}]" if step.get("error") else ""
            lines.append(f"  #{seq:<3} {fn}  {dur_str:>6}  {status}{err}")

    return "\n".join(lines)


def _fmt_upload_result(resp: dict) -> str:
    resp = _unwrap_platform_response(resp)
    name = resp.get("name", "?")
    size = resp.get("size_bytes", 0)
    uploaded_at = resp.get("uploaded_at", "?")
    return f"[AINDY Nodus] uploaded '{name}'  size={size}B  at={uploaded_at}"


# ---------------------------------------------------------------------------
# Helpers — local bytecode disassembly
# ---------------------------------------------------------------------------

def _local_disassemble(script: str, filename: str) -> str | None:
    """
    Return bytecode disassembly using the local Nodus VM, or None if
    the VM is not installed.  Errors are non-fatal.
    """
    try:
        from AINDY.nodus.tooling.runner import disassemble_source, format_disassembly_with_locs
        result = disassemble_source(script, filename=filename)
        if not result.get("ok"):
            return None
        return "\n".join(result.get("dis_pretty", []))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_run(
    file_path: str,
    *,
    api_url: str,
    token: str | None,
    project_root: str | None = None,
    input_payload: dict | None = None,
    error_policy: str = "fail",
    max_retries: int = 3,
    trace: bool = False,
    dump_bytecode: bool = False,
    json_output: bool = False,
) -> int:
    """Execute a Nodus script via POST /platform/nodus/run."""
    # Resolve file path
    if project_root:
        resolved = Path(project_root) / file_path
    else:
        resolved = Path(file_path)

    if not resolved.is_file():
        _print_err(f"File not found: {resolved}")
        return 1

    try:
        script = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        _print_err(f"Cannot read file: {exc}")
        return 1

    # Local bytecode dump before API call
    if dump_bytecode:
        dis = _local_disassemble(script, str(resolved))
        if dis:
            print(dis)
        else:
            _print_err(
                "[warn] --dump-bytecode requires the nodus package to be installed locally. "
                "Continuing with API execution."
            )

    # Build API request
    url = f"{api_url}/platform/nodus/run"
    payload: dict[str, Any] = {
        "script": script,
        "input": input_payload or {},
        "error_policy": error_policy,
    }

    status_code, resp = _http_post(url, payload, token=token)

    if status_code >= 400:
        detail = resp.get("detail") or resp
        _print_err(f"[AINDY Nodus] API error {status_code}: {detail}")
        return 1

    resp = _unwrap_platform_response(resp)

    if json_output:
        print(json.dumps(resp, indent=2))
    else:
        print(_fmt_run_result(resp))

    # Fetch and display trace
    if trace:
        trace_lookup_id = resp.get("run_id") or resp.get("trace_id")
        if not trace_lookup_id:
            _print_err("[warn] --trace: no run_id or trace_id in response")
        else:
            t_status, t_resp = _http_get(
                f"{api_url}/platform/nodus/trace/{trace_lookup_id}",
                token=token,
            )
            if t_status == 404:
                _print_err(
                    "[warn] --trace: no trace events found — "
                    "the script may not have called any host functions"
                )
            elif t_status >= 400:
                _print_err(f"[warn] --trace: fetch failed ({t_status})")
            else:
                if json_output:
                    print(json.dumps(t_resp, indent=2))
                else:
                    print(_fmt_trace(t_resp))

    # Exit code: 1 if script failed
    nodus_status = resp.get("nodus_status")
    if nodus_status and nodus_status != "success":
        return 1
    return 0


def cmd_trace(
    trace_id: str,
    *,
    api_url: str,
    token: str | None,
    json_output: bool = False,
) -> int:
    """Fetch and display a Nodus execution trace."""
    status_code, resp = _http_get(
        f"{api_url}/platform/nodus/trace/{trace_id}",
        token=token,
    )
    if status_code == 404:
        _print_err(f"[AINDY Nodus] trace not found: {trace_id!r}")
        return 1
    if status_code >= 400:
        _print_err(f"[AINDY Nodus] API error {status_code}: {resp.get('detail') or resp}")
        return 1

    resp = _unwrap_platform_response(resp)

    if json_output:
        print(json.dumps(resp, indent=2))
    else:
        print(_fmt_trace(resp))
    return 0


def cmd_upload(
    file_path: str,
    *,
    api_url: str,
    token: str | None,
    name: str | None = None,
    description: str | None = None,
    overwrite: bool = False,
    json_output: bool = False,
) -> int:
    """Upload a Nodus script via POST /platform/nodus/upload."""
    resolved = Path(file_path)
    if not resolved.is_file():
        _print_err(f"File not found: {resolved}")
        return 1

    try:
        content = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        _print_err(f"Cannot read file: {exc}")
        return 1

    script_name = name or resolved.stem
    url = f"{api_url}/platform/nodus/upload"
    payload: dict[str, Any] = {
        "name": script_name,
        "content": content,
        "overwrite": overwrite,
    }
    if description:
        payload["description"] = description

    status_code, resp = _http_post(url, payload, token=token)

    if status_code == 409:
        _print_err(
            f"[AINDY Nodus] Script {script_name!r} already exists. "
            "Use --overwrite to replace it."
        )
        return 1
    if status_code >= 400:
        _print_err(f"[AINDY Nodus] upload error {status_code}: {resp.get('detail') or resp}")
        return 1

    resp = _unwrap_platform_response(resp)

    if json_output:
        print(json.dumps(resp, indent=2))
    else:
        print(_fmt_upload_result(resp))
    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_simple_flags(
    args: list[str],
    flags_with_values: set[str],
    flags_no_values: set[str],
) -> tuple[list[str], dict]:
    """Minimal flag parser — returns (positional_args, flags_dict)."""
    positional: list[str] = []
    flags: dict[str, Any] = {}
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg in flags_no_values:
            flags[arg] = True
            idx += 1
        elif arg in flags_with_values:
            if idx + 1 >= len(args):
                raise ValueError(f"Missing value for {arg}")
            flags[arg] = args[idx + 1]
            idx += 2
        else:
            positional.append(arg)
            idx += 1
    return positional, flags


def _render_help() -> str:
    return "\n".join([
        "Usage: python cli.py <command> [options]",
        "",
        "Commands:",
        "  run <file.nd> [--api-url URL] [--api-token TOKEN] [--project-root PATH]",
        "                [--input JSON] [--error-policy fail|retry] [--max-retries N]",
        "                [--trace] [--dump-bytecode] [--json]",
        "",
        "  trace <trace_id> [--api-url URL] [--api-token TOKEN] [--json]",
        "",
        "  upload <file.nd> [--api-url URL] [--api-token TOKEN]",
        "                   [--name NAME] [--description TEXT] [--overwrite] [--json]",
        "",
        "Environment variables:",
        f"  {_ENV_API_URL:<20} Base URL  (default: {_DEFAULT_API_URL})",
        f"  {_ENV_API_TOKEN:<20} Bearer token / platform API key",
        "",
        "Examples:",
        "  python cli.py run script.nd",
        "  python cli.py run script.nd --trace --input '{\"goal\": \"Q2 growth\"}'",
        "  python cli.py run script.nd --dump-bytecode --error-policy retry",
        "  python cli.py trace <uuid>",
        "  python cli.py upload my_script.nd --name my_processor --overwrite",
    ])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv
    args = argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print(_render_help())
        return 0

    command = args[0]
    cmd_args = args[1:]

    # Common flags present in all subcommands
    _common_with_values = {"--api-url", "--api-token"}
    _common_no_values = {"--json"}

    if command == "run":
        flags_with_values = _common_with_values | {
            "--project-root", "--input", "--error-policy", "--max-retries",
        }
        flags_no_values = _common_no_values | {"--trace", "--dump-bytecode"}

        try:
            positional, flags = _parse_simple_flags(cmd_args, flags_with_values, flags_no_values)
        except ValueError as exc:
            _print_err(str(exc))
            return 1

        if not positional:
            _print_err("Usage: python cli.py run <file.nd>")
            return 1

        input_payload: dict | None = None
        if "--input" in flags:
            try:
                raw = json.loads(str(flags["--input"]))
                if not isinstance(raw, dict):
                    raise ValueError("--input must be a JSON object")
                input_payload = raw
            except (json.JSONDecodeError, ValueError) as exc:
                _print_err(f"Invalid --input: {exc}")
                return 1

        max_retries = 3
        if "--max-retries" in flags:
            try:
                max_retries = int(str(flags["--max-retries"]))
            except ValueError:
                _print_err(f"Invalid --max-retries: {flags['--max-retries']!r}")
                return 1

        error_policy = str(flags.get("--error-policy", "fail"))
        if error_policy not in ("fail", "retry"):
            _print_err("--error-policy must be 'fail' or 'retry'")
            return 1

        return cmd_run(
            positional[0],
            api_url=_api_url(flags.get("--api-url")),
            token=_api_token(flags.get("--api-token")),
            project_root=flags.get("--project-root"),
            input_payload=input_payload,
            error_policy=error_policy,
            max_retries=max_retries,
            trace="--trace" in flags,
            dump_bytecode="--dump-bytecode" in flags,
            json_output="--json" in flags,
        )

    if command == "trace":
        flags_with_values = _common_with_values.copy()
        try:
            positional, flags = _parse_simple_flags(cmd_args, flags_with_values, _common_no_values)
        except ValueError as exc:
            _print_err(str(exc))
            return 1

        if not positional:
            _print_err("Usage: python cli.py trace <trace_id>")
            return 1

        return cmd_trace(
            positional[0],
            api_url=_api_url(flags.get("--api-url")),
            token=_api_token(flags.get("--api-token")),
            json_output="--json" in flags,
        )

    if command == "upload":
        flags_with_values = _common_with_values | {"--name", "--description"}
        flags_no_values = _common_no_values | {"--overwrite"}

        try:
            positional, flags = _parse_simple_flags(cmd_args, flags_with_values, flags_no_values)
        except ValueError as exc:
            _print_err(str(exc))
            return 1

        if not positional:
            _print_err("Usage: python cli.py upload <file.nd>")
            return 1

        return cmd_upload(
            positional[0],
            api_url=_api_url(flags.get("--api-url")),
            token=_api_token(flags.get("--api-token")),
            name=flags.get("--name"),
            description=flags.get("--description"),
            overwrite="--overwrite" in flags,
            json_output="--json" in flags,
        )

    _print_err(f"Unknown command: {command!r}  (use --help)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
