@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
where py >nul 2>&1
if errorlevel 1 goto use_python
py -3.13 "%~dp0launch_workbench_windows.py"
goto finished
:use_python
python "%~dp0launch_workbench_windows.py"
:finished
if errorlevel 1 echo Workbench stopped with an error. See the message above.
pause
