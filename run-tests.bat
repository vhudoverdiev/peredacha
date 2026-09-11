@echo off
setlocal

cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m unittest discover -s tests
) else (
    python -m unittest discover -s tests
)

