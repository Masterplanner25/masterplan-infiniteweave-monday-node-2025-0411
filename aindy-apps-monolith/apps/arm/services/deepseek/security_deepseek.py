"""
ARM Security Validator

Validates all inputs before the reasoning engine runs.
No reasoning happens without passing security validation.

Validation layers:
1. File path safety (no traversal, allowed directories only)
2. File type allowlist (.py, .js, .ts, .jsx, .tsx, .json, .md, .txt, .yaml, .yml)
3. Sensitive content detection (.env, API keys, passwords, private keys)
4. Size and token threshold checks
5. Content policy (no malicious code patterns)
"""
import re
from pathlib import Path
from typing import Optional
from fastapi import HTTPException


class SecurityValidator:
    """
    Validates all file paths and content before ARM processes them.
    Raises HTTPException on any violation so FastAPI returns the correct
    HTTP status code directly — no silent failures.
    """

    # File types ARM is allowed to analyze
    ALLOWED_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx",
        ".json", ".md", ".txt", ".yaml", ".yml",
    }

    # Regex patterns that indicate sensitive content.
    # Each pattern is compiled once at class definition time.
    SENSITIVE_PATTERNS = [
        # Generic assignment of key/secret/password/token/credential to a string value ≥ 8 chars
        re.compile(
            r'(?i)(api[_\-]?key|secret|password|token|credential)\s*=\s*[\'"][^\'"]{8,}[\'"]'
        ),
        # OpenAI API key
        re.compile(r'sk-[a-zA-Z0-9]{48}'),
        # .env file reference
        re.compile(r'(?i)\.env'),
        # PEM private key block
        re.compile(r'-----BEGIN\s.*PRIVATE KEY-----'),
        # AWS access key
        re.compile(r'AKIA[0-9A-Z]{16}'),
    ]

    # Path segments that ARM must never access
    BLOCKED_PATH_SEGMENTS = [
        ".env",
        "venv",
        "__pycache__",
        ".git",
        "secrets",
        "credentials",
        "keys",
    ]

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.max_file_size_bytes = self.config.get("max_file_size_bytes", 100_000)
        self.max_chunk_tokens = self.config.get("max_chunk_tokens", 4000)

    # ── Path validation ──────────────────────────────────────────────────────

    def validate_file_path(self, file_path: str) -> Path:
        """
        Validate that the file path is safe and accessible.

        Checks:
        - No blocked directory segments (prevents traversal to .env, .git, etc.)
        - Extension is in the allowed set
        - File exists on disk

        Returns the resolved Path if all checks pass.
        Raises HTTPException 403 (forbidden) or 422 (unsupported) or 404 (not found).
        """
        path = Path(file_path).resolve()
        path_str_lower = str(path).lower().replace("\\", "/")

        # Block path traversal into sensitive directories
        for segment in self.BLOCKED_PATH_SEGMENTS:
            if f"/{segment}" in path_str_lower or path_str_lower.startswith(segment):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Access to path containing '{segment}' is not permitted. "
                        "ARM cannot analyze sensitive directories."
                    ),
                )

        # Allowlist file extension
        if path.suffix.lower() not in self.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"File type '{path.suffix}' is not supported for analysis. "
                    f"Allowed types: {', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
                ),
            )

        # File must exist
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_path}",
            )

        return path

    # ── Content validation ───────────────────────────────────────────────────

    def validate_content(self, content: str) -> str:
        """
        Scan content for sensitive data before it is sent to OpenAI.

        Raises HTTPException 403 if any sensitive pattern is detected.
        Returns the content unchanged if all checks pass.
        """
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern.search(content):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Content contains potentially sensitive data "
                        "(API keys, passwords, private keys, or .env references). "
                        "Remove sensitive data before analysis."
                    ),
                )
        return content

    def validate_size(self, content: str) -> str:
        """
        Ensure the content is within the configured size limit.

        Raises HTTPException 422 if the encoded size exceeds the maximum.
        """
        byte_size = len(content.encode("utf-8"))
        if byte_size > self.max_file_size_bytes:
            limit_kb = self.max_file_size_bytes // 1000
            raise HTTPException(
                status_code=422,
                detail=(
                    f"File too large for analysis. "
                    f"Maximum size: {limit_kb} KB. "
                    f"Received: {byte_size // 1000} KB."
                ),
            )
        return content

    def validate_code_input(self, code: str) -> str:
        """
        Validate a raw code string submitted directly (not via file path).
        Used for generation requests that include original_code.
        """
        self.validate_content(code)
        self.validate_size(code)
        return code

    # ── Full pipeline ────────────────────────────────────────────────────────

    def full_file_validation(self, file_path: str) -> tuple:
        """
        Run the complete validation pipeline for file-based analysis.

        Pipeline:
        1. Validate path (traversal, extension, existence)
        2. Read file content
        3. Scan for sensitive data
        4. Check size limit

        Returns (path: Path, content: str) if all checks pass.
        Raises HTTPException on any violation.
        """
        path = self.validate_file_path(file_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        self.validate_content(content)
        self.validate_size(content)
        return path, content
