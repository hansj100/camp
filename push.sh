#!/bin/bash
cd "/c/Users/han/Documents/Claude/Projects/camp"
git add -A
git commit -m "update $(date '+%Y-%m-%d %H:%M')"
git push origin main
echo "GitHub 업로드 완료! 이제 서버에서 재시작 버튼 누르세요."
