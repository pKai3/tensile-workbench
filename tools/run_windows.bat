@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
if not "%~1"=="setup" if not "%~1"=="launch" exit /b 2
where py >nul 2>&1
if errorlevel 1 goto try_python
py -3.13 -c "import sys,struct,sysconfig; sys.exit(not (sys.version_info[:2]==(3,13) and struct.calcsize('P')==8 and not sysconfig.get_config_var('Py_GIL_DISABLED')))" >nul 2>&1
if errorlevel 1 goto try_python
py -3.13 "%~dp0..\workbench_environment.py" "%~1"
set "RESULT=%ERRORLEVEL%"
goto finished
:try_python
where python >nul 2>&1
if errorlevel 1 goto missing
python -c "import sys,struct,sysconfig; sys.exit(not (sys.version_info[:2]==(3,13) and struct.calcsize('P')==8 and not sysconfig.get_config_var('Py_GIL_DISABLED')))" >nul 2>&1
if errorlevel 1 goto missing
python "%~dp0..\workbench_environment.py" "%~1"
set "RESULT=%ERRORLEVEL%"
goto finished
:missing
echo.
echo Install standard Python 3.13 for Windows x86-64, including its launcher.
echo https://www.python.org/downloads/windows/
echo Do not choose embeddable or free-threaded Python. See SETUP.md.
echo On a managed computer, ask IT if installation is blocked.
set "RESULT=1"
:finished
echo.
if not "%RESULT%"=="0" echo Workbench stopped with an error. See the message above and SETUP.md.
pause
exit /b %RESULT%
