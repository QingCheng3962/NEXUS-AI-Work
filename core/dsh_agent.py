"""把 DSH（DeepSeek Harness）作为本地 Agent 嵌入工作站。

不走 Web UI、不打开浏览器：直接驱动 `dsh --profile headless --json`，
从 stdin 提交任务，逐行解析 JSON 事件（思考 / 文本 / 工具调用 / 工具结果），
并通过 `--session-id` 延续同一段会话。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, AsyncIterator

from . import approval, llm, runtime, security, settings

_READ_LIMIT = 4 * 1024 * 1024


def _find_npx() -> str | None:
    return shutil.which("npx") or shutil.which("npx.cmd")


def _find_node() -> str | None:
    return shutil.which("node") or shutil.which("node.exe")


class DSHAgent:
    def __init__(self) -> None:
        self.proc: asyncio.subprocess.Process | None = None
        self.busy = False
        self.cancelled = False
        self.session_id = ""
        self.last_error = ""

    # ------------------------------------------------------------------ #
    # 环境
    # ------------------------------------------------------------------ #
    def node_path(self) -> Path | str | None:
        return runtime.bundled_node() or _find_node()

    def available(self) -> bool:
        if runtime.dsh_is_bundled():
            return True
        return bool(_find_npx() and _find_node())

    def node_version(self) -> str:
        node = self.node_path()
        if not node:
            return ""
        try:
            out = subprocess.run(
                [str(node), "--version"],
                capture_output=True,
                text=True,
                timeout=security.command_timeout_seconds(),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return out.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def dsh_version(self) -> str:
        if runtime.bundled_dsh_bin():
            package_json = runtime.bundled_dsh_bin().parent.parent / "package.json"
            try:
                return json.loads(package_json.read_text(encoding="utf-8")).get("version", "")
            except (OSError, ValueError):
                return "内置"
        return settings.get("dsh.package", "@deepseek-ai/dsh")

    def has_stored_credentials(self) -> bool:
        path = Path.home() / ".dsh" / ".credentials.yaml"
        try:
            return path.exists() and path.stat().st_size > 10
        except OSError:
            return False

    def check_environment(self) -> dict[str, Any]:
        return {
            "node": self.node_version() or "未找到",
            "dsh": self.dsh_version() or "未找到",
            "bundled": runtime.dsh_is_bundled(),
            "credentials": self.has_stored_credentials(),
            "ok": self.available(),
        }

    # ------------------------------------------------------------------ #
    # 启动参数
    # ------------------------------------------------------------------ #
    def _base(self) -> tuple[list[str], bool]:
        node = runtime.bundled_node()
        bin_js = runtime.bundled_dsh_bin()
        if node and bin_js:
            return [str(node), str(bin_js)], True
        npx = _find_npx()
        if not npx:
            raise FileNotFoundError("未找到 Node.js / npx，且安装包不包含内置 DSH 运行时。")
        package = settings.get("dsh.package", "@deepseek-ai/dsh")
        return [npx, "-y", package], False

    def _patch_file(self, model: str | None = None) -> Path | None:
        cfg = settings.load().get("dsh", {})
        lines: list[str] = []
        model = str(model or cfg.get("model") or "").strip()
        if model:
            lines += [
                "- id: agent-default-model",
                "  config:",
                "    provider: deepseek-official",
                f"    model: {json.dumps(model, ensure_ascii=False)}",
            ]
            effort = (cfg.get("reasoning_effort") or "").strip()
            if effort in ("off", "low", "high", "max"):
                lines.append(f"    reasoningEffort: {json.dumps(effort)}")
        if cfg.get("use_stored_credentials"):
            lines += [
                "- id: credentials",
                "  disabled: false",
                "- id: authorization",
                "  disabled: false",
                "- id: deepseek-account",
                "  disabled: false",
            ]
        plugin = approval.broker.plugin_path()
        lines += [
            "- insert:",
            "    - id: anvil-approval",
            f"      name: {json.dumps(plugin.as_uri())}",
            "      config: {}",
        ]
        path = settings.DATA_DIR / "dsh-headless.patch.yml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _env(self, permission: str | None = None) -> dict[str, str]:
        cfg = settings.load()
        env = os.environ.copy()

        key = (cfg["dsh"].get("api_key") or "").strip() or (
            llm.active_profile().get("api_key") or ""
        ).strip()
        if key:
            env["DEEPSEEK_API_KEY"] = key

        # DSH 使用 Anthropic Messages 兼容端点；留空时交给 DSH 使用其官方
        # 默认地址，不能复用 Anvil 普通对话的 OpenAI 兼容 Base URL。
        base_url = (cfg["dsh"].get("base_url") or "").strip()
        if base_url:
            env["DEEPSEEK_BASE_URL"] = base_url.rstrip("/")

        home = (cfg["dsh"].get("home") or "").strip()
        if home:
            env["DSH_HOME"] = str(Path(home).expanduser())

        mode = security.permission_mode(
            permission or (cfg["dsh"].get("permission") or "read-only")
        )
        env["DSH_PERMISSION_MODE"] = mode
        env["ANVIL_APPROVAL_URL"] = approval.broker.url()
        env["ANVIL_APPROVAL_TOKEN"] = approval.broker.token
        env["ANVIL_APPROVAL_ENABLED"] = "1" if mode == "workspace-write" else "0"
        env["NO_COLOR"] = "1"
        return env

    def workspace(self) -> Path:
        return security.workspace_root(settings.get("dsh.workspace") or settings.WORKSPACE_DIR)

    def _command(self, session_id: str | None = None, model: str | None = None) -> list[str]:
        base, bundled = self._base()
        argv = [*base]
        patch = self._patch_file(model)
        if patch:
            argv += ["--patch", str(patch)]
        argv += ["--profile", "headless", "--json"]
        if session_id:
            argv += ["--session-id", session_id]
        if os.name == "nt" and not bundled:
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            argv = [comspec, "/d", "/s", "/c", f'"{subprocess.list2cmdline(argv)}"']
        return argv

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #
    async def stream(
        self,
        task: str,
        session_id: str | None = None,
        workspace: Path | None = None,
        permission: str = "read-only",
        model: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """运行一轮任务；逐条产出 DSH JSON 事件，末尾产出 `_exit`。

        ``model`` 用于模型调度模式：每一轮可以指定不同的模型 ID。权限和
        工作区在这里再次校验，避免绕过界面直接调用核心层。
        """
        task = (task or "").strip()
        if not task:
            yield {"type": "error", "message": "任务内容不能为空"}
            return
        if self.busy:
            yield {"type": "error", "message": "已有 DSH 任务正在执行，请先停止。"}
            return

        try:
            workdir = security.ensure_workspace(workspace or self.workspace())
            mode = security.permission_mode(permission)
        except security.SecurityError as exc:
            yield {"type": "error", "message": f"安全校验失败：{exc}"}
            yield {"type": "_exit", "returncode": -1, "stderr": str(exc), "cancelled": False}
            return

        self.busy = True
        self.cancelled = False
        self.last_error = ""
        stderr_lines: list[str] = []
        timed_out = False

        try:
            argv = self._command(session_id, model)
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(workdir),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env(mode),
                limit=_READ_LIMIT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.proc = proc

            async def read_stderr() -> None:
                if not proc.stderr:
                    return
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", "replace").rstrip()
                    if text:
                        stderr_lines.append(text)
                        if len(stderr_lines) > 200:
                            del stderr_lines[:100]

            err_task = asyncio.create_task(read_stderr())

            try:
                assert proc.stdin is not None
                proc.stdin.write((task + "\n").encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()

                assert proc.stdout is not None
                loop = asyncio.get_running_loop()
                deadline = loop.time() + security.task_timeout_seconds()
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        timed_out = True
                        break
                    try:
                        line = await asyncio.wait_for(
                            proc.stdout.readline(), timeout=remaining
                        )
                    except asyncio.TimeoutError:
                        timed_out = True
                        break
                    if not line:
                        break
                    text = line.decode("utf-8", "replace").strip()
                    if not text:
                        continue
                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue

                    if event.get("type") == "tool_call":
                        raw_input = event.get("input")
                        parsed_input = raw_input
                        if isinstance(raw_input, str):
                            try:
                                parsed_input = json.loads(raw_input)
                            except json.JSONDecodeError:
                                parsed_input = raw_input
                        try:
                            security.inspect_tool_call(
                                str(event.get("tool") or ""),
                                parsed_input,
                                workdir,
                                mode,
                            )
                        except security.SecurityError as exc:
                            self.last_error = str(exc)
                            yield {
                                "type": "error",
                                "message": f"安全拦截：{exc}",
                            }
                            await asyncio.to_thread(self._kill_process, proc)
                            break

                    if event.get("type") == "session" and event.get("sessionId"):
                        self.session_id = str(event["sessionId"])
                    yield event

                if timed_out:
                    self.last_error = f"任务超过 {int(security.task_timeout_seconds())} 秒未完成，已强制终止。"
                    await asyncio.to_thread(self._kill_process, proc)
                    yield {"type": "error", "message": self.last_error}
            finally:
                try:
                    returncode = await asyncio.wait_for(proc.wait(), timeout=10)
                except asyncio.TimeoutError:
                    await asyncio.to_thread(self._kill_process, proc)
                    try:
                        returncode = await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        returncode = -1
                await asyncio.gather(err_task, return_exceptions=True)
                stderr = "\n".join(stderr_lines[-60:])
                if returncode != 0 and stderr and not self.last_error:
                    self.last_error = stderr
                yield {
                    "type": "_exit",
                    "returncode": returncode,
                    "stderr": stderr,
                    "cancelled": self.cancelled,
                    "timed_out": timed_out,
                }
        except FileNotFoundError as exc:
            self.last_error = str(exc)
            yield {"type": "error", "message": str(exc)}
            yield {"type": "_exit", "returncode": -1, "stderr": str(exc), "cancelled": False}
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            yield {"type": "error", "message": f"启动 DSH 失败：{exc}"}
            yield {"type": "_exit", "returncode": -1, "stderr": str(exc), "cancelled": False}
        finally:
            self.proc = None
            self.busy = False

    @staticmethod
    def _kill_process(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=15,
                )
            else:
                proc.terminate()
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass

    def cancel(self) -> None:
        self.cancelled = True
        proc = self.proc
        if not proc or proc.returncode is not None:
            return
        self._kill_process(proc)


dsh_agent = DSHAgent()
