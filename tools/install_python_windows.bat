@echo off
setlocal EnableExtensions DisableDelayedExpansion
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" goto unsupported
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" goto unsupported
if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" if /i not "%PROCESSOR_ARCHITEW6432%"=="AMD64" goto unsupported
if not exist "%~dp0python_installers.conf" exit /b 1
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0python_installers.conf") do set "%%A=%%B"
echo.
echo Tensile Workbench needs standard 64-bit Python 3.14.
echo Setup can download and open the official Python installer, then continue.
echo Keep Tcl/Tk and the Python launcher selected. Choose all-users installation
echo in the installer if wanted; Windows handles any administrator approval.
choice /c YN /n /m "Download and install Python 3.14 now? [Y/N] "
if errorlevel 2 exit /b 1
if errorlevel 1 goto install
exit /b 1
:install
rem Inline PowerShell needs no script-execution-policy changes. Paths are data.
powershell.exe -NoProfile -Command ^
 "$ErrorActionPreference='Stop'; $result=0; $directory=$null;" ^
 "try { [Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12;" ^
 "$directory=Join-Path ([IO.Path]::GetTempPath()) ('tensile-python-'+[Guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Path $directory | Out-Null; $installer=Join-Path $directory 'python.exe';" ^
 "Write-Host ('Downloading Python '+$env:TW_PYTHON_INSTALL_VERSION+' from python.org...'); Invoke-WebRequest -UseBasicParsing -Uri $env:TW_PYTHON_WINDOWS_URL -OutFile $installer -TimeoutSec 300;" ^
 "if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $env:TW_PYTHON_WINDOWS_SHA256) { throw 'Installer checksum did not match. The installer was not opened.' };" ^
 "if ((Get-AuthenticodeSignature -LiteralPath $installer).Status -ne 'Valid') { throw 'Windows could not verify the installer signature. Ask IT for help.' };" ^
 "Write-Host 'Complete the Python installer and close its window. Workbench setup will then continue.'; $installation=Start-Process -FilePath $installer -ArgumentList 'Include_launcher=1','Include_tcltk=1' -Wait -PassThru;" ^
 "if ($installation.ExitCode -notin @(0,3010)) { throw ('Python installation was cancelled or failed (code '+$installation.ExitCode+'). Rerun setup to retry.') };" ^
 "if ($installation.ExitCode -eq 3010) { Write-Host 'Python requested a Windows restart. Restart if the next step cannot find Python.' }" ^
 "} catch { [Console]::Error.WriteLine($_.Exception.Message); $result=1 } finally { if ($directory) { Remove-Item -LiteralPath $directory -Recurse -Force -ErrorAction SilentlyContinue } }; exit $result"
exit /b %ERRORLEVEL%
:unsupported
echo This Workbench installer supports Windows x86-64. See SETUP.md.
exit /b 1
