@echo off
rem ===========================================================================
rem  run.cmd - run project scripts with the venv python.
rem
rem  IMPORTANT: this file is intentionally ASCII-only.
rem  cmd.exe reads .bat files using the OEM codepage (GBK on zh-CN Windows),
rem  NOT UTF-8. Chinese comments here get mis-decoded into bytes that cmd
rem  tries to execute as commands, which produces an endless error loop.
rem  Any Chinese explanation belongs in the README, not in this file.
rem
rem  Why this file exists:
rem    PowerShell blocks .ps1 scripts by default, so
rem    .venv\Scripts\Activate.ps1 fails and the venv is NOT activated.
rem    Then `python` resolves to the system Python, which has no packages.
rem    .cmd files are NOT affected by the execution policy.
rem
rem  Usage:
rem    run.cmd                              (environment diagnosis)
rem    run.cmd 01_check_env.py
rem    run.cmd selftest.py
rem    run.cmd make_demo_session.py
rem    run.cmd 02_extract_pose.py --video testdata\people-walking.mp4 --session walk
rem    run.cmd 03_events_and_metrics.py --session walk
rem    run.cmd 04_report.py --session walk
rem ===========================================================================

setlocal
set PYTHONUTF8=1

set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo.
  echo [ERROR] venv not found:
  echo         %PY%
  echo.
  echo         Run this first to create it:
  echo           powershell -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  echo.
  exit /b 1
)

if "%~1"=="" (
  rem No arguments: print an environment diagnosis.
  "%PY%" "%~dp0env_hint.py"
  exit /b %ERRORLEVEL%
)

"%PY%" %*
exit /b %ERRORLEVEL%
