# modules/deepseek/security_deepseek.py
import os

class SecurityValidator:
    """
    Ensures file paths, extensions, and content are safe before processing.
    Prevents the ARM from operating on unauthorized or sensitive files.
    """

    SAFE_EXTENSIONS = {".py", ".json", ".txt", ".md", ".sql"}
    MAX_FILE_SIZE_MB = 5

    def validate_file(self, file_path: str):
        # Path checks
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Size check
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if size_mb > self.MAX_FILE_SIZE_MB:
            raise ValueError(f"File too large ({size_mb:.2f} MB)")

        # Extension check
        _, ext = os.path.splitext(file_path)
        if ext.lower() not in self.SAFE_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        # Sensitive keyword scan
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            for forbidden in ["SECRET_KEY", "API_KEY", "PASSWORD"]:
                if forbidden in content:
                    raise PermissionError(f"Sensitive token found in {file_path}")

        return True
