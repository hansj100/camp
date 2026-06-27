#!/bin/bash
# CampWatch 시작 스크립트

cd "$(dirname "$0")"

echo "=== CampWatch 시작 ==="

# 웹서버 백그라운드 실행
nohup python3 app.py > logs/web.log 2>&1 &
WEB_PID=$!
echo "웹서버 PID: $WEB_PID"

# 크롤러 백그라운드 실행
nohup python3 crawler.py > logs/crawler.log 2>&1 &
CRAWLER_PID=$!
echo "크롤러 PID: $CRAWLER_PID"

echo "$WEB_PID" > logs/web.pid
echo "$CRAWLER_PID" > logs/crawler.pid

echo "실행 완료. 접속: http://$(curl -s ifconfig.me):5000"
echo "로그: tail -f logs/web.log  /  tail -f logs/crawler.log"
