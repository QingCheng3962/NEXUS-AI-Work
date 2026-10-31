"""模型调度的纯函数测试。"""

from core import model_router


def _cfg(mode: str = "router") -> dict:
    return {
        "dsh": {
            "model": "direct-model",
            "router": {
                "mode": mode,
                "cheap_model": "fast-model",
                "strong_model": "pro-model",
                "fallback_model": "backup-model",
            },
        }
    }


def test_classify_code_task_as_strong() -> None:
    assert model_router.classify_task("帮我重构这个 Python 函数并修复报错") == "strong"
    assert model_router.classify_task("今天天气怎么样") == "cheap"


def test_router_selects_roles_and_fallback(monkeypatch) -> None:
    monkeypatch.setattr(model_router.settings, "load", lambda: _cfg())
    monkeypatch.setattr(model_router.model_catalog, "cached_models", lambda: [])

    chat = model_router.choose("帮我写一段介绍", mode="router")
    assert chat.role == "cheap"
    assert chat.model == "fast-model"
    assert chat.fallback == "backup-model"

    code = model_router.choose("修复 typescript 编译错误", mode="router")
    assert code.role == "strong"
    assert code.model == "pro-model"


def test_direct_mode_has_no_fallback(monkeypatch) -> None:
    monkeypatch.setattr(model_router.settings, "load", lambda: _cfg("direct"))
    decision = model_router.choose("写一个函数", mode="direct")
    assert decision.mode == "direct"
    assert decision.model == "direct-model"
    assert decision.fallback == ""


def test_balance_error_detection() -> None:
    assert model_router.is_balance_error("Error: Insufficient Balance")
    assert model_router.is_balance_error("账户余额不足（402）")
    assert not model_router.is_balance_error("permission denied")
