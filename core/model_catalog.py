"""模型目录：从当前 DSH API 自动发现可用模型。

DSH 的 API Key 通道本身只内置两个模型别名，不会主动查询远端模型列表。
这里直接请求兼容的 ``/models`` 接口，把当前 Base URL + Key 真正可用的
模型展示到界面中；检测失败时保留已有缓存，不伪造默认模型。
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

try:  # PyYAML 用于读取 DSH 保存的登录凭据；缺失时仍支持 API Key。
    import yaml
except ImportError:  # pragma: no cover - 依赖里已声明 PyYAML
    yaml = None  # type: ignore[assignment]

from . import llm, settings

DEFAULT_DSH_BASE = "https://api.deepseek.com/anthropic"
CREDENTIALS_FILE = Path.home() / ".dsh" / ".credentials.yaml"
_TIMEOUT = 8.0


class ModelCatalogError(RuntimeError):
    """可展示给用户的模型检测错误。"""


# --------------------------------------------------------------------------- #
# 凭据与地址
# --------------------------------------------------------------------------- #
def _stored_credentials() -> dict[str, str]:
    """读取 DSH 凭据文件中的 API Key 与账户登录令牌。

    文件由 DSH 维护；这里只读，不写回，也不把密钥放进日志。账户令牌使用
    DSH 自己的 ``x-dsh-auth-token`` 请求头，不能当作普通 API Key 使用。
    """
    try:
        text = CREDENTIALS_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"api_key": "", "account_token": ""}

    api_key_value = ""
    account_token = ""
    if yaml is not None:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            data = None
        if isinstance(data, dict):
            refs = data.get("refs") if isinstance(data.get("refs"), dict) else {}
            api_key_value = str(refs.get("DEEPSEEK_API_KEY") or "")
            records = data.get("records") if isinstance(data.get("records"), dict) else {}
            account = records.get("deepseek-account-platform/default")
            if isinstance(account, dict):
                payload = account.get("payload")
                if isinstance(payload, dict):
                    account_token = str(payload.get("token") or "")

    if not api_key_value:
        # 极简回退：只解析 refs 区块中的 API Key。
        in_refs = False
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if line.startswith("refs:"):
                in_refs = True
                continue
            if in_refs:
                if not line.startswith((" ", "\t")):
                    break
                key, sep, value = line.strip().partition(":")
                if sep and key == "DEEPSEEK_API_KEY":
                    api_key_value = value
                    break
    return {
        "api_key": api_key_value.strip().strip("\"'"),
        "account_token": account_token.strip().strip("\"'"),
    }


def api_key() -> str:
    """按 DSH 启动时的优先级返回可用的 API Key。"""
    cfg = settings.load().get("dsh", {})
    candidates = [
        cfg.get("api_key") or "",
        os.environ.get("DEEPSEEK_API_KEY") or "",
        llm.active_profile().get("api_key") or "",
    ]
    for value in candidates:
        if str(value).strip():
            return str(value).strip()
    if cfg.get("use_stored_credentials", True):
        return _stored_credentials()["api_key"]
    return ""


def account_token() -> str:
    """DSH 桌面版登录后保存的账户令牌（不是 API Key）。"""
    cfg = settings.load().get("dsh", {})
    if not cfg.get("use_stored_credentials", True):
        return ""
    return _stored_credentials()["account_token"]


def base_url() -> str:
    return (settings.get("dsh.base_url", "") or "").strip()


def source_id(base: str | None = None, key: str | None = None) -> str:
    """给 Base URL + 凭据生成不可逆指纹，用来判断缓存是否过期。"""
    secret = (key if key is not None else api_key()).strip()
    if not secret:
        secret = account_token()
    value = f"{(base if base is not None else base_url()).strip()}\n{secret}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def has_credentials() -> bool:
    return bool(api_key() or account_token())


# --------------------------------------------------------------------------- #
# 地址推导
# --------------------------------------------------------------------------- #
def _endpoint_candidates(base: str | None = None) -> list[str]:
    raw = (base if base is not None else base_url()).strip().rstrip("/")
    if not raw:
        raw = DEFAULT_DSH_BASE
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ModelCatalogError("API Base URL 格式不正确，请填写完整的 http(s) 地址。")

    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    candidates: list[str] = []
    if path.endswith("/v1"):
        candidates = [f"{raw}/models", f"{origin}/models"]
    elif "/anthropic" in path:
        candidates = [f"{origin}/models", f"{raw}/models"]
    elif path:
        candidates = [f"{raw}/models", f"{origin}/models", f"{origin}/v1/models"]
    else:
        candidates = [f"{raw}/models", f"{raw}/v1/models"]

    unique: list[str] = []
    for item in candidates:
        if item not in unique:
            unique.append(item)
    return unique


# --------------------------------------------------------------------------- #
# 响应解析
# --------------------------------------------------------------------------- #
def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_models(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("data")
            or payload.get("models")
            or payload.get("items")
            or payload.get("result")
            or []
        )
    else:
        items = []
    if not isinstance(items, list):
        return []

    result: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            model_id, name = item.strip(), item.strip()
            context_window = max_tokens = 0
        elif isinstance(item, dict):
            model_id = str(
                item.get("id")
                or item.get("model")
                or item.get("name")
                or item.get("display_name")
                or ""
            ).strip()
            name = str(
                item.get("name")
                or item.get("display_name")
                or item.get("displayName")
                or model_id
            ).strip()
            context_window = _as_int(
                item.get("context_window")
                or item.get("contextWindow")
                or item.get("max_context_length")
            )
            max_tokens = _as_int(
                item.get("max_output_tokens")
                or item.get("maxTokens")
                or item.get("max_output")
            )
        else:
            continue
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        result.append(
            {
                "id": model_id,
                "name": name or model_id,
                "context_window": context_window,
                "max_output_tokens": max_tokens,
            }
        )
    return result


def _request_models(endpoint: str, key: str, token: str = "") -> list[dict]:
    variants: list[dict[str, str]] = []
    base_headers = {"Accept": "application/json", "User-Agent": "NEXUS/1.0"}
    if key:
        variants.append({**base_headers, "Authorization": f"Bearer {key}"})
        variants.append({**base_headers, "x-api-key": key})
    if token:
        variants.append({**base_headers, "x-dsh-auth-token": token})
    if not variants:
        raise ModelCatalogError("还没有可用凭据，无法检测模型。")

    last_auth_error = ""
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            for headers in variants:
                response = client.get(endpoint, headers=headers)
                if response.status_code in (401, 403):
                    last_auth_error = "API Key 或 DSH 登录凭据无效，没有查询模型列表的权限。"
                    continue
                if response.status_code == 404:
                    raise ModelCatalogError(
                        "当前 API 没有 /models 接口，请手动填写模型 ID。"
                    )
                if response.status_code >= 400:
                    raise ModelCatalogError(
                        f"模型接口返回 HTTP {response.status_code}，请检查 Base URL 与凭据。"
                    )
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ModelCatalogError(
                        "模型接口返回的不是 JSON，请检查 Base URL。"
                    ) from exc
                models = parse_models(payload)
                if not models:
                    raise ModelCatalogError("模型接口没有返回可用模型。")
                return models
    except httpx.HTTPError as exc:
        raise ModelCatalogError(f"无法连接模型接口：{exc}") from exc

    raise ModelCatalogError(last_auth_error or "没有查询到可用模型。")


def detect_models(
    base: str | None = None,
    key: str | None = None,
) -> list[dict]:
    """调用当前 API 的 ``/models``，返回规范化后的模型列表。"""
    if key is not None:
        effective_key = key.strip()
        effective_token = ""
    else:
        effective_key = api_key()
        effective_token = account_token()
    if not effective_key and not effective_token:
        raise ModelCatalogError(
            "还没有可用凭据。请填写 API Key，或启用 DSH 已保存的凭据后再检测。"
        )

    errors: list[str] = []
    for endpoint in _endpoint_candidates(base):
        try:
            return _request_models(endpoint, effective_key, effective_token)
        except ModelCatalogError as exc:
            errors.append(str(exc))
            # 连接失败时继续尝试备用地址没有意义。
            if "无法连接" in str(exc):
                break
    raise ModelCatalogError(errors[-1] if errors else "没有找到可用的模型接口。")


# --------------------------------------------------------------------------- #
# 本地缓存
# --------------------------------------------------------------------------- #
def cached_models() -> list[dict]:
    items = settings.get("dsh.models", []) or []
    models: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        models.append(
            {
                "id": model_id,
                "name": str(item.get("name") or model_id),
                "context_window": _as_int(item.get("context_window")),
                "max_output_tokens": _as_int(item.get("max_output_tokens")),
            }
        )
    return models


def save_catalog(models: list[dict], base: str | None = None, key: str | None = None) -> None:
    settings.update(
        {
            "dsh": {
                "models": models,
                "models_source": source_id(base, key),
                "models_checked_at": int(time.time()),
            }
        }
    )


def clear_catalog() -> None:
    settings.update(
        {"dsh": {"models": [], "models_source": "", "models_checked_at": 0}}
    )


def cache_is_current() -> bool:
    stored = settings.get("dsh.models_source", "")
    return bool(stored) and stored == source_id()


def display_name(model: dict) -> str:
    return str(model.get("name") or model.get("id") or "").strip()


def select_options(models: list[dict] | None = None) -> dict[str, str]:
    """返回 NiceGUI ``ui.select`` 使用的 model id -> label 映射。"""
    options: dict[str, str] = {}
    for model in models if models is not None else cached_models():
        model_id = str(model.get("id") or "").strip()
        if not model_id:
            continue
        label = display_name(model) or model_id
        if label == model_id:
            label = model_id
        options[model_id] = label
    return options
