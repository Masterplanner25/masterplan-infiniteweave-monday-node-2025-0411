from __future__ import annotations

from .types import RecallRequest


class QueryExpander:
    def expand(self, request: RecallRequest) -> str:
        query = request.query or ""

        if request.task_type == "analysis":
            return f"{query} code analysis insights patterns"
        if request.task_type == "strategy":
            return f"{query} decisions strategy outcomes"
        if request.task_type == "codegen":
            return f"{query} code generation refactor snippets"
        if request.task_type == "nodus_execution":
            return f"{query} execution outcomes decisions"

        return query
