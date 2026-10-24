"""OpenAI 兼容的大模型调用与多模型配置。

每个模型档案（profile）独立保存 provider、Base URL、Key、模型 ID 和推理强度。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator, Iterable

import httpx

from . import settings

MODEL_PRESETS = [
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-v4-flash",
    "deepseek-v4",
    "gpt-4o-mini",
    "gpt-4o",
    "qwen-plus",
]

EFFORT_LEVELS = ["low", "normal", "high", "max"]
EFFORT_API = {"low": "low", "normal": "medium", "high": "high", "max": "high"}
EFFORT_LABELS = {"low": "Low", "normal": "Normal", "high": "High", "max": "Max"}

_TIMEOUT = httpx.Timeout(connect=20.0, read=300.0, write=60.0, pool=20.0)


class LLMError(RuntimeError):
    """模型调用相关的可展示错误。"""


# --------------------------------------------------------------------------- #
# 模型档案
# --------------------------------------------------------------------------- #
def profiles() -> list[dict]:
    items = settings.get("llm.profiles", []) or []
    return [item for item in items if isinstance(item, dict) and item.get("id")]


def active_profile() -> dict:
    items = profiles()
    active_id = settings.get("llm.active", "")
    for item in items:
        if item.get("id") == active_id:
            return item
    return items[0] if items else _fallback_profile()


def get_profile(profile_id: str) -> dict:
    for item in profiles():
        if item.get("id") == profile_id:
            return item
    return active_profile()


def _fallback_profile() -> dict:
    return {
        "id": "default",
        "name": "默认模型",
        "provider": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com",
        "api_key": "",
        "model": "deepseek-chat",
        "temperature": 0.7,
        "reasoning_effort": "normal",
    }


def _save_profiles(items: list[dict], active_id: str | None = None) -> None:
    partial: dict = {"llm": {"profiles": items}}
    if active_id:
        partial["llm"]["active"] = active_id
    settings.update(partial)


def set_active(profile_id: str) -> None:
    if any(item["id"] == profile_id for item in profiles()):
        settings.set_value("llm.active", profile_id)


def add_profile(name: str = "新模型") -> dict:
    items = profiles()
    base = active_profile()
    profile = {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "provider": base.get("provider", "DeepSeek 官方"),
        "base_url": base.get("base_url", "https://api.deepseek.com"),
        "api_key": base.get("api_key", ""),
        "model": base.get("model", "deepseek-chat"),
        "temperature": base.get("temperature", 0.7),
        "reasoning_effort": "normal",
    }
    items.append(profile)
    _save_profiles(items, profile["id"])
    return profile


def update_profile(profile: dict) -> None:
    items = profiles()
    for index, item in enumerate(items):
        if item.get("id") == profile.get("id"):
            items[index] = profile
            break
    else:
        items.append(profile)
    _save_profiles(items, profile.get("id"))


def delete_profile(profile_id: str) -> bool:
    items = profiles()
    if len(items) <= 1:
        return False
    remaining = [item for item in items if item.get("id") != profile_id]
    if len(remaining) == len(items):
        return False
    active_id = settings.get("llm.active", "")
    if active_id == profile_id:
        active_id = remaining[0]["id"]
    _save_profiles(remaining, active_id)
    return True


def profile_label(profile: dict) -> str:
    return f"{profile.get('name', '模型')} · {profile.get('model', '')}"


# --------------------------------------------------------------------------- #
# 调用
# --------------------------------------------------------------------------- #
def _endpoint(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise LLMError("未配置 API 地址，请打开 AI 设置填写。")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _headers(profile: dict) -> dict[str, str]:
    key = (profile.get("api_key") or "").strip()
    if not key:
        raise LLMError("这个模型还没有配置 API Key，请打开 AI 设置填写。")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def build_messages(history: Iterable[dict], system_prompt: str | None = None) -> list[dict]:
    prompt = system_prompt if system_prompt is not None else settings.get("llm.system_prompt", "")
    messages: list[dict] = []
    if prompt:
        messages.append({"role": "system", "content": prompt})
    for item in history:
        role = item.get("role")
        content = item.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    return messages


def _payload(profile: dict, messages: list[dict], stream: bool, temperature: float | None) -> dict:
    payload = {
        "model": profile.get("model") or "deepseek-chat",
        "messages": messages,
        "temperature": float(
            temperature if temperature is not None else profile.get("temperature", 0.7)
        ),
        "stream": stream,
    }
    effort = profile.get("reasoning_effort") or "normal"
    if effort != "normal" and effort in EFFORT_API:
        # Codex 风格的强度档位；服务端不支持时会返回错误，切回 normal 即可。
        payload["reasoning_effort"] = EFFORT_API[effort]
    return payload


def _friendly_error(status: int, body: str) -> str:
    detail = body
    try:
        payload = json.loads(body)
        detail = payload.get("error", {}).get("message") or payload.get("message") or body
    except Exception:
        pass
    detail = str(detail).strip()[:400]
    if status == 401:
        return f"API Key 无效或无权限（401）。{detail}"
    if status == 402:
        return f"账户余额不足（402）。{detail}"
    if status == 429:
        return f"请求过于频繁或额度受限（429）。{detail}"
    if status >= 500:
        return f"模型服务暂时不可用（{status}）。{detail}"
    return f"请求失败（HTTP {status}）。{detail}"


async def stream_chat(
    history: Iterable[dict],
    profile_id: str | None = None,
    temperature: float | None = None,
) -> AsyncIterator[str]:
    """流式产出 assistant 文本片段。"""
    profile = get_profile(profile_id) if profile_id else active_profile()
    payload = _payload(profile, build_messages(history), stream=True, temperature=temperature)
    url = _endpoint(profile.get("base_url", ""))
    headers = _headers(profile)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise LLMError(_friendly_error(response.status_code, body))

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    chunk = delta.get("content")
                    if chunk:
                        yield chunk
    except httpx.ConnectError as exc:
        raise LLMError(f"无法连接到模型服务：{exc}") from exc
    except httpx.ReadTimeout as exc:
        raise LLMError("模型响应超时，请稍后重试或换一个模型。") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"网络请求异常：{exc}") from exc


async def test_connection(profile_id: str | None = None) -> tuple[bool, str]:
    """发一个最小请求验证配置。返回 (成功, 提示)。"""
    profile = get_profile(profile_id) if profile_id else active_profile()
    payload = {
        "model": profile.get("model") or "deepseek-chat",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(
                _endpoint(profile.get("base_url", "")),
                json=payload,
                headers=_headers(profile),
            )
        elapsed = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            return False, _friendly_error(response.status_code, response.text)
        return True, f"连接成功，延迟 {elapsed} ms"
    except LLMError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 - 统一展示
        return False, f"连接失败：{exc}"
