"""配置加载：YAML 文件 + 环境变量。"""
from __future__ import annotations

import os
from typing import Any, Dict

import yaml

DEFAULTS: Dict[str, Any] = {
    "general": {"name": "OpenSight", "overlay_notice": True},
    "recognition": {
        "backend": "insightface",
        "model": "buffalo_sc",
        "threshold": 0.6,
        "detect_every_n_frames": 5,
        "min_face_size": 40,
        "providers": "",
    },
    "pets": {
        "enabled": True, "backend": "pet-onnx", "model_size": "small",
        "model_path": "", "threshold": 0.35,
    },
    "cameras": [],
    "events": {
        "retention_days": 30,
        "save_snapshot": True,
        "cooldown_seconds": 30,
        # 旧配置兼容字段（新配置请使用 notifications）
        "webhook_url": "",
        "mqtt": {"enabled": False},
    },
    "notifications": {
        "telegram": {"enabled": False, "bot_token": "", "chat_id": "", "include_photo": True},
        "custom_bot": {"enabled": False, "provider": "wecom", "webhook_url": ""},
        "local_bridge": {
            "enabled": False, "preset": "openclaw", "url": "",
            "user_id": "", "group_id": "",
        },
        "webhook": {"enabled": False, "url": ""},
        "mqtt": {"enabled": False, "host": "", "port": 1883, "topic": "opensight/events"},
    },
    "notice_text": "AI 辅助识别区域 · 结果仅供人工复核",
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    def __init__(self) -> None:
        path = os.getenv("OPENSIGHT_CONFIG", "/app/config.yaml")
        self.raw: Dict[str, Any] = {}
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.raw = yaml.safe_load(f) or {}
        self.cfg = _deep_merge(DEFAULTS, self.raw)
        self.data_dir = os.getenv("OPENSIGHT_DATA_DIR", "/data")
        self.go2rtc_api = os.getenv("OPENSIGHT_GO2RTC_API", "http://127.0.0.1:1984")
        self.log_level = os.getenv("OPENSIGHT_LOG_LEVEL", "INFO")
        os.makedirs(self.data_dir, exist_ok=True)

    def __getitem__(self, key: str) -> Any:
        return self.cfg[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.cfg.get(key, default)

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "opensight.db")

    @property
    def snapshot_dir(self) -> str:
        p = os.path.join(self.data_dir, "snapshots")
        os.makedirs(p, exist_ok=True)
        return p

    @property
    def gallery_dir(self) -> str:
        p = os.path.join(self.data_dir, "gallery")
        os.makedirs(p, exist_ok=True)
        return p


settings = Settings()
