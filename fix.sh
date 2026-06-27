#!/bin/bash
KEY="/c/Users/han/Documents/Claude/Projects/camp/ssh-key-2026-06-25.key"
APP="/c/Users/han/Documents/Claude/Projects/camp/campwatch/app.py"
chmod 600 "$KEY"
echo "앱 업로드 중..."
scp -i "$KEY" -o StrictHostKeyChecking=no "$APP" ubuntu@140.245.43.57:~/campwatch/
echo "Flask 재시작..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@140.245.43.57 "pkill -f 'python3 app.py' 2>/dev/null; sleep 1; nohup python3 ~/campwatch/app.py > ~/campwatch/logs/web.log 2>&1 </dev/null & sleep 2 && echo '완료'"
