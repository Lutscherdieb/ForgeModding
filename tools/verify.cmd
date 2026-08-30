@echo off
rem Thin wrapper so the verify gate is runnable next to Forge's own .cmd launchers.
rem Writes verify-report.txt (the evidence artifact) and echoes it.
pushd "%~dp0.."
python tools\verify.py > verify-report.txt
set RC=%ERRORLEVEL%
type verify-report.txt
popd
exit /b %RC%
