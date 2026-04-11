from __future__ import annotations

import argparse
from pathlib import Path

from AINDY.db.database import SessionLocal
from AINDY.memory.memory_ingest_service import MemoryIngestService


DEFAULT_PATHS = [
    Path("memorytraces"),
    Path("memoryevents"),
]


def main():
    parser = argparse.ArgumentParser(description="Ingest symbolic memory files into Memory Bridge.")
    parser.add_argument("--user-id", required=True, help="User ID to own ingested memory nodes")
    parser.add_argument("--paths", nargs="*", help="Paths to ingest (files or directories)")
    parser.add_argument("--dry-run", action="store_true", help="Parse without writing to DB")

    args = parser.parse_args()

    paths = [Path(p) for p in (args.paths or DEFAULT_PATHS)]

    db = SessionLocal()
    try:
        service = MemoryIngestService(db=db, user_id=args.user_id)
        results = service.ingest_paths(paths, dry_run=args.dry_run)
    finally:
        db.close()

    total = len(results)
    ingested = sum(1 for r in results if r.status == "ingested")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")

    print(f"Ingested: {ingested} / {total}")
    if skipped:
        print(f"Skipped: {skipped}")
    if failed:
        print(f"Failed: {failed}")

    for result in results:
        print(f"- {result.status}: {result.path} trace={result.trace_id} node={result.node_id}")


if __name__ == "__main__":
    main()
