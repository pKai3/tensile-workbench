@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
rem Detection must not let the new Python install manager install before consent.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
if not "%~1"=="setup" if not "%~1"=="launch" if not "%~1"=="install-app" if not "%~1"=="desktop" exit /b 2
set "TW_BOOTSTRAP_ATTEMPTED="
set "TW_BOOTSTRAPPED="
set "TW_ENV_DIR=%LOCALAPPDATA%\TensileWorkbench\py314\venv"
if defined TENSILE_ENV_DIR set "TW_ENV_DIR=%TENSILE_ENV_DIR%"
set "TW_PYTHON_CHECK=import sys,struct,sysconfig,platform; sys.exit(not (sys.version_info[:2]==(3,14) and struct.calcsize('P')==8 and not sysconfig.get_config_var('Py_GIL_DISABLED') and platform.machine().lower() in ('amd64','x86_64')))"
:discover
set "PYTHON_BIN="
set "PYTHON_SELECTOR="
rem Only exit code zero is success. Python's install manager can return negative
rem HRESULT errors such as 0xA0000006, which "if not errorlevel 1" accepts.
for %%P in ("%TW_ENV_DIR%\Scripts\python.exe" "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" "%ProgramFiles%\Python314\python.exe") do (
    if exist "%%~P" (
        "%%~P" -c "%TW_PYTHON_CHECK%" >nul 2>&1 && (
            set "PYTHON_BIN=%%~P"
            goto ready
        )
    )
)
for %%P in ("py" "%SystemRoot%\py.exe" "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe") do (
    "%%~P" -3.14 -c "%TW_PYTHON_CHECK%" >nul 2>&1 && (
        set "PYTHON_BIN=%%~P"
        set "PYTHON_SELECTOR=-3.14"
        goto ready
    )
)
for /f "delims=" %%P in ('where python3.14 python 2^>nul') do (
    "%%~P" -c "%TW_PYTHON_CHECK%" >nul 2>&1 && (
        set "PYTHON_BIN=%%~P"
        goto ready
    )
)
if defined TW_BOOTSTRAP_ATTEMPTED goto missing
set "TW_BOOTSTRAP_ATTEMPTED=1"
call "%~dp0install_python_windows.bat" || goto failed
set "TW_BOOTSTRAPPED=1"
goto discover
:ready
if not defined TW_BOOTSTRAPPED goto run_action
if "%~1"=="setup" goto run_action
if "%~1"=="install-app" goto run_action
"%PYTHON_BIN%" %PYTHON_SELECTOR% "%~dp0..\workbench_environment.py" setup || goto failed
:run_action
"%PYTHON_BIN%" %PYTHON_SELECTOR% "%~dp0..\workbench_environment.py" "%~1"
set "RESULT=%ERRORLEVEL%"
goto finished
:missing
echo Python 3.14 was not found after installation. Rerun Install_Tensile_Workbench_App.bat, or see SETUP.md.
echo On a managed computer, ask IT if installation is blocked.
set "RESULT=1"
goto finished
:failed
set "RESULT=%ERRORLEVEL%"
:finished
if "%~1"=="desktop" if "%RESULT%"=="0" exit /b 0
echo.
if not "%RESULT%"=="0" echo Workbench stopped. See the message above and SETUP.md.
pause
exit /b %RESULT%
