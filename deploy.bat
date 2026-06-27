@echo off
chcp 65001 >nul
echo =============================================
echo   CampWatch 서버 배포
echo =============================================
echo.

set KEY=C:\Users\han\Documents\Claude\Projects\camp\ssh-key-2026-06-25.key
set HOST=ubuntu@140.245.43.57
set REMOTE_DIR=/home/ubuntu/campwatch

echo [1/4] 서버에 디렉토리 생성 중...
ssh -i "%KEY%" -o StrictHostKeyChecking=no %HOST% "mkdir -p %REMOTE_DIR%/templates %REMOTE_DIR%/logs"

echo [2/4] 파일 업로드 중...
scp -i "%KEY%" -o StrictHostKeyChecking=no ^
  campwatch\app.py ^
  campwatch\crawler.py ^
  campwatch\models.py ^
  campwatch\requirements.txt ^
  campwatch\run.sh ^
  %HOST%:%REMOTE_DIR%/

scp -i "%KEY%" -o StrictHostKeyChecking=no ^
  campwatch\templates\base.html ^
  campwatch\templates\login.html ^
  campwatch\templates\register.html ^
  campwatch\templates\dashboard.html ^
  campwatch\templates\add.html ^
  campwatch\templates\settings.html ^
  %HOST%:%REMOTE_DIR%/templates/

echo [3/4] 서버 환경 설치 중...
ssh -i "%KEY%" -o StrictHostKeyChecking=no %HOST% "cd %REMOTE_DIR% && pip3 install -r requirements.txt -q && chmod +x run.sh"

echo [4/4] 기존 프로세스 종료 후 재시작...
ssh -i "%KEY%" -o StrictHostKeyChecking=no %HOST% "pkill -f 'python3 app.py' 2>/dev/null; pkill -f 'python3 crawler.py' 2>/dev/null; cd %REMOTE_DIR% && bash run.sh"

echo.
echo =============================================
echo   배포 완료!
echo   접속: http://140.245.43.57:5000
echo =============================================
pause
