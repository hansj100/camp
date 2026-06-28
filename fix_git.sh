#!/bin/bash
# fix_git.sh — GitHub 설정 + 최초 push
KEY="/c/Users/han/Documents/Claude/Projects/camp/ssh-key-2026-06-25.key"
chmod 600 "$KEY"

echo "[1/5] git 기본 설정..."
git config --global user.email "hansj10014@gmail.com"
git config --global user.name "han"

echo "[2/5] git 초기화..."
cd "/c/Users/han/Documents/Claude/Projects/camp"
git init 2>/dev/null || true
git checkout -b main 2>/dev/null || git checkout main 2>/dev/null || true
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/hansj100/camp.git

echo "[3/5] 파일 추가 및 커밋..."
git add -A
git commit -m "CampWatch initial commit" 2>/dev/null || git commit --allow-empty -m "update"

echo "[4/5] GitHub push..."
git push -u origin main --force

echo "[5/5] 서버에 git 설정..."
ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@140.245.43.57 << 'SSHEOF'
cd ~/campwatch
git config --global user.email "server@campwatch.com"
git config --global user.name "server"
git init 2>/dev/null || true
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/hansj100/camp.git
git fetch origin main
git checkout -f main 2>/dev/null || git checkout -b main origin/main
chmod +x restart.sh
echo "서버 git 설정 완료"
SSHEOF

echo ""
echo "완료! 이제 재시작 버튼이 git pull로 최신 코드를 가져옵니다."
