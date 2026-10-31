"""模型调度：简易直连与按任务自动选模。

调度模式使用当前 API 自动检测到的模型 ID，不内置任何硬编码模型：
- 闲聊/总结等轻任务走 ``cheap_model``；
- 代码、调试、文件修改等重任务走 ``strong_model``；
- 主力模型返回余额不足时，自动重试 ``fallback_model``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import model_catalog, settings

CODE_PATTERN = re.compile(
    r"(?i)(?:"
    r"```|代码|编程|脚本|函数|方法|类|接口|数据库|算法|重构|调试|报错|异常|"
    r"bug|fix|debug|refactor|test|单元测试|编译|构建|部署|依赖|npm|pip|git|"
    r"python|javascript|typescript|react|vue|sql|html|css|powershell|cmd|shell|"
    r"文件|目录|路径|修改|删除|创建|读取|写入|实现|开发|修复|优化|性能|"
    r"docker|kubernetes|api|http|json|yaml|正则|"
    r"\.(?:py|js|ts|tsx|jsx|json|ya?ml|sql|html|css|md|ps1|bat|sh|java|cpp|c|go|rs)"
    r")"
)
BALANCE_PATTERN = re.compile(
    r"(?i)(?:insufficient[ _-]?(?:balance|quota|credit)|"
    r"insufficient_quota|quota[ _-]?exceeded|payment[ _-]?required|"
    r"余额不足|额度不足|账户余额|欠费|402)"
)

_STRONG_HINTS = ("pro", "max", "reasoner", "large", "ultra", "thinking", "v4")
_CHEAP_HINTS = ("flash", "mini", "lite", "fast", "air", "turbo", "small", "chat")


@dataclass(frozen=True)
class RouteDecision:
    mode: str
    role: str
    model: str
    fallback: str
    reason: str

    def display(self) -> str:
        if self.mode == "router":
            role = "强模型" if self.role == "strong" else "轻量模型"
            text = f"{role} · {self.model or '未配置'}"
            if self.fallback:
                text += f" · 备用 {self.fallback}"
            return text
        return f"直连 · {self.model or '未配置'}"


def classify_task(task: str) -> str:
    text = (task or "").strip()
    if not text:
        return "cheap"
    # 代码块、命令行和较长的工程类描述视为重任务。
    if CODE_PATTERN.search(text):
        return "strong"
    if len(text) > 900:
        return "strong"
    return "cheap"


def _id(item: dict) -> str:
    return str(item.get("id") or "").strip()


def _label(item: dict) -> str:
    return f"{item.get('id', '')} {item.get('name', '')}".lower()


def _first_matching(models: list[dict], hints: tuple[str, ...], exclude: set[str]) -> str:
    for hint in hints:
        for item in models:
            model_id = _id(item)
            if model_id and model_id not in exclude and hint in _label(item):
                return model_id
    return ""


def _pick_strong(models: list[dict]) -> str:
    found = _first_matching(models, _STRONG_HINTS, set())
    if found:
        return found
    # 没有明显标记时，优先上下文窗口更大的模型。
    ordered = sorted(models, key=lambda item: int(item.get("context_window") or 0), reverse=True)
    return _id(ordered[0]) if ordered else ""


def _pick_cheap(models: list[dict], exclude: set[str]) -> str:
    found = _first_matching(models, _CHEAP_HINTS, exclude)
    if found:
        return found
    for item in models:
        model_id = _id(item)
        if model_id and model_id not in exclude:
            return model_id
    return _id(models[0]) if models else ""


def suggest_router_models(models: list[dict]) -> dict[str, str]:
    """根据当前 API 返回的模型推荐三个角色，不写配置。"""
    if not models:
        return {}
    strong = _pick_strong(models)
    cheap = _pick_cheap(models, {strong})
    used = {strong, cheap}
    fallback = next((_id(item) for item in models if _id(item) not in used), "")
    return {
        "strong_model": strong,
        "cheap_model": cheap,
        "fallback_model": fallback,
    }


def bootstrap_router_models(models: list[dict] | None = None) -> dict[str, str]:
    """首次检测到模型时，用检测结果填充空白的调度角色。

    只填充空白字段，不覆盖用户手工选择；所有值都来自当前 API。
    """
    items = models if models is not None else model_catalog.cached_models()
    suggestions = suggest_router_models(items)
    if not suggestions:
        return {}
    router = settings.get("dsh.router", {}) or {}
    update: dict[str, str] = {}
    for key in ("strong_model", "cheap_model", "fallback_model"):
        if not str(router.get(key) or "").strip() and suggestions.get(key):
            update[key] = suggestions[key]
    if update:
        settings.update({"dsh": {"router": update}})
    return update


def choose(task: str, mode: str | None = None) -> RouteDecision:
    cfg = settings.load().get("dsh", {})
    router = cfg.get("router") if isinstance(cfg.get("router"), dict) else {}
    active_mode = str(mode or router.get("mode") or "direct").strip().lower()
    if active_mode not in ("direct", "router"):
        active_mode = "direct"

    direct_model = str(cfg.get("model") or "").strip()
    models = model_catalog.cached_models()
    if not direct_model and models:
        direct_model = _id(models[0])

    if active_mode == "direct":
        return RouteDecision(
            mode="direct",
            role="direct",
            model=direct_model,
            fallback="",
            reason="简易模式：直接使用当前模型",
        )

    role = classify_task(task)
    cheap = str(router.get("cheap_model") or "").strip()
    strong = str(router.get("strong_model") or "").strip()
    fallback = str(router.get("fallback_model") or "").strip()
    model = strong if role == "strong" else cheap
    if not model:
        model = direct_model
    if fallback == model:
        fallback = ""
    reason = "检测到代码/工程任务，使用强模型" if role == "strong" else "轻量任务，使用低成本模型"
    if not model:
        reason = "尚未配置模型，请先在 AI 设置中检测模型"
    return RouteDecision(
        mode="router",
        role=role,
        model=model,
        fallback=fallback,
        reason=reason,
    )


def is_balance_error(text: str) -> bool:
    return bool(BALANCE_PATTERN.search(text or ""))


def mode_label(mode: str) -> str:
    return "调度模式" if str(mode).lower() == "router" else "简易模式"
