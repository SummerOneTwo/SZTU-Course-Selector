@echo off
chcp 65001 >nul

echo 正在检查环境...

where uv >nul 2>nul
if %errorlevel% equ 0 goto start_script

echo ==============================================================
echo ❌ 未检测到 uv 环境 (Python 现代包管理器)。
echo 运行此脚本需要 uv。您可以选择让此脚本自动为您下载安装。
echo ==============================================================
set /p install_uv="是否立即自动下载并安装 uv？(Y 按回车确定，其他键取消): "

if /i "%install_uv%"=="Y" goto install_uv_cmd
goto cancel_install

:install_uv_cmd
echo ⏳ 正在调用 PowerShell 自动下载并安装 uv...
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
if %errorlevel% neq 0 (
    echo ❌ uv 安装失败，请访问 https://docs.astral.sh/uv/ 手动安装。
    pause
    exit /b 1
)
echo ✅ uv 安装成功！
echo ⚠️ 请关闭当前窗口并重新双击 run.bat 运行脚本。
pause
exit /b 0

:cancel_install
echo 🛑 已取消安装。请手动安装 uv 后再运行此脚本。
pause
exit /b 1

:start_script
echo ✅ 环境检查通过，开始启动选课脚本...
echo.

uv sync
uv run sztu_course_selector.py

echo.
pause
