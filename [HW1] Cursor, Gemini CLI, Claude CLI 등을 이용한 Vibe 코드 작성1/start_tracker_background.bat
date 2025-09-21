@echo off
echo 앱 사용시간 추적 프로그램을 백그라운드에서 시작합니다...
cd /d "%~dp0"
start /B python scheduler.py
echo 프로그램이 백그라운드에서 실행 중입니다.
echo 종료하려면 작업 관리자에서 python.exe 프로세스를 종료하세요.
pause

