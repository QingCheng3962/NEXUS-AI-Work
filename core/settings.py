"""配置管理：data/config.json 的读写、深度合并与点号取值。"""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any

from . import runtime

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = runtime.support_dir()
CONFIG_FILE = DATA_DIR / "config.json"
WORKSPACE_DIR = runtime.default_workspace()

DEFAULTS: dict[str, Any] = {
    "app": {
        "host": "127.0.0.1",
        "port": 8080,
        "theme": "dark",
        "user_name": "HI",
        "sidebar_collapsed": False,
    },
    "llm": {
        "active": "deepseek",
        "profiles": [
            {
                "id": "deepseek",
                "name": "DeepSeek 官方",
                "provider": "DeepSeek 官方",
                "base_url": "https://api.deepseek.com",
                "api_key": "",
                "model": "deepseek-chat",
                "temperature": 0.7,
                "reasoning_effort": "normal",
            }
        ],
        "system_prompt": (
            "你是「Anvil」——运行在用户个人工作站里的 AI 助理。"
            "回答要准确、简洁、有结构；涉及代码时优先给出可直接运行的方案。"
        ),
    },
    "dsh": {
        "workspace": str(WORKSPACE_DIR),
        "model": "",
        "models": [],
        "models_source": "",
        "models_checked_at": 0,
        "reasoning_effort": "",
        "permission": "read-only",
        "base_url": "",
        "api_key": "",
        "home": "",
        "use_stored_credentials": True,
        "package": "@deepseek-ai/dsh@0.2.1-rc.2",
        "task_timeout": 300,
        "command_timeout": 30,
        "snapshot_enabled": True,
        "snapshot_max_mb": 256,
        "router": {
            "mode": "direct",
            "cheap_model": "",
            "strong_model": "",
            "fallback_model": "",
        },
    },
}

_lock = threading.RLock()
_cache: dict[str, Any] | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    """把 override 合并进 base 的副本，dict 递归合并。"""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict[str, Any]:
    """读取配置；文件不存在或损坏时回退到默认配置。"""
    global _cache
    with _lock:
        if _cache is not None:
            return copy.deepcopy(_cache)

        ensure_data_dir()
        cfg = copy.deepcopy(DEFAULTS)
        raw: dict[str, Any] = {}
        migrated = False
        if CONFIG_FILE.exists():
            try:
                loaded = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw = loaded
                    cfg = _deep_merge(cfg, raw)
            except (json.JSONDecodeError, OSError):
                pass

        # 旧版单模型配置迁移到多模型 profiles
        raw_llm = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
        if raw_llm and "profiles" not in raw_llm:
            legacy = {
                "id": "default",
                "name": raw_llm.get("provider") or "默认模型",
                "provider": raw_llm.get("provider") or "DeepSeek 官方",
                "base_url": raw_llm.get("base_url") or "https://api.deepseek.com",
                "api_key": raw_llm.get("api_key") or "",
                "model": raw_llm.get("model") or "deepseek-chat",
                "temperature": raw_llm.get("temperature", 0.7),
                "reasoning_effort": raw_llm.get("reasoning_effort") or "normal",
            }
            cfg["llm"]["profiles"] = [legacy]
            cfg["llm"]["active"] = "default"
            for key in ("provider", "base_url", "api_key", "model", "temperature"):
                cfg["llm"].pop(key, None)
            migrated = True

        profiles = cfg["llm"].get("profiles") or []
        if profiles and not any(p.get("id") == cfg["llm"].get("active") for p in profiles):
            cfg["llm"]["active"] = profiles[0].get("id", "deepseek")

        # 品牌迁移：旧版本的 NEXUS 默认工作区/提示词改为 Anvil（保留旧值用于迁移）。
        old_prompt = str(cfg["llm"].get("system_prompt") or "")
        if "NEXUS" in old_prompt:
            cfg["llm"]["system_prompt"] = old_prompt.replace("NEXUS", "Anvil")
            migrated = True
        old_workspace = str(cfg["dsh"].get("workspace") or "").strip()
        if old_workspace:
            old_path = Path(old_workspace).expanduser()
            if old_path.name.upper() in ("NEXUS-WORKSPACE", "ANVIL-WORKSPACE"):
                new_path = old_path.with_name("Anvil-Workspace")
                try:
                    if old_path.exists() and not new_path.exists():
                        old_path.rename(new_path)
                    cfg["dsh"]["workspace"] = str(new_path)
                except OSError:
                    cfg["dsh"]["workspace"] = old_workspace
                migrated = True

        # 首次运行时落盘，方便用户直接编辑
        if not CONFIG_FILE.exists() or migrated:
            _write(cfg)
        _cache = cfg
        return copy.deepcopy(cfg)


def _write(cfg: dict[str, Any]) -> None:
    ensure_data_dir()
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_FILE)


def save(cfg: dict[str, Any]) -> None:
    global _cache
    with _lock:
        _cache = _deep_merge(DEFAULTS, cfg)
        _write(_cache)


def update(partial: dict[str, Any]) -> dict[str, Any]:
    """局部更新配置并立即写盘。"""
    with _lock:
        cfg = load()
        cfg = _deep_merge(cfg, partial)
        save(cfg)
        return cfg


def get(path: str, default: Any = None) -> Any:
    """支持点号路径，例如 get('llm.model')。"""
    node: Any = load()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_value(path: str, value: Any) -> None:
    """按点号路径写入单个配置值。"""
    with _lock:
        cfg = load()
        node = cfg
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        save(cfg)


def reset() -> dict[str, Any]:
    save(copy.deepcopy(DEFAULTS))
    return load()
