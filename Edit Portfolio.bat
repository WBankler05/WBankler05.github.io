@echo off
title Portfolio Editor
cd /d "%~dp0"
".venv\Scripts\python.exe" editor\server.py
if errorlevel 1 pause
