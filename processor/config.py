"""Configuration helpers for the processor CLI."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "audio": {
        "sample_rate": 16000,
        "frame_ms": 40,
        "silence_ms": 900,
        "min_utterance_ms": 120,
        "auto_threshold": True,
        "calibration_ms": 1200,
        "start_threshold": 0.015,
        "stop_threshold": 0.010,
    },
    "agent": {
        "name": "codex",
        "workspace": ".",
        "open_permissions": True,
        "dry_run": False,
        "model": None,
        "reasoning_effort": None,
        "timeout_seconds": 600,
        "idle_timeout_seconds": 120,
    },
    "prompt": {
        "context": "",
    },
    "logging": {
        "path": None,
    },
}


def load_config(path: str | Path | None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    if path is None:
        return config

    with Path(path).expanduser().open("r", encoding="utf-8") as file:
        loaded = json.load(file)
    _deep_update(config, loaded)
    return config


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
