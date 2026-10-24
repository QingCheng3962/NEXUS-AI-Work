@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [NEXUS] 正在创建虚拟环境...
    py -3.13 -m venv .venv
    if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo [NEXUS] 未找到 Python，请先安装 Python 3.10+（推荐 3.13）并勾选 "Add to PATH"。
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -U pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

echo.
echo   NEXUS · AI 个人工作站
echo   浏览器将自动打开 http://127.0.0.1:8080
echo   按 Ctrl+C 停止服务
echo.
".venv\Scripts\python.exe" app.py %*
pause
