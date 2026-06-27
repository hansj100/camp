#!/bin/bash
cd "/c/Users/han/Documents/Claude/Projects/camp"

echo "[1/4] Git 사용자 설정..."
git config --global user.email "hansj10014@gmail.com"
git config --global user.name "hansj100"
git config --global init.defaultBranch main

echo "[2/4] Git 초기화..."
git init
git branch -M main
git remote remove origin 2>/dev/null
git remote add origin https://github.com/hansj100/camp.git

echo "[3/4] 첫 커밋..."
git add -A
git commit -m "CampWatch 초기 업로드"

echo "[4/4] GitHub에 push..."
git push -u origin main

echo ""
echo "로컬 완료! 서버 git 설정 중..."

KEY="/c/Users/han/Documents/Claude/Projects/camp/ssh-key-2026-06-25.key"
chmod 600 "$KEY"

ssh -i "$KEY" -o StrictHostKeyChecking=no ubuntu@140.245.43.57 "
  cd ~/campwatch
  rm -rf .git
  git init
  git config user.email 'hansj10014@gmail.com'
  git config user.name 'hansj100'
  git remote add origin https://github.com/hansj100/camp.git
  git fetch origin main
  git checkout -f main
  chmod +x restart.sh
  echo '서버 git 설정 완료'
"
echo "모두 완료!"
