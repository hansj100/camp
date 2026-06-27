#!/bin/bash
cd ~/campwatch
mkdir -p logs
pkill -f 'python3 app.py' 2>/dev/null
pkill -f 'python3 crawler.py' 2>/dev/null
sleep 1
nohup python3 app.py > logs/web.log 2>&1 &
echo "web PID: $!"
nohup python3 crawler.py > logs/crawler.log 2>&1 &
echo "crawler PID: $!"
sleep 2
ps aux | grep python3 | grep -v grep
