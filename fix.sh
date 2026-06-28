#!/bin/bash
KEY="/c/Users/han/Documents/Claude/Projects/camp/ssh-key-2026-06-25.key"
chmod 600 "$KEY"

echo "[1/4] DB 마이그레이션..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@140.245.43.57 "python3 - << 'EOF'
import sqlite3, os
conn = sqlite3.connect(os.path.expanduser('~/campwatch/campwatch.db'))
for col, defval in [('telegram_token','NULL'), ('level','1'), ('is_approved','1'), ('is_admin','0')]:
    try:
        conn.execute(f'ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT {defval}')
        print(f'users.{col} 추가')
    except:
        print(f'users.{col} 이미 있음')
try:
    conn.execute('ALTER TABLE watch_conditions ADD COLUMN nights INTEGER DEFAULT 1')
    print('watch_conditions.nights 추가')
except:
    print('watch_conditions.nights 이미 있음')
try:
    conn.execute('ALTER TABLE watch_conditions ADD COLUMN zone_id TEXT DEFAULT NULL')
    print('watch_conditions.zone_id 추가')
except:
    print('watch_conditions.zone_id 이미 있음')
conn.execute('UPDATE users SET is_approved=1 WHERE is_approved IS NULL')
conn.commit()
conn.close()
print('마이그레이션 완료')
EOF"

echo "[1b/4] favorites 테이블 마이그레이션..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@140.245.43.57 "python3 -c \"
import sqlite3
conn = sqlite3.connect('/home/ubuntu/campwatch/campwatch.db')
conn.execute('''CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    zone_id TEXT NOT NULL,
    campsite TEXT NOT NULL,
    sido TEXT DEFAULT \\\"\\\",
    created_at TEXT DEFAULT (datetime(\\\"now\\\",\\\"localtime\\\")),
    UNIQUE(user_id, zone_id)
)''')
conn.commit()
conn.close()
print('favorites 마이그레이션 완료')
\""

echo "[2/4] 파일 업로드..."
scp -i "$KEY" -o StrictHostKeyChecking=no \
  campwatch/app.py \
  campwatch/models.py \
  campwatch/crawler.py \
  campwatch/restart.sh \
  ubuntu@140.245.43.57:~/campwatch/

scp -i "$KEY" -o StrictHostKeyChecking=no \
  campwatch/templates/base.html \
  campwatch/templates/admin.html \
  campwatch/templates/telegram.html \
  campwatch/templates/settings.html \
  campwatch/templates/campsites.html \
  campwatch/templates/status.html \
  campwatch/templates/dashboard.html \
  campwatch/templates/favorites.html \
  ubuntu@140.245.43.57:~/campwatch/templates/

echo "[3/4] 패키지 설치..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@140.245.43.57 \
  "pip3 install -r ~/campwatch/requirements.txt -q --break-system-packages"

echo "[4/4] Flask 재시작..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@140.245.43.57 \
  "chmod +x ~/campwatch/restart.sh; pkill -f 'python3 app.py'; pkill -f 'python3 crawler.py'; sleep 1; mkdir -p ~/campwatch/logs; nohup python3 ~/campwatch/app.py > ~/campwatch/logs/web.log 2>&1 </dev/null & nohup python3 ~/campwatch/crawler.py > ~/campwatch/logs/crawler.log 2>&1 </dev/null & sleep 2 && ps aux | grep python3 | grep -v grep"

echo ""
echo "완료! → http://140.245.43.57:5000"
