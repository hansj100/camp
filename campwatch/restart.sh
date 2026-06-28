#!/bin/bash
cd ~/campwatch

echo "GitHub에서 최신 코드 받는 중..."
git pull origin main 2>&1 || echo "git pull 실패 (계속 진행)"

pkill -f 'python3 app.py' 2>/dev/null
pkill -f 'python3 crawler.py' 2>/dev/null
sleep 1
mkdir -p logs
nohup python3 app.py > logs/web.log 2>&1 </dev/null &
nohup python3 crawler.py > logs/crawler.log 2>&1 </dev/null &
echo "재시작 완료"
