"""
ARM File Processor

Handles file reading, chunking, and session metadata creation.
Splits large files into token-safe chunks to stay within OpenAI context limits.
"""
import uuid
import time
from pathlib import Path
from datetime import datetime, timezone


class FileProcessor:
    """
    Reads files and prepares their content for ARM reasoning operations.

    Core responsibilities:
    - Read files with encoding fallback
    - Chunk content by line boundaries (preserves code structure)
    - Generate UUID session IDs for grouping related operations
    - Build structured session log dictionaries for DB persistence
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.max_chunk_tokens = config.get("max_chunk_tokens", 4000)
        # Rough approximation: 4 characters ≈ 1 token
        self.chars_per_chunk = self.max_chunk_tokens * 4

    # ── File reading ─────────────────────────────────────────────────────────

    def read_file(self, path: Path) -> str:
        """Read file content with UTF-8 encoding and replacement fallback."""
        return path.read_text(encoding="utf-8", errors="replace")

    # ── Chunking ─────────────────────────────────────────────────────────────

    def chunk_content(self, content: str) -> list:
        """
        Split file content into chunks that fit within the token limit.

        Splits on newline boundaries to preserve code structure — a line
        is never split across two chunks.

        Returns a list of string chunks. Single-chunk files return a
        one-element list.
        """
        if len(content) <= self.chars_per_chunk:
            return [content]

        chunks = []
        lines = content.split("\n")
        current_chunk = []
        current_size = 0

        for line in lines:
            line_size = len(line) + 1  # +1 for the newline character
            if current_size + line_size > self.chars_per_chunk and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_size = line_size
            else:
                current_chunk.append(line)
                current_size += line_size

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    # ── Session utilities ────────────────────────────────────────────────────

    def create_session_id(self) -> str:
        """Generate a UUID v4 session ID for grouping related ARM operations."""
        return str(uuid.uuid4())

    def create_session_log(
        self,
        session_id: str,
        file_path: str,
        operation: str,
        start_time: float,
        input_tokens: int,
        output_tokens: int,
        status: str,
        error: str = None,
    ) -> dict:
        """
        Build a structured session log entry for DB persistence.

        Includes Infinity Algorithm Execution Speed metric
        (tokens processed per second).
        """
        elapsed = time.time() - start_time
        total_tokens = input_tokens + output_tokens
        return {
            "session_id": session_id,
            "file_path": file_path,
            "operation": operation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "execution_seconds": round(elapsed, 3),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "status": status,
            "error": error,
            # Infinity Algorithm metric: Execution Speed (tokens/second)
            "execution_speed": round(
                total_tokens / max(elapsed, 0.001), 1
            ),
        }
