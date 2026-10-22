@echo off
cd /d "%~dp0.."
python -X utf8 -m eval.win_run %* > eval\runs\_win_run.console.log 2>&1
