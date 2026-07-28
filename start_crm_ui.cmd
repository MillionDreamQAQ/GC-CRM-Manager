@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m crm_support_ui.launcher
if errorlevel 1 (
  echo.
  echo 启动失败。请确认已安装 requirements.txt 中的依赖，并已完成 az login。
  pause
)
