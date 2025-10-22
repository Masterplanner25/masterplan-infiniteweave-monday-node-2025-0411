# modules/deepseek/config_manager_deepseek.py
import json
import os
from datetime import datetime

class ConfigManager:
    """
    Loads, updates, and saves DeepSeek ARM runtime configuration.
    Self-tuning parameters can later be tied to Infinity Algorithm metrics.
    """

    def __init__(self, config_path: str = "deepseek_config.json"):
        self.config_path = config_path
        if not os.path.exists(config_path):
            self.save({"temperature": 0.3, "max_chunk_tokens": 2000, "retry_limit": 3})

    # --------------------------
    def load(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: dict):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # --------------------------
    def update(self, key: str, value):
        cfg = self.load()
        cfg[key] = value
        cfg["last_updated"] = datetime.utcnow().isoformat()
        self.save(cfg)
        return cfg
