from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

_script_lock = threading.Lock()
_NODUS_SCRIPT_REGISTRY: dict[str, dict[str, Any]] = {}
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "nodus"


def get_script_record(name: str) -> dict[str, Any] | None:
    with _script_lock:
        record = _NODUS_SCRIPT_REGISTRY.get(name)
        return dict(record) if record else None


def load_script_source(name: str) -> str | None:
    record = get_script_record(name)
    if record:
        return str(record["content"])

    disk_path = _SCRIPTS_DIR / f"{name}.nodus"
    if not disk_path.exists():
        return None

    try:
        content = disk_path.read_text(encoding="utf-8")
    except OSError:
        return None

    with _script_lock:
        existing = _NODUS_SCRIPT_REGISTRY.get(name)
        if existing:
            return str(existing["content"])
        _NODUS_SCRIPT_REGISTRY[name] = {
            "name": name,
            "content": content,
            "description": None,
            "size_bytes": len(content.encode("utf-8")),
            "uploaded_at": None,
            "uploaded_by": None,
            "restored_from_disk": True,
        }
    return content


def store_script(
    *,
    name: str,
    content: str,
    description: str | None,
    uploaded_at: str | None,
    uploaded_by: str | None,
) -> dict[str, Any]:
    meta = {
        "name": name,
        "content": content,
        "description": description,
        "size_bytes": len(content.encode("utf-8")),
        "uploaded_at": uploaded_at,
        "uploaded_by": uploaded_by,
    }
    with _script_lock:
        _NODUS_SCRIPT_REGISTRY[name] = meta
    return dict(meta)


def script_exists(name: str) -> bool:
    with _script_lock:
        return name in _NODUS_SCRIPT_REGISTRY


def list_script_metadata(*, include_disk: bool = True) -> list[dict[str, Any]]:
    if include_disk and _SCRIPTS_DIR.exists():
        for script_path in _SCRIPTS_DIR.glob("*.nodus"):
            try:
                load_script_source(script_path.stem)
            except Exception:
                continue

    with _script_lock:
        return [
            {
                "name": meta["name"],
                "description": meta.get("description"),
                "size_bytes": meta.get("size_bytes", 0),
                "uploaded_at": meta.get("uploaded_at"),
                "uploaded_by": meta.get("uploaded_by"),
            }
            for meta in reversed(list(_NODUS_SCRIPT_REGISTRY.values()))
        ]
