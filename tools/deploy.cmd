@echo off
rem Thin wrapper so deploy is runnable next to Forge's own .cmd launchers.
rem Idempotent: safe to re-run after a Forge reinstall removes the junction.
pushd "%~dp0.."
python tools\deploy.py %*
set RC=%ERRORLEVEL%
popd
exit /b %RC%
