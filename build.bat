@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [NEXUS] 正在创建构建环境...
    py -3.13 -m venv .venv
    if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo [NEXUS] 未找到 Python，请先安装 Python 3.10+（推荐 3.13）。
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -U pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-build.txt
)

echo.
echo   NEXUS · 构建 Windows EXE
echo   产物：dist\NEXUS\NEXUS.exe
echo.
".venv\Scripts\python.exe" scripts\prepare_vendor.py
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" scripts\build_exe.py %*
if errorlevel 1 goto :fail

echo.
echo 构建完成，正在打开输出目录...
explorer dist\NEXUS
pause
exit /b 0

:fail
echo.
echo 构建失败，请查看上方错误信息。
pause
exit /b 1
