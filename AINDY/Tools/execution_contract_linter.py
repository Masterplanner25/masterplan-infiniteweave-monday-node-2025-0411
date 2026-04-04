from __future__ import annotations

import argparse
import ast
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
ROUTES_DIR = ROOT / "routes"
SERVICES_DIR = ROOT / "services"
CORE_PIPELINE_FILE = ROOT / "core" / "execution_pipeline.py"
SIGNAL_HELPER_FILE = ROOT / "core" / "execution_signal_helper.py"
MEMORY_ENGINE_FILE = ROOT / "services" / "memory_capture_engine.py"
SYSTEM_EVENT_FILE = ROOT / "services" / "system_event_service.py"
AGENT_EVENT_SERVICE_FILE = ROOT / "services" / "agent_event_service.py"
ALLOWED_TEST_DIRECT_MEMORY_FILES = {
    (ROOT / "tests" / "integration" / "test_memory_bridge_v5.py").resolve(),
    (ROOT / "tests" / "system" / "test_system_event_invariants.py").resolve(),
}
SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "node_modules",
    "dist",
    "build",
}


@dataclass(slots=True)
class Violation:
    path: Path
    line: int
    violation_type: str
    message: str
    suggestion: str


class RouteFunctionAnalyzer(ast.NodeVisitor):
    def __init__(self, fn_node: ast.AST, valid_wrapper_names: set[str]):
        self.fn_node = fn_node
        self.valid_wrapper_names = valid_wrapper_names
        self.calls_pipeline = False
        self.raw_return_lines: list[int] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name in {"execute_with_pipeline", "execute_with_pipeline_sync", "run_execution"} | self.valid_wrapper_names:
            self.calls_pipeline = True
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if _is_raw_response_return(node.value):
            self.raw_return_lines.append(node.lineno)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self.fn_node:
            for stmt in node.body:
                self.visit(stmt)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self.fn_node:
            for stmt in node.body:
                self.visit(stmt)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _is_router_decorated(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "router":
                return True
    return False


def _is_raw_response_return(value: ast.AST | None) -> bool:
    if value is None:
        return False
    if isinstance(value, (ast.Dict, ast.List)):
        return True
    if isinstance(value, ast.Call):
        name = _call_name(value)
        if name in {"JSONResponse", "Response"}:
            return True
    return False


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def _parse_file(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception:
        return None


def lint_routes() -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(_iter_python_files(ROUTES_DIR)):
        tree = _parse_file(path)
        if tree is None:
            continue
        valid_wrapper_names = _find_valid_wrapper_names(tree)
        for node in tree.body:
            if not _is_router_decorated(node):
                continue
            analyzer = RouteFunctionAnalyzer(node, valid_wrapper_names)
            analyzer.visit(node)
            if not analyzer.calls_pipeline:
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        violation_type="route_pipeline_missing",
                        message="ExecutionContract violation: route must use execution pipeline",
                        suggestion="Wrap endpoint body in handler(ctx) and return execute_with_pipeline(...).",
                    )
                )
            for line in analyzer.raw_return_lines:
                violations.append(
                    Violation(
                        path=path,
                        line=line,
                        violation_type="raw_response_return",
                        message="ExecutionContract violation: raw response bypass",
                        suggestion="Return raw data from handler(ctx) and let the pipeline adapt the response.",
                    )
                )
    return violations


def _find_valid_wrapper_names(tree: ast.AST) -> set[str]:
    valid: set[str] = set()
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        analyzer = RouteFunctionAnalyzer(node, set())
        analyzer.visit(node)
        if analyzer.calls_pipeline:
            valid.add(node.name)
    return valid


def lint_memory_usage() -> list[Violation]:
    violations: list[Violation] = []
    allowed = {
        CORE_PIPELINE_FILE.resolve(),
        SIGNAL_HELPER_FILE.resolve(),
        MEMORY_ENGINE_FILE.resolve(),
    }
    for path in sorted(_iter_python_files(ROOT)):
        if path.resolve() in allowed:
            continue
        if path.resolve() in ALLOWED_TEST_DIRECT_MEMORY_FILES:
            continue
        tree = _parse_file(path)
        if tree is None:
            continue
        imported_memory_engine = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "memory.memory_capture_engine":
                imported_memory_engine = True
            if isinstance(node, ast.Call):
                if _is_memory_capture_call(node) and imported_memory_engine:
                    violations.append(
                        Violation(
                            path=path,
                            line=node.lineno,
                            violation_type="direct_memory_call",
                            message="ExecutionContract violation: memory must be pipeline-controlled",
                            suggestion="Return execution_signals.memory from the handler instead of calling memory directly.",
                        )
                    )
    return violations


def lint_event_usage() -> list[Violation]:
    violations: list[Violation] = []
    allowed = {
        CORE_PIPELINE_FILE.resolve(),
        SIGNAL_HELPER_FILE.resolve(),
        SYSTEM_EVENT_FILE.resolve(),
        AGENT_EVENT_SERVICE_FILE.resolve(),
    }
    for path in sorted(_iter_python_files(ROOT)):
        if path.resolve() in allowed:
            continue
        tree = _parse_file(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                if name in {"emit_event", "emit_system_event"}:
                    violations.append(
                        Violation(
                            path=path,
                            line=node.lineno,
                            violation_type="direct_event_emit",
                            message="ExecutionContract violation: events must be pipeline-controlled",
                            suggestion="Return execution_signals.events and let the pipeline emit them.",
                        )
                    )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "SystemEvent":
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        violation_type="system_event_model_use",
                        message="ExecutionContract violation: events must be pipeline-controlled",
                        suggestion="Emit through pipeline signals instead of constructing event records directly.",
                    )
                )
    return violations


def lint_service_execution() -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(_iter_python_files(SERVICES_DIR)):
        if path.name in {"execution_service.py", "execution_envelope.py"}:
            continue
        tree = _parse_file(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                if name == "run_execution":
                    violations.append(
                        Violation(
                            path=path,
                            line=node.lineno,
                            violation_type="service_execution_entry",
                            message="ExecutionContract violation: service cannot act as execution entry",
                            suggestion="Move execution entry to the route layer and call the service from handler(ctx).",
                        )
                    )
    return violations


def _is_memory_capture_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"capture", "evaluate_and_capture"}:
        return False
    base = node.func.value
    if isinstance(base, ast.Name):
        return base.id in {"engine", "memory_engine", "capture_engine"}
    return False


def render_report(violations: list[Violation]) -> str:
    lines = []
    for item in sorted(violations, key=lambda v: (str(v.path), v.line, v.violation_type)):
        rel = item.path.relative_to(ROOT)
        lines.append(f"{rel}:{item.line}: {item.violation_type}: {item.message}")
        lines.append(f"  fix: {item.suggestion}")
    if not lines:
        return "ExecutionContract linter: no violations found."
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail on violations.")
    parser.add_argument("--fix", action="store_true", help="Reserved for future safe autofixes.")
    args = parser.parse_args(argv)

    strict = args.strict or os.getenv("STRICT_EXECUTION_CONTRACT", "false").lower() in {"1", "true", "yes"}
    violations = []
    violations.extend(lint_routes())
    violations.extend(lint_memory_usage())
    violations.extend(lint_event_usage())
    violations.extend(lint_service_execution())

    print(render_report(violations))

    if args.fix:
        print("Auto-fix mode is not implemented yet; manual review required for all reported violations.")

    if violations and strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
