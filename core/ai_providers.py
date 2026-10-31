"""多 AI 服务商节点：SQLite 存储，并在切换节点时同步 DSH 运行时配置。"""

from __future__ import annotations

from . import db, settings


def list_providers() -> list[dict]:
    return db.list_ai_providers()


def active_provider_id() -> str:
    return str(settings.get("dsh.active_provider_id", "") or "").strip()


def active_provider() -> dict | None:
    provider_id = active_provider_id()
    if not provider_id.isdigit():
        return None
    return db.get_ai_provider(int(provider_id))


def _runtime_values(provider: dict) -> dict[str, str]:
    return {
        "active_provider_id": str(provider["id"]),
        "base_url": str(provider.get("base_url") or "").strip(),
        "api_key": str(provider.get("api_key") or "").strip(),
        "model": str(provider.get("model") or "").strip(),
    }


def activate(provider_id: int | str) -> bool:
    """把某个节点设为当前节点，并同步基础连接信息。"""
    try:
        numeric_id = int(provider_id)
    except (TypeError, ValueError):
        return False
    provider = db.get_ai_provider(numeric_id)
    if not provider:
        return False
    settings.update({"dsh": _runtime_values(provider)})
    return True


def apply_selection(value: str) -> bool:
    """处理主聊天下拉框的值：provider:<id> 或 model:<model-id>。"""
    choice = str(value or "").strip()
    if choice.startswith("provider:"):
        return activate(choice.split(":", 1)[1])
    if choice.startswith("model:"):
        model = choice.split(":", 1)[1].strip()
        if not model:
            return False
        # 保留当前 Base URL / Key；只切换模型，方便继续使用自动检测的模型。
        settings.update(
            {"dsh": {"active_provider_id": "", "model": model}}
        )
        return True
    return False


def select_options() -> dict[str, str]:
    options: dict[str, str] = {}
    for provider in list_providers():
        model = str(provider.get("model") or "").strip() or "未填写模型"
        options[f"provider:{provider['id']}"] = (
            f"{provider['name']} · {model}"
        )
    return options


def selected_value(current_model: str, detected_options: dict[str, str]) -> str:
    """计算主聊天下拉框当前值。"""
    provider_id = active_provider_id()
    if provider_id:
        key = f"provider:{provider_id}"
        provider = active_provider()
        if provider and key in select_options():
            return key
    if current_model:
        return f"model:{current_model}"
    return next(iter(detected_options), "")


def reconcile_active_provider() -> None:
    """AI 设置被手动修改后，避免主聊天仍显示过期的服务商节点。"""
    provider = active_provider()
    if provider is None:
        if active_provider_id():
            settings.set_value("dsh.active_provider_id", "")
        return
    runtime = settings.get("dsh", {}) or {}
    expected = _runtime_values(provider)
    if any(
        str(runtime.get(key) or "").strip() != expected[key]
        for key in ("base_url", "api_key", "model")
    ):
        settings.set_value("dsh.active_provider_id", "")
