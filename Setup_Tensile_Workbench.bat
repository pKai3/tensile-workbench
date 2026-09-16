@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0tools\run_windows.bat" setup
exit /b %ERRORLEVEL%
