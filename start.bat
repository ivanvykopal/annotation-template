@echo off
rem Starts the Label Studio annotation stack:
rem   1) snapshot CORS server on 127.0.0.1:8765  (article HTML embeds)
rem   2) Label Studio itself on 127.0.0.1:8080   (blocks this window)
rem
rem Close both by closing the two windows / Ctrl-C.

setlocal
cd /d "%~dp0"

start "LS snapshots :8765" venv\Scripts\python.exe cors_server.py

echo Open http://localhost:8080 and log in with your Label Studio account
venv\Scripts\label-studio.exe
