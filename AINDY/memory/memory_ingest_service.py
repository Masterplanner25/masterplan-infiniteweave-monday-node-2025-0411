from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
from AINDY.db.dao.memory_trace_dao import MemoryTraceDAO

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    path: str
    trace_id: Optional[str]
    node_id: Optional[str]
    status: str
    message: Optional[str] = None


class MemoryIngestService:
    def __init__(self, db, user_id: str):
        self.db = db
        self.user_id = user_id
        self.node_dao = MemoryNodeDAO(db)
        self.trace_dao = MemoryTraceDAO(db)

    def ingest_paths(self, paths: Iterable[Path], dry_run: bool = False) -> list[IngestResult]:
        results: list[IngestResult] = []
        for path in paths:
            try:
                if path.is_dir():
                    for file_path in sorted(path.iterdir()):
                        if file_path.is_file():
                            results.append(self._ingest_file(file_path, dry_run=dry_run))
                elif path.is_file():
                    results.append(self._ingest_file(path, dry_run=dry_run))
            except Exception as exc:
                logger.warning("[MemoryIngest] failed: %s", exc)
                results.append(IngestResult(path=str(path), trace_id=None, node_id=None, status="failed", message=str(exc)))
        return results

    def _ingest_file(self, path: Path, dry_run: bool) -> IngestResult:
        content = path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return IngestResult(path=str(path), trace_id=None, node_id=None, status="skipped", message="empty")

        origin_kind = path.parent.name
        title = self._extract_title(content) or path.stem
        description = self._extract_description(content)
        date_label = self._extract_date(content)

        extra = {
            "origin_path": str(path),
            "origin_file": path.name,
            "origin_kind": origin_kind,
            "origin_title": title,
            "origin_date": date_label,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }

        tags = self._build_tags(origin_kind, path.stem)

        if dry_run:
            return IngestResult(path=str(path), trace_id="dry-run", node_id="dry-run", status="dry_run")

        trace = self.trace_dao.create_trace(
            user_id=self.user_id,
            title=title,
            description=description,
            source=origin_kind,
            extra=extra,
        )

        node = self.node_dao.save(
            content=content,
            source=f"symbolic_ingest:{origin_kind}",
            tags=tags,
            user_id=self.user_id,
            node_type="insight",
            extra=extra,
        )

        trace_id = trace.get("id") if trace else None
        node_id = node.get("id") if node else None

        if trace_id and node_id:
            try:
                self.trace_dao.append_node(
                    trace_id=trace_id,
                    node_id=node_id,
                    user_id=self.user_id,
                )
            except Exception as exc:
                logger.warning("[MemoryIngest] append failed: %s", exc)

        return IngestResult(path=str(path), trace_id=trace_id, node_id=node_id, status="ingested")

    def _build_tags(self, origin_kind: str, stem: str) -> list[str]:
        tags = {"symbolic", origin_kind}
        tags.update(self._slugify(stem).split("-"))
        return [t for t in tags if t]

    def _extract_title(self, content: str) -> Optional[str]:
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("#").strip()
        match = re.search(r"^\*\*Title:\*\*\s*(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_description(self, content: str) -> Optional[str]:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return None
        if lines[0].startswith("#") and len(lines) > 1:
            return lines[1]
        return lines[0]

    def _extract_date(self, content: str) -> Optional[str]:
        patterns = [
            r"^\*\*Date:\*\*\s*(.+)$",
            r"^Date:\s*(.+)$",
            r"^\*\*Temporal Anchor:\*\*\s*(.+)$",
            r"^Temporal Anchor:\s*(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    def _slugify(self, value: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return value
