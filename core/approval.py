"""DSH 授权桥：把 headless 进程中的审批请求转发到桌面界面。

DSH 的 `ask` 策略在找不到 answerer 时会 fail-closed。headless 模式没有
交互式客户端，因此这里注入一个很小的 Cordis 插件，让它通过本机 HTTP
回连 Anvil，由用户在 AI 工作窗口里决定是否允许一次敏感操作。
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Request

from . import settings

PLUGIN_SOURCE = r"""
export function apply(ctx) {
  const url = process.env.ANVIL_APPROVAL_URL;
  const token = process.env.ANVIL_APPROVAL_TOKEN;
  if (!url || !token || process.env.ANVIL_APPROVAL_ENABLED !== '1') return;

  ctx.on('approval/request', async (request, next) => {
    const controller = new AbortController();
    if (request.signal) {
      request.signal.addEventListener('abort', () => controller.abort(), { once: true });
    }
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-anvil-approval-token': token,
        },
        body: JSON.stringify({
          toolName: request.toolName || '',
          reason: request.reason || '',
          callId: request.callId || '',
        }),
        signal: controller.signal,
      });
      if (!response.ok) return 'unavailable';
      const data = await response.json();
      const allowed = ['allowed-once', 'rejected', 'cancelled', 'unavailable'];
      return allowed.includes(data.outcome) ? data.outcome : 'unavailable';
    } catch (error) {
      if (controller.signal.aborted) return 'cancelled';
      return 'unavailable';
    }
  });
}
"""


class ApprovalBroker:
    def __init__(self) -> None:
        self.token = secrets.token_hex(20)
        self.handler: Callable[[dict[str, Any]], Awaitable[bool]] | None = None
        self.port: int | None = None
        self._plugin: Path | None = None

    def plugin_path(self) -> Path:
        if self._plugin is None:
            path = settings.DATA_DIR / "anvil_dsh_approval.mjs"
            path.write_text(PLUGIN_SOURCE, encoding="utf-8")
            self._plugin = path
        return self._plugin

    def url(self) -> str:
        port = self.port or int(settings.get("app.port", 8080) or 8080)
        return f"http://127.0.0.1:{port}/api/dsh/approval"

    async def decide(self, payload: dict[str, Any], remote: str) -> str:
        if remote not in ("127.0.0.1", "::1", "localhost"):
            return "unavailable"
        handler = self.handler
        if handler is None:
            return "unavailable"
        try:
            allowed = await asyncio.wait_for(handler(payload), timeout=300)
        except asyncio.TimeoutError:
            return "rejected"
        except Exception:  # noqa: BLE001 - 回连失败必须 fail-closed
            return "unavailable"
        return "allowed-once" if allowed else "rejected"


broker = ApprovalBroker()


def install_route(fastapi_app) -> None:
    """在 NiceGUI 的 FastAPI 实例上注册本机授权回连端点。"""

    @fastapi_app.post("/api/dsh/approval")
    async def _dsh_approval(request: Request):
        if request.headers.get("x-anvil-approval-token", "") != broker.token:
            return {"outcome": "unavailable"}
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            payload = {}
        remote = request.client.host if request.client else ""
        return {"outcome": await broker.decide(payload, remote)}
