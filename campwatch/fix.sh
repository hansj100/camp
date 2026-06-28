#!/bin/bash
# CampWatch DB 마이그레이션 및 배포 스크립트

SERVER="ubuntu@140.245.43.57"
KEY="$1"  # 사용법: bash fix.sh ~/.ssh/your-key.pem

if [ -z "$KEY" ]; then
  echo "사용법: bash fix.sh ~/.ssh/your-key.pem"
  exit 1
fi

echo "=== 1. DB 마이그레이션: watch_conditions.source 컬럼 추가 ==="
ssh -i "$KEY" "$SERVER" "python3 -c \"
import sqlite3
conn = sqlite3.connect('/home/ubuntu/campwatch/campwatch.db')
try:
    conn.execute(\\\"ALTER TABLE watch_conditions ADD COLUMN source TEXT DEFAULT 'foresttrip'\\\")
    conn.commit()
    print('source 컬럼 추가 완료')
except Exception as e:
    print('이미 존재 또는 오류:', e)
conn.close()
\""

echo "=== 2. 최신 코드 pull 및 재시작 ==="
ssh -i "$KEY" "$SERVER" "cd /home/ubuntu/campwatch && git pull origin main && bash restart.sh"

echo "=== 완료 ==="
