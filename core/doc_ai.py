"""用 DSH 为导入文档生成摘要。

文档分析是一次独立的只读任务，使用临时空工作区，不接触用户文件；
模型选择复用模型调度器，主模型余额不足时可切换备用模型。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from . import documents, model_router
from .dsh_agent import dsh_agent

Progress = Callable[[str], Awaitable[None] | None]


async def _notify(callback: Progress | None, text: str) -> None:
    if callback is None:
        return
    result = callback(text)
    if asyncio.iscoroutine(result):
        await result


async def summarize(doc: documents.DocumentText, progress: Progress | None = None) -> str:
    if dsh_agent.busy:
        raise documents.DocumentError("AI 正在执行其他任务，请稍后再导入文档。")
    decision = model_router.choose("总结文档并提取要点", mode="router")
    models = [decision.model] if decision.model else []
    if decision.fallback and decision.fallback != decision.model:
        models.append(decision.fallback)
    if not models:
        raise documents.DocumentError("尚未选择模型，请先在 AI 设置中检测模型。")

    prompt = documents.build_summary_prompt(doc)
    last_error = ""
    for model in models:
        await _notify(progress, f"正在用 {model} 提取摘要…")
        answer = ""
        error = ""
        with tempfile.TemporaryDirectory(prefix="anvil-doc-") as workdir:
            async for event in dsh_agent.stream(
                prompt,
                workspace=Path(workdir),
                permission="read-only",
                model=model,
            ):
                kind = event.get("type")
                if kind == "text":
                    answer += event.get("text", "")
                elif kind == "final":
                    value = event.get("text", "")
                    if isinstance(value, str) and value.strip():
                        answer = value
                elif kind == "error":
                    error = str(event.get("message") or "文档摘要失败")
                elif kind == "_exit" and event.get("returncode"):
                    error = event.get("stderr") or error or "文档摘要失败"
        if answer.strip():
            return answer.strip()
        last_error = error or "模型没有返回摘要。"
        if len(models) > 1 and model_router.is_balance_error(last_error):
            await _notify(progress, "主模型余额不足，正在切换备用模型…")
            continue
        break
    raise documents.DocumentError(f"AI 摘要失败：{last_error}")
