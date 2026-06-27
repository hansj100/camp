#!/bin/bash
cd ~/campwatch

# GitHub에서 최신 코드 pull
echo "GitHub에서 최신 코드 받는 중..."
git pull origin main 2>&1 || echo "git pull 실패 (무시하고 계속)"

# Flask 재시작
pkill -f 'python3 app.py' 2>/dev/null
pkill -f 'python3 crawler.py' 2>/dev/null
sleep 1
mkdir -p logs
nohup python3 app.py > logs/web.log 2>&1 &
nohup python3 crawler.py > logs/crawler.log 2>&1 &
echo "재시작 완료"
