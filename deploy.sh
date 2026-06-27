#!/bin/bash
KEY="/c/Users/han/Documents/Claude/Projects/camp/ssh-key-2026-06-25.key"
HOST="ubuntu@140.245.43.57"
REMOTE="~/campwatch"

chmod 600 "$KEY"

echo "[0/5] test 계정 관리자 권한 설정..."
ssh -i "$KEY" -o StrictHostKeyChecking=no $HOST "python3 - << 'EOF'
import sqlite3, bcrypt, os
conn = sqlite3.connect(os.path.expanduser('~/campwatch/campwatch.db'))
existing = conn.execute('SELECT id FROM users WHERE username=?', ('test',)).fetchone()
if existing:
    conn.execute('UPDATE users SET is_admin=1, is_approved=1 WHERE username=?', ('test',))
    print('test 계정 관리자 권한 부여 완료')
else:
    pw = bcrypt.hashpw(b'test1234', bcrypt.gensalt()).decode()
    conn.execute('INSERT INTO users (username,password,is_approved,is_admin) VALUES (?,?,1,1)', ('test', pw))
    print('test 계정 생성 완료 (비번: test1234)')
conn.commit()
conn.close()
EOF"

echo "[1/5] 파일 업로드..."
scp -i "$KEY" -o StrictHostKeyChecking=no \
  campwatch/app.py \
  campwatch/models.py \
  campwatch/crawler.py \
  campwatch/requirements.txt \
  campwatch/run.sh \
  campwatch/restart.sh \
  $HOST:$REMOTE/

scp -i "$KEY" -o StrictHostKeyChecking=no \
  campwatch/templates/*.html \
  $HOST:$REMOTE/templates/

echo "[2/5] 패키지 설치..."
ssh -i "$KEY" -o StrictHostKeyChecking=no $HOST \
  "pip3 install -r $REMOTE/requirements.txt -q --break-system-packages"

echo "[3/5] DB 마이그레이션..."
ssh -i "$KEY" -o StrictHostKeyChecking=no $HOST "python3 - << 'EOF'
import sqlite3, os
conn = sqlite3.connect(os.path.expanduser('~/campwatch/campwatch.db'))
for col, defval in [('is_approved','1'), ('is_admin','0')]:
    try:
        conn.execute(f'ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT {defval}')
        print(f'{col} 컬럼 추가')
    except:
        print(f'{col} 이미 있음')
conn.execute('UPDATE users SET is_approved=1 WHERE is_approved IS NULL')
conn.commit()
conn.close()
print('마이그레이션 완료')
EOF"

echo "[4/5] Flask 재시작..."
ssh -i "$KEY" -o StrictHostKeyChecking=no $HOST \
  "pkill -f 'python3 app.py' 2>/dev/null; pkill -f 'python3 crawler.py' 2>/dev/null; chmod +x $REMOTE/restart.sh; sleep 1; mkdir -p $REMOTE/logs; nohup python3 $REMOTE/app.py > $REMOTE/logs/web.log 2>&1 </dev/null & nohup python3 $REMOTE/crawler.py > $REMOTE/logs/crawler.log 2>&1 </dev/null & sleep 2 && ps aux | grep python3 | grep -v grep"

echo ""
echo "[5/5] 완료! → http://140.245.43.57:5000"
echo "관리자: admin / campwatch1234"
echo "테스트: test / test1234"
