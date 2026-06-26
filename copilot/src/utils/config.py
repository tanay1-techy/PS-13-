"""
Centralized configuration loader.
Reads config.yaml once and provides typed access to all settings.
All paths are resolved relative to the project root.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # copilot/
_CONFIG: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    """Load config.yaml from project root."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    config_path = _PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        _CONFIG = yaml.safe_load(f)
    return _CONFIG


def get(key: str, default: Any = None) -> Any:
    """
    Dot-notation access into the config tree.
    Example: get("simulator.num_devices") -> 20
    """
    cfg = _load_config()
    keys = key.split(".")
    val = cfg
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


def get_path(key: str) -> Path:
    """
    Get a path value from config, resolved relative to PROJECT_ROOT.
    Example: get_path("paths.sqlite_db") -> /abs/path/copilot/data/store/telemetry.db
    """
    raw = get(key)
    if raw is None:
        raise KeyError(f"Path config key not found: {key}")
    return _PROJECT_ROOT / raw


def project_root() -> Path:
    return _PROJECT_ROOT


def ensure_dirs():
    """Create all necessary directories defined in config."""
    dirs_to_create = [
        get_path("paths.models_dir"),
        get_path("paths.models_dir") / "llm",
        get_path("paths.models_dir") / "embeddings",
        get_path("paths.data_dir"),
        get_path("paths.runbooks_dir"),
        get_path("paths.store_dir"),
    ]
    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)


# ── Convenience typed getters ──

def simulator_cfg() -> Dict[str, Any]:
    return get("simulator", {})


def analytics_cfg() -> Dict[str, Any]:
    return get("analytics", {})


def rag_cfg() -> Dict[str, Any]:
    return get("rag", {})


def llm_cfg() -> Dict[str, Any]:
    return get("llm", {})


def mls_cfg() -> Dict[str, Any]:
    return get("mls", {})


def dashboard_cfg() -> Dict[str, Any]:
    return get("dashboard", {})
