@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0tools\run_windows.bat" install-app
exit /b %ERRORLEVEL%
