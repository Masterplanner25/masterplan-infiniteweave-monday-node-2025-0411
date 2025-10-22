# modules/deepseek/file_processor_deepseek.py
import os
from datetime import datetime

class FileProcessor:
    """
    Handles file reading/writing and lightweight auditing for DeepSeek runs.
    """

    LOG_DIR = "logs/deepseek/"

    def __init__(self):
        os.makedirs(self.LOG_DIR, exist_ok=True)

    def save_log(self, message: str):
        timestamp = datetime.utcnow().isoformat()
        log_path = os.path.join(self.LOG_DIR, "arm_activity.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    def get_recent_logs(self, limit: int = 50):
        log_path = os.path.join(self.LOG_DIR, "arm_activity.log")
        if not os.path.exists(log_path):
            return []
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return lines[-limit:]
