@echo off
cd /d C:\Users\antho\Downloads\nebula
python tools\_capture_alien_toasts.py > tools\_toast_demo_alien\capture.log 2>&1
echo EXIT=%ERRORLEVEL% >> tools\_toast_demo_alien\capture.log
